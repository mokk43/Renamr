"""Tests for LLM request cadence and sampled extraction behavior."""

import json
import time
from unittest.mock import MagicMock, patch

import pytest


class TestCadenceEnforcement:
    """Tests for enforcing minimum interval between LLM requests."""

    def test_interval_enforcement_concept(self):
        """
        Verify the concept of interval enforcement.

        The actual enforcement happens in the worker, but we test the timing logic here.
        """
        # Simulate the timing logic used in the worker
        interval = 2.0
        request_times: list[float] = []

        def make_request():
            """Simulate making a request with interval enforcement."""
            if request_times:
                elapsed = time.monotonic() - request_times[-1]
                if elapsed < interval:
                    wait_time = interval - elapsed
                    time.sleep(wait_time)
            request_times.append(time.monotonic())

        # Make 3 requests
        for _ in range(3):
            make_request()

        # Verify intervals
        for i in range(1, len(request_times)):
            actual_interval = request_times[i] - request_times[i - 1]
            assert actual_interval >= interval - 0.1  # Allow small timing variance

    def test_worker_uses_monotonic_clock(self):
        """Verify worker uses monotonic clock for timing."""
        # Import the worker to check its implementation
        from txt_process.ui.workers import ExtractNamesWorker

        # Check that time.monotonic is used in the source
        import inspect

        source = inspect.getsource(ExtractNamesWorker._wait_interval)
        assert "time.monotonic" in source

    def test_worker_respects_interval_config(self):
        """Verify worker uses configured interval."""
        from txt_process.ui.workers import ExtractNamesWorker
        from txt_process.core.config import Config

        config = Config(request_interval_seconds=3.0)

        # Create worker (don't run it)
        worker = ExtractNamesWorker(
            text="test",
            config=config,
            api_key="test-key",
        )

        # Verify it uses the config value
        assert worker.config.request_interval_seconds == 3.0


class TestSerialCadence:
    """End-to-end assertion: worker issues serial calls ≥ interval apart."""

    def test_serial_calls_respect_interval_and_no_overlap(self):
        """LLM calls must be serial (no overlap) and ≥ interval apart."""
        import threading

        from txt_process.core.config import Config
        from txt_process.ui.workers import ExtractNamesWorker

        interval = 0.2  # keep test fast while still enforcing cadence
        config = Config(
            base_url="http://localhost:11434",
            model="mock",
            prompt_template="{chunk_text}",
            request_interval_seconds=interval,
            begin_scan_chunks=10,  # force serial path
        )

        chunks = ["chunk-0", "chunk-1", "chunk-2"]
        start_times: list[float] = []
        end_times: list[float] = []
        in_flight = 0
        max_in_flight = 0
        lock = threading.Lock()

        def fake_chat(prompt: str, **_kwargs: object) -> str:
            nonlocal in_flight, max_in_flight
            with lock:
                in_flight += 1
                max_in_flight = max(max_in_flight, in_flight)
                start_times.append(time.monotonic())
            # Simulate some work; any overlap would be detectable here.
            time.sleep(0.05)
            with lock:
                end_times.append(time.monotonic())
                in_flight -= 1
            return '{"names": []}'

        worker = ExtractNamesWorker(text="\n\n".join(chunks), config=config, api_key="ollama")
        with patch("txt_process.ui.workers.split_into_chunks", return_value=chunks):
            with patch("txt_process.ui.workers.LLMClient") as mock_llm:
                mock_llm.return_value.chat.side_effect = fake_chat
                worker.run()

        assert len(start_times) == len(chunks)
        assert max_in_flight == 1, "LLM calls must be serial (no concurrency)"
        for i in range(1, len(start_times)):
            gap = start_times[i] - start_times[i - 1]
            assert gap + 0.01 >= interval, (
                f"Request {i} started {gap:.3f}s after prior start; "
                f"expected ≥ {interval}s"
            )


class TestLLMClientMocking:
    """Tests for LLM client with mocked responses."""

    def test_mock_llm_response(self):
        """Test extracting names with mocked LLM."""
        from txt_process.core.llm_client import LLMClient
        from txt_process.core.name_extract import extract_names_from_response

        # Mock the OpenAI client
        with patch("txt_process.core.llm_client.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_openai.return_value = mock_client

            # Set up mock response
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = '{"names": ["张三", "李四"]}'
            mock_client.chat.completions.create.return_value = mock_response

            # Create client and make request
            client = LLMClient(
                base_url="https://api.example.com/v1",
                api_key="test-key",
                model="test-model",
            )
            response = client.chat("Extract names from: ...")

            # Verify response
            names = extract_names_from_response(response)
            assert names == ["张三", "李四"]

    def test_mock_llm_empty_response(self):
        """Test handling empty LLM response."""
        from txt_process.core.llm_client import LLMClient

        with patch("txt_process.core.llm_client.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_openai.return_value = mock_client

            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = ""
            mock_client.chat.completions.create.return_value = mock_response

            client = LLMClient(
                base_url="https://api.example.com/v1",
                api_key="test-key",
                model="test-model",
            )
            response = client.chat("Extract names from: ...")

            assert response == ""

    def test_mock_llm_no_choices(self):
        """Test handling response with no choices."""
        from txt_process.core.llm_client import LLMClient

        with patch("txt_process.core.llm_client.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_openai.return_value = mock_client

            mock_response = MagicMock()
            mock_response.choices = []
            mock_client.chat.completions.create.return_value = mock_response

            client = LLMClient(
                base_url="https://api.example.com/v1",
                api_key="test-key",
                model="test-model",
            )
            response = client.chat("Extract names from: ...")

            assert response == ""


class TestNoRetryBehavior:
    """Tests that extraction errors do not trigger retry calls."""

    def test_worker_does_not_retry_after_chunk_failure(self):
        """A failed chunk should continue without a second model call."""
        from txt_process.core.config import Config
        from txt_process.ui.workers import ExtractNamesWorker

        config = Config(
            base_url="http://localhost:11434",
            model="qwen3.5:0.8b",
            prompt_template="{chunk_text}",
            request_interval_seconds=0.0,
        )

        worker = ExtractNamesWorker(text="hello world", config=config, api_key="ollama")
        error_payload: list[tuple[str, str]] = []
        chunk_errors: list[tuple[int, str]] = []
        worker.error.connect(lambda message, details: error_payload.append((message, details)))
        worker.chunk_error.connect(lambda idx, msg: chunk_errors.append((idx, msg)))

        with patch("txt_process.ui.workers.split_into_chunks", return_value=["chunk-1"]):
            with patch("txt_process.ui.workers.LLMClient") as mock_llm:
                mock_llm.return_value.chat.side_effect = RuntimeError("simulated failure")
                worker.run()

        assert mock_llm.return_value.chat.call_count == 1
        assert chunk_errors == [(0, "simulated failure")]
        assert len(error_payload) == 1
        assert error_payload[0][0] == "All 1 chunk(s) failed"


class TestSampledExtractionBehavior:
    """Tests for large-document phased extraction."""

    def test_worker_uses_phased_sampling_for_large_documents(self):
        """Large docs should use phase 1 sampling plus phase 3 targeted fill."""
        from txt_process.core.config import Config
        from txt_process.ui.workers import ExtractNamesWorker

        chunks = [
            "Alice appears in chunk 0",
            "Bob appears in chunk 1",
            "Alice and Bob appear in chunk 2",
            "Alice Bob Carol in chunk 3",  # skipped: hit_count=2 -> no phase 3
            "No known names in chunk 4",  # skipped: hit_count=0 -> phase 3
            "Alice and Bob appear in chunk 5",
            "Alice only in chunk 6",  # skipped: hit_count=1 -> phase 3
            "Alice Bob in chunk 7",  # skipped: hit_count=2 -> no phase 3
        ]
        config = Config(
            base_url="http://localhost:11434",
            model="qwen3.5:0.8b",
            prompt_template="{chunk_text}",
            request_interval_seconds=0.0,
            begin_scan_chunks=2,
            scan_interval=3,
        )

        worker = ExtractNamesWorker(text="\n\n".join(chunks), config=config, api_key="ollama")
        finished_payload: list[tuple[list[str], dict[str, int]]] = []
        worker.finished.connect(lambda names, counts: finished_payload.append((names, counts)))

        names_by_chunk: dict[str, list[str]] = {
            chunks[0]: ["Alice"],
            chunks[1]: ["Bob"],
            chunks[2]: ["Alice", "Bob"],
            chunks[3]: ["Alice", "Bob", "Carol"],
            chunks[4]: ["Carol"],
            chunks[5]: ["Alice", "Bob"],
            chunks[6]: ["Alice", "Eve"],
            chunks[7]: ["Alice", "Bob"],
        }

        called_prompts: list[str] = []

        def fake_chat(prompt: str, **_kwargs: object) -> str:
            called_prompts.append(prompt)
            return json.dumps({"names": names_by_chunk[prompt]}, ensure_ascii=False)

        with patch("txt_process.ui.workers.split_into_chunks", return_value=chunks):
            with patch("txt_process.ui.workers.LLMClient") as mock_llm:
                mock_llm.return_value.chat.side_effect = fake_chat
                worker.run()

        # Phase 1 indices: [0, 1, 2, 5], Phase 3 candidates: [4, 6]
        assert called_prompts == [
            chunks[0],
            chunks[1],
            chunks[2],
            chunks[5],
            chunks[4],
            chunks[6],
        ]

        assert len(finished_payload) == 1
        names, _counts = finished_payload[0]
        assert "Eve" in names
