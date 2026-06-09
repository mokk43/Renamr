"""Compatibility tests for worker adapters and cadence plumbing."""

from __future__ import annotations

import inspect
from unittest.mock import patch

from txt_process.core.config import Config
from txt_process.core.extraction import ExtractionCancelled, ExtractionResult
from txt_process.ui.workers import ExtractNamesWorker


def test_extraction_wait_uses_monotonic_clock():
    source = inspect.getsource(
        __import__(
            "txt_process.core.extraction", fromlist=["_wait_with_cadence"]
        )._wait_with_cadence
    )
    assert "monotonic_clock" in source


def test_worker_respects_interval_config():
    config = Config(request_interval_seconds=3.0)
    worker = ExtractNamesWorker(text="test", config=config, api_key="test-key")
    assert worker.config.request_interval_seconds == 3.0


def test_worker_forwards_finished_payload_from_core_extraction():
    config = Config()
    worker = ExtractNamesWorker(text="hello", config=config, api_key="key")
    finished_payload: list[tuple[list[str], dict[str, int]]] = []
    worker.finished.connect(lambda names, counts: finished_payload.append((names, counts)))

    with patch("txt_process.ui.workers.extract_names") as extract:
        extract.return_value = ExtractionResult(
            name_pairs=[("Alice", ""), ("Bob", "")],
            counts={"Alice": 2, "Bob": 1},
            errors=[],
        )
        worker.run()

    assert finished_payload == [(["Alice", "Bob"], {"Alice": 2, "Bob": 1})]


def test_worker_reports_all_chunks_failed_error():
    config = Config()
    worker = ExtractNamesWorker(text="hello", config=config, api_key="key")
    errors: list[tuple[str, str]] = []
    worker.error.connect(lambda message, details: errors.append((message, details)))

    with patch("txt_process.ui.workers.extract_names") as extract:
        extract.return_value = ExtractionResult(name_pairs=[], counts={}, errors=["Chunk 1: boom"])
        worker.run()

    assert errors == [("All 1 chunk(s) failed", "Chunk 1: boom")]


def test_worker_propagates_cancelled_error():
    config = Config()
    worker = ExtractNamesWorker(text="hello", config=config, api_key="key")
    errors: list[tuple[str, str]] = []
    worker.error.connect(lambda message, details: errors.append((message, details)))

    with patch("txt_process.ui.workers.extract_names", side_effect=ExtractionCancelled()):
        worker.run()

    assert errors == [("Cancelled", "Extraction was cancelled by user.")]
