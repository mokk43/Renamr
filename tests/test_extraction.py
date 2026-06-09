"""Tests for shared extraction orchestration."""

from __future__ import annotations

import json
from unittest.mock import patch

from txt_process.core.config import Config
from txt_process.core.extraction import (
    ExtractionResult,
    ProgressEvent,
    run_extraction,
)


class _FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        seconds = max(0.0, seconds)
        self.sleeps.append(seconds)
        self.now += seconds


class _CallbackRecorder:
    def __init__(self) -> None:
        self.progress: list[ProgressEvent] = []
        self.logs: list[str] = []
        self.chunk_name_payloads: list[tuple[int, list[str]]] = []
        self.chunk_error_payloads: list[tuple[int, str]] = []
        self.cancelled = False

    def on_progress(self, event: ProgressEvent) -> None:
        self.progress.append(event)

    def on_log(self, message: str) -> None:
        self.logs.append(message)

    def on_chunk_names(self, chunk_index: int, names: list[str]) -> None:
        self.chunk_name_payloads.append((chunk_index, names))

    def on_chunk_error(self, chunk_index: int, message: str) -> None:
        self.chunk_error_payloads.append((chunk_index, message))

    def should_cancel(self) -> bool:
        return self.cancelled


def test_serial_calls_respect_interval_and_no_overlap():
    interval = 0.2
    config = Config(
        base_url="http://localhost:11434",
        model="mock",
        prompt_template="{chunk_text}",
        request_interval_seconds=interval,
        begin_scan_chunks=10,
    )
    chunks = ["chunk-0", "chunk-1", "chunk-2"]
    clock = _FakeClock()
    callbacks = _CallbackRecorder()

    start_times: list[float] = []
    in_flight = 0
    max_in_flight = 0

    def fake_chat(prompt: str, **_kwargs: object) -> str:
        nonlocal in_flight, max_in_flight
        _ = prompt
        in_flight += 1
        max_in_flight = max(max_in_flight, in_flight)
        start_times.append(clock.monotonic())
        clock.sleep(0.05)
        in_flight -= 1
        return '{"names": []}'

    with (
        patch("txt_process.core.extraction.split_into_chunks", return_value=chunks),
        patch("txt_process.core.extraction.LLMClient") as mock_llm,
    ):
        mock_llm.return_value.chat.side_effect = fake_chat
        run_extraction(
            text="\n\n".join(chunks),
            config=config,
            api_key="ollama",
            callbacks=callbacks,
            monotonic_clock=clock.monotonic,
            sleeper=clock.sleep,
        )

    assert len(start_times) == len(chunks)
    assert max_in_flight == 1
    for idx in range(1, len(start_times)):
        assert start_times[idx] - start_times[idx - 1] >= interval - 1e-6


def test_failed_chunk_keeps_cadence_for_following_requests():
    interval = 2.0
    config = Config(
        base_url="http://localhost:11434",
        model="mock",
        prompt_template="{chunk_text}",
        request_interval_seconds=interval,
        begin_scan_chunks=10,
    )
    chunks = ["chunk-0", "chunk-1"]
    clock = _FakeClock()
    callbacks = _CallbackRecorder()
    start_times: list[float] = []
    responses = iter([RuntimeError("transient"), '{"names": ["Alice"]}'])

    def fake_chat(prompt: str, **_kwargs: object) -> str:
        _ = prompt
        start_times.append(clock.monotonic())
        clock.sleep(0.01)
        response = next(responses)
        if isinstance(response, Exception):
            raise response
        return response

    with (
        patch("txt_process.core.extraction.split_into_chunks", return_value=chunks),
        patch("txt_process.core.extraction.LLMClient") as mock_llm,
    ):
        mock_llm.return_value.chat.side_effect = fake_chat
        result = run_extraction(
            text="\n\n".join(chunks),
            config=config,
            api_key="ollama",
            callbacks=callbacks,
            monotonic_clock=clock.monotonic,
            sleeper=clock.sleep,
        )

    assert len(start_times) == 2
    assert start_times[1] - start_times[0] >= interval - 1e-6
    assert result.errors == ["Chunk 1: transient"]
    assert [name for name, _ in result.name_pairs] == ["Alice"]


def test_large_doc_uses_phased_sampling_for_low_hit_chunks():
    chunks = [
        "Alice appears in chunk 0",
        "Bob appears in chunk 1",
        "Alice and Bob appear in chunk 2",
        "Alice Bob Carol in chunk 3",  # skipped, 2 hits, no phase 3
        "No known names in chunk 4",  # skipped, 0 hits, phase 3
        "Alice and Bob appear in chunk 5",
        "Alice only in chunk 6",  # skipped, 1 hit, phase 3
        "Alice Bob in chunk 7",  # skipped, 2 hits, no phase 3
    ]
    config = Config(
        base_url="http://localhost:11434",
        model="mock",
        prompt_template="{chunk_text}",
        request_interval_seconds=0.0,
        begin_scan_chunks=2,
        scan_interval=3,
    )
    callbacks = _CallbackRecorder()
    called_prompts: list[str] = []
    names_by_chunk = {
        chunks[0]: ["Alice"],
        chunks[1]: ["Bob"],
        chunks[2]: ["Alice", "Bob"],
        chunks[3]: ["Alice", "Bob", "Carol"],
        chunks[4]: ["Carol"],
        chunks[5]: ["Alice", "Bob"],
        chunks[6]: ["Alice", "Eve"],
        chunks[7]: ["Alice", "Bob"],
    }

    def fake_chat(prompt: str, **_kwargs: object) -> str:
        called_prompts.append(prompt)
        return json.dumps({"names": names_by_chunk[prompt]}, ensure_ascii=False)

    with (
        patch("txt_process.core.extraction.split_into_chunks", return_value=chunks),
        patch("txt_process.core.extraction.LLMClient") as mock_llm,
    ):
        mock_llm.return_value.chat.side_effect = fake_chat
        result = run_extraction(
            text="\n\n".join(chunks),
            config=config,
            api_key="ollama",
            callbacks=callbacks,
        )

    assert called_prompts == [chunks[0], chunks[1], chunks[2], chunks[5], chunks[4], chunks[6]]
    names = [name for name, _ in result.name_pairs]
    assert "Eve" in names


def test_invalid_json_triggers_single_corrective_retry():
    config = Config(
        base_url="http://localhost:11434",
        model="mock",
        prompt_template="{chunk_text}",
        request_interval_seconds=0.2,
    )
    chunks = ["chunk-one"]
    callbacks = _CallbackRecorder()
    clock = _FakeClock()
    prompts: list[str] = []
    start_times: list[float] = []
    responses = iter(["not-json", '{"names": ["Alice"]}'])

    def fake_chat(prompt: str, **_kwargs: object) -> str:
        prompts.append(prompt)
        start_times.append(clock.monotonic())
        return next(responses)

    with (
        patch("txt_process.core.extraction.split_into_chunks", return_value=chunks),
        patch("txt_process.core.extraction.LLMClient") as mock_llm,
    ):
        mock_llm.return_value.chat.side_effect = fake_chat
        result = run_extraction(
            text="chunk-one",
            config=config,
            api_key="ollama",
            callbacks=callbacks,
            monotonic_clock=clock.monotonic,
            sleeper=clock.sleep,
        )

    assert len(prompts) == 2
    assert "Respond with ONLY strict JSON" in prompts[1]
    assert len(start_times) == 2
    assert start_times[1] - start_times[0] >= 0.2 - 1e-6
    assert result.errors == []
    assert [name for name, _ in result.name_pairs] == ["Alice"]


def test_second_parse_failure_records_chunk_error_and_continues():
    config = Config(
        base_url="http://localhost:11434",
        model="mock",
        prompt_template="{chunk_text}",
        request_interval_seconds=0.0,
    )
    chunks = ["bad chunk", "good chunk"]
    callbacks = _CallbackRecorder()
    responses = iter(["bad json", "still bad", '{"names": ["Bob"]}'])

    def fake_chat(prompt: str, **_kwargs: object) -> str:
        _ = prompt
        return next(responses)

    with (
        patch("txt_process.core.extraction.split_into_chunks", return_value=chunks),
        patch("txt_process.core.extraction.LLMClient") as mock_llm,
    ):
        mock_llm.return_value.chat.side_effect = fake_chat
        result = run_extraction(
            text="\n\n".join(chunks),
            config=config,
            api_key="ollama",
            callbacks=callbacks,
        )

    assert len(result.errors) == 1
    assert callbacks.chunk_error_payloads
    assert callbacks.chunk_error_payloads[0][0] == 0
    assert [name for name, _ in result.name_pairs] == ["Bob"]


def test_rate_limit_error_waits_then_continues():
    clock = _FakeClock()
    callbacks = _CallbackRecorder()
    config = Config(
        base_url="http://localhost:11434",
        model="mock",
        prompt_template="{chunk_text}",
        request_interval_seconds=0.0,
    )
    chunks = ["rate-limited", "normal"]
    reset_ms = str((100 + 30) * 1000)
    error_text = f"error code: 429 ... X-RateLimit-Reset': '{reset_ms}'"
    responses = iter([RuntimeError(error_text), '{"names": ["Alice"]}'])

    def fake_chat(prompt: str, **_kwargs: object) -> str:
        response = next(responses)
        if isinstance(response, Exception):
            raise response
        return response

    with (
        patch("txt_process.core.extraction.time.time", return_value=100.0),
        patch("txt_process.core.extraction.split_into_chunks", return_value=chunks),
        patch("txt_process.core.extraction.LLMClient") as mock_llm,
    ):
        mock_llm.return_value.chat.side_effect = fake_chat
        result = run_extraction(
            text="\n\n".join(chunks),
            config=config,
            api_key="ollama",
            callbacks=callbacks,
            monotonic_clock=clock.monotonic,
            sleeper=clock.sleep,
        )

    assert sum(clock.sleeps) >= 29.9
    assert any("rate limit" in log.lower() for log in callbacks.logs)
    assert len(result.errors) == 1
    assert [name for name, _ in result.name_pairs] == ["Alice"]
    assert isinstance(result, ExtractionResult)
