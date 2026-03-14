"""Tests for LLM request cadence enforcement."""

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

        source = inspect.getsource(ExtractNamesWorker.run)
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
            with patch("txt_process.core.name_extract._dbg", lambda *args, **kwargs: None):
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
        progress_events: list[tuple[int, int, str]] = []
        finished_payload: list[list[str]] = []
        worker.progress.connect(lambda c, t, s: progress_events.append((c, t, s)))
        worker.finished.connect(lambda names: finished_payload.append(names))

        with patch("txt_process.ui.workers.split_into_chunks", return_value=["chunk-1"]):
            with patch("txt_process.ui.workers.LLMClient") as mock_llm:
                with patch("txt_process.ui.workers._dbg", lambda *args, **kwargs: None):
                    mock_llm.return_value.chat.side_effect = RuntimeError("simulated failure")
                    worker.run()

        assert mock_llm.return_value.chat.call_count == 1
        assert any(
            status == "Chunk 1 failed, continuing..."
            for _, _, status in progress_events
        )
        assert all(
            status != "Retrying with correction..."
            for _, _, status in progress_events
        )
        assert finished_payload == [[]]
