"""Background worker threads for long-running operations."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Signal

from txt_process.core.chunking import split_into_chunks
from txt_process.core.llm_client import LLMClient
from txt_process.core.name_extract import (
    count_name_occurrences,
    dedupe_names,
    extract_names_from_response,
)

if TYPE_CHECKING:
    from txt_process.core.config import Config


class ExtractNamesWorker(QObject):
    """Worker that extracts names from text using LLM.

    When the total chunk count exceeds ``config.begin_scan_chunks``, a
    three-phase strategy is used to reduce the number of LLM calls:

    Phase 1 – seed scan: send all chunks up to ``begin_scan_chunks``, then
              every ``scan_interval``-th chunk after that.
    Phase 2 – local scan: substring-search skipped chunks for known names.
    Phase 3 – targeted fill: send skipped chunks with <2 known-name hits to
              the LLM.

    For shorter documents the worker falls back to the original serial scan.
    """

    progress = Signal(int, int, str)  # current, total, status
    chunk_names = Signal(int, list)  # chunk_index, names
    chunk_error = Signal(int, str)  # chunk_index, error_message
    finished = Signal(list, dict)  # deduplicated names, occurrence counts
    error = Signal(str, str)  # message, details
    log = Signal(str)  # free-form log line

    def __init__(self, text: str, config: "Config", api_key: str) -> None:
        super().__init__()
        self.text = text
        self.config = config
        self.api_key = api_key
        self._cancelled = False
        self._last_request_start = 0.0

    def cancel(self) -> None:
        """Request cancellation of the extraction."""
        self._cancelled = True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _wait_interval(self, progress_idx: int, progress_total: int) -> bool:
        """Sleep until the inter-request interval has elapsed.

        Returns False if cancelled during the wait.
        """
        interval = self.config.request_interval_seconds
        elapsed = time.monotonic() - self._last_request_start
        if self._last_request_start > 0 and elapsed < interval:
            wait_time = interval - elapsed
            self.progress.emit(
                progress_idx, progress_total, f"Waiting {wait_time:.1f}s..."
            )
            wait_start = time.monotonic()
            while time.monotonic() - wait_start < wait_time:
                if self._cancelled:
                    return False
                time.sleep(0.1)
        return True

    def _call_llm_for_chunk(
        self,
        chunk_idx: int,
        chunk_text: str,
        client: LLMClient,
        all_names: list[str],
        failed_chunks: list[tuple[int, str]],
        progress_idx: int,
        progress_total: int,
    ) -> bool | None:
        """Send one chunk to the LLM with rate-limiting and error handling.

        Returns ``True`` on success, ``False`` on non-fatal error,
        ``None`` when the run must abort (rate-limit or cancellation).
        """
        if self._cancelled:
            self.error.emit("Cancelled", "Extraction was cancelled by user.")
            return None

        if not self._wait_interval(progress_idx, progress_total):
            self.error.emit("Cancelled", "Extraction was cancelled by user.")
            return None

        self.progress.emit(progress_idx, progress_total, f"Calling model (chunk {chunk_idx + 1})...")
        prompt = self.config.prompt_template.replace("{chunk_text}", chunk_text)

        try:
            self._last_request_start = time.monotonic()
            response = client.chat(prompt)
            names = extract_names_from_response(response)
            all_names.extend(names)
            self.chunk_names.emit(chunk_idx, names)
            return True
        except Exception as e:
            if _is_rate_limit_error(e):
                wait_info = _extract_rate_limit_wait(str(e))
                message = "Rate limit exceeded. Please wait and retry."
                details = wait_info.get("message") or "Provider rate limit."
                self.error.emit(message, details)
                return None
            failed_chunks.append((chunk_idx, str(e)))
            self.chunk_error.emit(chunk_idx, str(e))
            return False

    # ------------------------------------------------------------------
    # Main entry
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Execute the extraction process."""
        try:
            self.progress.emit(0, 0, "Splitting text into chunks...")
            chunks = split_into_chunks(self.text, self.config.chunk_max_bytes)
            total_chunks = len(chunks)

            if total_chunks == 0:
                self.finished.emit([], {})
                return

            client = LLMClient(
                base_url=self.config.base_url,
                api_key=self.api_key,
                model=self.config.model,
                temperature=self.config.temperature,
                timeout=self.config.timeout_seconds,
                max_tokens=self.config.max_tokens,
            )

            if total_chunks <= self.config.begin_scan_chunks:
                self._run_serial(chunks, client)
            else:
                self._run_phased(chunks, client)

        except Exception as e:
            self.error.emit("Extraction failed", str(e))

    # ------------------------------------------------------------------
    # Serial path (small documents)
    # ------------------------------------------------------------------

    def _run_serial(self, chunks: list[str], client: LLMClient) -> None:
        """Original serial scan — one LLM call per chunk."""
        total = len(chunks)
        all_names: list[str] = []
        failed_chunks: list[tuple[int, str]] = []

        self.log.emit(f"Serial extraction: {total} chunks (below threshold, scanning all)")

        for progress_idx, (i, chunk) in enumerate(enumerate(chunks)):
            result = self._call_llm_for_chunk(
                i, chunk, client, all_names, failed_chunks, progress_idx, total
            )
            if result is None:
                return
            self.progress.emit(progress_idx + 1, total, "Processing...")

        self._finish(all_names, failed_chunks)

    # ------------------------------------------------------------------
    # Three-phase path (large documents)
    # ------------------------------------------------------------------

    def _run_phased(self, chunks: list[str], client: LLMClient) -> None:
        total_chunks = len(chunks)
        begin = self.config.begin_scan_chunks
        interval = self.config.scan_interval

        phase1_indices: list[int] = list(range(begin))
        for i in range(begin, total_chunks, interval):
            phase1_indices.append(i)

        phase1_set = set(phase1_indices)
        skipped_indices = [i for i in range(total_chunks) if i not in phase1_set]

        # ---- Phase 1: seed scan via LLM ----
        self.log.emit(
            f"Phase 1: seed scan — sending {len(phase1_indices)} of {total_chunks} "
            f"chunks to LLM (first {begin} + every {interval}th after)"
        )

        all_names: list[str] = []
        failed_chunks: list[tuple[int, str]] = []
        phase1_total = len(phase1_indices)

        for progress_idx, chunk_idx in enumerate(phase1_indices):
            result = self._call_llm_for_chunk(
                chunk_idx,
                chunks[chunk_idx],
                client,
                all_names,
                failed_chunks,
                progress_idx,
                phase1_total,
            )
            if result is None:
                return
            self.progress.emit(progress_idx + 1, phase1_total, "Phase 1 — scanning...")

        known_names = set(dedupe_names(all_names))
        self.log.emit(f"Phase 1 complete: {len(known_names)} unique names discovered")

        if not known_names and not skipped_indices:
            self._finish(all_names, failed_chunks)
            return

        # ---- Phase 2: local substring scan of skipped chunks ----
        self.log.emit(
            f"Phase 2: local scan — checking {len(skipped_indices)} skipped chunks "
            f"for {len(known_names)} known names"
        )
        self.progress.emit(0, len(skipped_indices), "Phase 2 — local scan...")

        phase3_candidates: list[int] = []
        for scan_idx, chunk_idx in enumerate(skipped_indices):
            if self._cancelled:
                self.error.emit("Cancelled", "Extraction was cancelled by user.")
                return

            chunk_text = chunks[chunk_idx]
            hit_count = sum(1 for name in known_names if name in chunk_text)
            if hit_count < 2:
                phase3_candidates.append(chunk_idx)

            self.progress.emit(scan_idx + 1, len(skipped_indices), "Phase 2 — local scan...")

        self.log.emit(
            f"Phase 2 complete: {len(phase3_candidates)} chunks have <2 known-name "
            f"hits — queued for Phase 3"
        )

        # ---- Phase 3: targeted LLM calls for low-hit chunks ----
        if phase3_candidates:
            self.log.emit(
                f"Phase 3: targeted fill — sending {len(phase3_candidates)} "
                f"chunks to LLM"
            )
            phase3_total = len(phase3_candidates)

            for progress_idx, chunk_idx in enumerate(phase3_candidates):
                result = self._call_llm_for_chunk(
                    chunk_idx,
                    chunks[chunk_idx],
                    client,
                    all_names,
                    failed_chunks,
                    progress_idx,
                    phase3_total,
                )
                if result is None:
                    return
                self.progress.emit(
                    progress_idx + 1, phase3_total, "Phase 3 — targeted fill..."
                )

            self.log.emit("Phase 3 complete")
        else:
            self.log.emit("Phase 3: skipped — no low-hit chunks found")

        self._finish(all_names, failed_chunks)

    # ------------------------------------------------------------------
    # Shared finish
    # ------------------------------------------------------------------

    def _finish(
        self, all_names: list[str], failed_chunks: list[tuple[int, str]]
    ) -> None:
        if not all_names and failed_chunks:
            _, first_error = failed_chunks[0]
            self.error.emit(
                f"All {len(failed_chunks)} chunk(s) failed",
                first_error,
            )
            return

        deduped = dedupe_names(all_names)
        counts = count_name_occurrences(self.text, deduped)
        self.finished.emit(deduped, counts)


def _is_rate_limit_error(error: Exception) -> bool:
    """Detect if an exception indicates rate limiting."""
    name = type(error).__name__
    msg = str(error).lower()
    return "ratelimit" in name.lower() or "rate limit" in msg or "error code: 429" in msg


def _extract_rate_limit_wait(message: str) -> dict[str, object]:
    """Extract rate limit reset info from error message string."""
    import re
    import time

    match = re.search(r"X-RateLimit-Reset': '\\d+'", message)
    if match:
        reset_str = match.group().split("'")[-2]
        try:
            reset_ms = int(reset_str)
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
