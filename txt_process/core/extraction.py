"""Shared extraction orchestration used by all UI layers."""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from txt_process.core.chunking import split_into_chunks
from txt_process.core.config import Config
from txt_process.core.llm_client import LLMClient
from txt_process.core.name_extract import dedupe_names, extract_names_from_response
from txt_process.core.replace import count_name_occurrences

_FIRST_CHUNK_LLM_TIMEOUT_SECONDS = 30.0


@dataclass(slots=True)
class ProgressEvent:
    """Progress payload emitted during extraction."""

    stage: str
    current: int
    total: int
    detail: str | None = None
    running_names: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ExtractionResult:
    """Final extraction output."""

    name_pairs: list[tuple[str, str]]
    counts: dict[str, int]
    errors: list[str] = field(default_factory=list)


class ExtractionCallbacks(Protocol):
    """Callback contract for UI adapters."""

    def on_progress(self, event: ProgressEvent) -> None:
        """Handle progress updates."""

    def on_log(self, message: str) -> None:
        """Handle free-form diagnostics."""

    def on_chunk_names(self, chunk_index: int, names: list[str]) -> None:
        """Handle parsed names for one chunk."""

    def on_chunk_error(self, chunk_index: int, message: str) -> None:
        """Handle non-fatal per-chunk errors."""

    def should_cancel(self) -> bool:
        """Return ``True`` when extraction should stop."""


class ExtractionCancelled(RuntimeError):
    """Raised when extraction is cancelled."""


class ChunkRequestError(RuntimeError):
    """Wrap a chunk failure together with the latest request start time."""

    def __init__(self, error: Exception, request_start: float) -> None:
        super().__init__(str(error))
        self.error = error
        self.request_start = request_start


class _NoopCallbacks:
    def on_progress(self, event: ProgressEvent) -> None:
        return None

    def on_log(self, message: str) -> None:
        return None

    def on_chunk_names(self, chunk_index: int, names: list[str]) -> None:
        return None

    def on_chunk_error(self, chunk_index: int, message: str) -> None:
        return None

    def should_cancel(self) -> bool:
        return False


def _phase_1_indices(total_chunks: int, begin_scan_chunks: int, scan_interval: int) -> list[int]:
    """Return phase-1 indices for sampled extraction."""
    if total_chunks <= 0:
        return []

    begin = max(0, min(begin_scan_chunks, total_chunks))
    interval = max(1, scan_interval)

    indices: list[int] = list(range(begin))
    indices.extend(range(begin, total_chunks, interval))
    return list(dict.fromkeys(indices))


def _phase_2_local_scan(
    chunks: list[str], known_names: set[str], skipped_indices: list[int]
) -> dict[int, int]:
    """Count known-name hits for skipped chunks."""
    local_counts: dict[int, int] = {}
    for chunk_idx in skipped_indices:
        chunk_text = chunks[chunk_idx]
        local_counts[chunk_idx] = sum(1 for name in known_names if name in chunk_text)
    return local_counts


def _phase_3_fill_indices(local_counts: dict[int, int], threshold: int = 2) -> list[int]:
    """Return skipped chunk indices that should be sent in phase 3."""
    return [chunk_idx for chunk_idx, hit_count in local_counts.items() if hit_count < threshold]


def _wait_for_seconds(
    wait_seconds: float,
    *,
    should_cancel: Callable[[], bool],
    monotonic_clock: Callable[[], float],
    sleeper: Callable[[float], None],
    on_wait: Callable[[float], None] | None = None,
) -> None:
    """Sleep cooperatively, checking cancellation while waiting."""
    wait_seconds = max(0.0, wait_seconds)
    if wait_seconds <= 0:
        return
    if on_wait is not None:
        on_wait(wait_seconds)

    deadline = monotonic_clock() + wait_seconds
    while monotonic_clock() < deadline:
        if should_cancel():
            raise ExtractionCancelled("Extraction was cancelled by user.")
        remaining = deadline - monotonic_clock()
        sleeper(min(0.1, remaining))


def _wait_with_cadence(
    *,
    last_request_start: float,
    interval_seconds: float,
    should_cancel: Callable[[], bool],
    monotonic_clock: Callable[[], float],
    sleeper: Callable[[float], None],
    on_wait: Callable[[float], None] | None = None,
) -> None:
    """Wait until the configured request-start interval has elapsed."""
    if last_request_start < 0:
        return

    elapsed = monotonic_clock() - last_request_start
    remaining = interval_seconds - elapsed
    if remaining <= 0:
        return

    _wait_for_seconds(
        remaining,
        should_cancel=should_cancel,
        monotonic_clock=monotonic_clock,
        sleeper=sleeper,
        on_wait=on_wait,
    )


def _build_strict_retry_prompt(prompt: str) -> str:
    return (
        "Your previous response was not valid. Respond with ONLY strict JSON in this "
        'exact form and nothing else: {"names": ["Name1", "Name2", ...]}\n\n' + prompt
    )


def _is_rate_limit_error(error: Exception) -> bool:
    """Detect provider rate-limit exceptions from transport/client text."""
    name = type(error).__name__.lower()
    message = str(error).lower()
    return "ratelimit" in name or "rate limit" in message or "error code: 429" in message


def _extract_rate_limit_wait(message: str) -> dict[str, object]:
    """Extract ``X-RateLimit-Reset`` milliseconds from provider error text."""
    match = re.search(r"X-RateLimit-Reset': '(\d+)'", message)
    if match:
        try:
            reset_ms = int(match.group(1))
            now_ms = int(time.time() * 1000)
            wait_seconds = max(0, int((reset_ms - now_ms) / 1000))
            return {
                "wait_seconds": wait_seconds,
                "has_reset": True,
                "message": f"Provider rate limit. Try again in ~{wait_seconds}s.",
            }
        except ValueError:
            pass
    return {"wait_seconds": None, "has_reset": False, "message": "Provider rate limit."}


def _call_llm_for_chunk(
    *,
    chunk_index: int,
    chunk_text: str,
    client: LLMClient,
    config: Config,
    callbacks: ExtractionCallbacks,
    all_names: list[str],
    progress_idx: int,
    progress_total: int,
    last_request_start: float,
    monotonic_clock: Callable[[], float],
    sleeper: Callable[[float], None],
) -> tuple[list[str], float]:
    """Call the LLM for one chunk with cadence + corrective retry."""
    if callbacks.should_cancel():
        raise ExtractionCancelled("Extraction was cancelled by user.")

    _wait_with_cadence(
        last_request_start=last_request_start,
        interval_seconds=config.request_interval_seconds,
        should_cancel=callbacks.should_cancel,
        monotonic_clock=monotonic_clock,
        sleeper=sleeper,
        on_wait=lambda wait: callbacks.on_progress(
            ProgressEvent(
                stage="waiting_interval",
                current=progress_idx,
                total=progress_total,
                detail=f"Waiting {wait:.1f}s...",
                running_names=dedupe_names(all_names),
            )
        ),
    )

    callbacks.on_progress(
        ProgressEvent(
            stage="calling_model",
            current=progress_idx,
            total=progress_total,
            detail=f"Calling model (chunk {chunk_index + 1})...",
            running_names=dedupe_names(all_names),
        )
    )

    prompt = config.prompt_template.replace("{chunk_text}", chunk_text)
    chunk_timeout = _FIRST_CHUNK_LLM_TIMEOUT_SECONDS if chunk_index == 0 else None

    request_start = monotonic_clock()
    try:
        response = client.chat(prompt, timeout=chunk_timeout)
    except Exception as error:  # noqa: BLE001 - surfaced to UI as chunk_error
        raise ChunkRequestError(error, request_start) from error

    callbacks.on_progress(
        ProgressEvent(
            stage="parsing",
            current=progress_idx,
            total=progress_total,
            detail=f"Parsing chunk {chunk_index + 1}...",
            running_names=dedupe_names(all_names),
        )
    )
    try:
        names = extract_names_from_response(response)
    except ValueError as parse_error:
        callbacks.on_log(
            f"Chunk {chunk_index + 1}: unparseable response, retrying with strict-JSON "
            "instruction."
        )
        _wait_with_cadence(
            last_request_start=request_start,
            interval_seconds=config.request_interval_seconds,
            should_cancel=callbacks.should_cancel,
            monotonic_clock=monotonic_clock,
            sleeper=sleeper,
            on_wait=lambda wait: callbacks.on_progress(
                ProgressEvent(
                    stage="waiting_interval",
                    current=progress_idx,
                    total=progress_total,
                    detail=f"Waiting {wait:.1f}s...",
                    running_names=dedupe_names(all_names),
                )
            ),
        )
        callbacks.on_progress(
            ProgressEvent(
                stage="calling_model",
                current=progress_idx,
                total=progress_total,
                detail=f"Retrying chunk {chunk_index + 1} (strict JSON)...",
                running_names=dedupe_names(all_names),
            )
        )
        retry_prompt = _build_strict_retry_prompt(prompt)
        request_start = monotonic_clock()
        response = client.chat(retry_prompt, timeout=chunk_timeout)
        callbacks.on_progress(
            ProgressEvent(
                stage="parsing",
                current=progress_idx,
                total=progress_total,
                detail=f"Parsing chunk {chunk_index + 1}...",
                running_names=dedupe_names(all_names),
            )
        )
        try:
            names = extract_names_from_response(response)
        except ValueError:
            raise ChunkRequestError(parse_error, request_start) from None

    return names, request_start


def _record_chunk_failure(
    *,
    chunk_index: int,
    error: Exception,
    callbacks: ExtractionCallbacks,
    all_names: list[str],
    progress_idx: int,
    progress_total: int,
    monotonic_clock: Callable[[], float],
    sleeper: Callable[[float], None],
    failed_chunks: list[tuple[int, str]],
) -> None:
    """Record one failed chunk and perform provider wait when applicable."""
    if _is_rate_limit_error(error):
        wait_info = _extract_rate_limit_wait(str(error))
        message = str(wait_info.get("message") or "Provider rate limit.")
        callbacks.on_log(message)
        wait_seconds = wait_info.get("wait_seconds")
        if isinstance(wait_seconds, int | float) and wait_seconds > 0:
            _wait_for_seconds(
                float(wait_seconds),
                should_cancel=callbacks.should_cancel,
                monotonic_clock=monotonic_clock,
                sleeper=sleeper,
                on_wait=lambda wait: callbacks.on_progress(
                    ProgressEvent(
                        stage="waiting_interval",
                        current=progress_idx,
                        total=progress_total,
                        detail=f"Waiting {wait:.1f}s for rate-limit reset...",
                        running_names=dedupe_names(all_names),
                    )
                ),
            )

    message = str(error)
    failed_chunks.append((chunk_index, message))
    callbacks.on_chunk_error(chunk_index, message)


def _run_chunk_pass(
    *,
    indices: list[int],
    chunks: list[str],
    client: LLMClient,
    config: Config,
    callbacks: ExtractionCallbacks,
    all_names: list[str],
    failed_chunks: list[tuple[int, str]],
    status_detail: str,
    last_request_start: float,
    monotonic_clock: Callable[[], float],
    sleeper: Callable[[float], None],
) -> float:
    """Run one pass of chunk indices, collecting successes and failures."""
    total = len(indices)
    for progress_idx, chunk_index in enumerate(indices):
        try:
            names, last_request_start = _call_llm_for_chunk(
                chunk_index=chunk_index,
                chunk_text=chunks[chunk_index],
                client=client,
                config=config,
                callbacks=callbacks,
                all_names=all_names,
                progress_idx=progress_idx,
                progress_total=total,
                last_request_start=last_request_start,
                monotonic_clock=monotonic_clock,
                sleeper=sleeper,
            )
        except ExtractionCancelled:
            raise
        except ChunkRequestError as error:
            last_request_start = error.request_start
            _record_chunk_failure(
                chunk_index=chunk_index,
                error=error.error,
                callbacks=callbacks,
                all_names=all_names,
                progress_idx=progress_idx,
                progress_total=total,
                monotonic_clock=monotonic_clock,
                sleeper=sleeper,
                failed_chunks=failed_chunks,
            )
            continue
        except Exception as error:  # noqa: BLE001 - surfaced to UI as chunk_error
            _record_chunk_failure(
                chunk_index=chunk_index,
                error=error,
                callbacks=callbacks,
                all_names=all_names,
                progress_idx=progress_idx,
                progress_total=total,
                monotonic_clock=monotonic_clock,
                sleeper=sleeper,
                failed_chunks=failed_chunks,
            )
            continue

        all_names.extend(names)
        callbacks.on_chunk_names(chunk_index, names)
        callbacks.on_progress(
            ProgressEvent(
                stage="calling_model",
                current=progress_idx + 1,
                total=total,
                detail=status_detail,
                running_names=dedupe_names(all_names),
            )
        )

    return last_request_start


def run_extraction(
    text: str,
    config: Config,
    api_key: str,
    callbacks: ExtractionCallbacks | None = None,
    *,
    monotonic_clock: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
) -> ExtractionResult:
    """Run extraction using serial or phased strategy."""
    callbacks = callbacks or _NoopCallbacks()

    callbacks.on_progress(
        ProgressEvent(
            stage="splitting",
            current=0,
            total=0,
            detail="Splitting text into chunks...",
            running_names=[],
        )
    )
    chunks = split_into_chunks(text, config.chunk_max_bytes)
    total_chunks = len(chunks)

    if total_chunks == 0:
        return ExtractionResult(name_pairs=[], counts={}, errors=[])

    client = LLMClient(
        base_url=config.base_url,
        api_key=api_key,
        model=config.model,
        temperature=config.temperature,
        timeout=config.timeout_seconds,
        max_tokens=config.max_tokens,
    )

    all_names: list[str] = []
    failed_chunks: list[tuple[int, str]] = []
    last_request_start = -1.0

    if total_chunks <= config.begin_scan_chunks:
        callbacks.on_log(
            f"Serial extraction: {total_chunks} chunks (below threshold, scanning all)"
        )
        last_request_start = _run_chunk_pass(
            indices=list(range(total_chunks)),
            chunks=chunks,
            client=client,
            config=config,
            callbacks=callbacks,
            all_names=all_names,
            failed_chunks=failed_chunks,
            status_detail="Processing...",
            last_request_start=last_request_start,
            monotonic_clock=monotonic_clock,
            sleeper=sleeper,
        )
    else:
        begin = config.begin_scan_chunks
        interval = config.scan_interval
        phase1_indices = _phase_1_indices(total_chunks, begin, interval)
        phase1_set = set(phase1_indices)
        skipped_indices = [idx for idx in range(total_chunks) if idx not in phase1_set]

        callbacks.on_log(
            f"Phase 1: seed scan, sending {len(phase1_indices)} of {total_chunks} chunks "
            f"(first {begin} + every {interval}th after)"
        )
        last_request_start = _run_chunk_pass(
            indices=phase1_indices,
            chunks=chunks,
            client=client,
            config=config,
            callbacks=callbacks,
            all_names=all_names,
            failed_chunks=failed_chunks,
            status_detail="Phase 1 — scanning...",
            last_request_start=last_request_start,
            monotonic_clock=monotonic_clock,
            sleeper=sleeper,
        )

        known_names = set(dedupe_names(all_names))
        callbacks.on_log(f"Phase 1 complete: {len(known_names)} unique names discovered")

        if skipped_indices:
            callbacks.on_log(
                f"Phase 2: local scan, checking {len(skipped_indices)} skipped chunks for "
                f"{len(known_names)} known names"
            )
            callbacks.on_progress(
                ProgressEvent(
                    stage="local_scan",
                    current=0,
                    total=len(skipped_indices),
                    detail="Phase 2 — local scan...",
                    running_names=dedupe_names(all_names),
                )
            )

            local_counts: dict[int, int] = {}
            for scan_idx, chunk_index in enumerate(skipped_indices):
                if callbacks.should_cancel():
                    raise ExtractionCancelled("Extraction was cancelled by user.")
                chunk_text = chunks[chunk_index]
                local_counts[chunk_index] = sum(1 for name in known_names if name in chunk_text)
                callbacks.on_progress(
                    ProgressEvent(
                        stage="local_scan",
                        current=scan_idx + 1,
                        total=len(skipped_indices),
                        detail="Phase 2 — local scan...",
                        running_names=dedupe_names(all_names),
                    )
                )

            phase3_candidates = _phase_3_fill_indices(local_counts, threshold=2)
            callbacks.on_log(
                f"Phase 2 complete: {len(phase3_candidates)} chunks have <2 known-name hits"
            )
            if phase3_candidates:
                callbacks.on_log(
                    f"Phase 3: targeted fill, sending {len(phase3_candidates)} chunks to LLM"
                )
                last_request_start = _run_chunk_pass(
                    indices=phase3_candidates,
                    chunks=chunks,
                    client=client,
                    config=config,
                    callbacks=callbacks,
                    all_names=all_names,
                    failed_chunks=failed_chunks,
                    status_detail="Phase 3 — targeted fill...",
                    last_request_start=last_request_start,
                    monotonic_clock=monotonic_clock,
                    sleeper=sleeper,
                )
            else:
                callbacks.on_log("Phase 3: skipped, no low-hit chunks found")

    deduped = dedupe_names(all_names)
    counts = {name: count_name_occurrences(text, name) for name in deduped}
    callbacks.on_progress(
        ProgressEvent(
            stage="done",
            current=total_chunks,
            total=total_chunks,
            detail="Done",
            running_names=deduped,
        )
    )
    return ExtractionResult(
        name_pairs=[(name, "") for name in deduped],
        counts=counts,
        errors=[f"Chunk {chunk_index + 1}: {message}" for chunk_index, message in failed_chunks],
    )
