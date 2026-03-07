"""Tests for LLM client protocol routing and payloads."""

from unittest.mock import MagicMock, patch

from txt_process.core.llm_client import LLMClient, is_ollama_base_url


class TestOllamaEndpointDetection:
    """Tests for Ollama endpoint auto-detection."""

    def test_detects_ollama_port_11434(self):
        assert is_ollama_base_url("http://localhost:11434")
        assert is_ollama_base_url("http://localhost:11434/v1")
        assert is_ollama_base_url("http://127.0.0.1:11434/v1/")

    def test_rejects_non_ollama_endpoints(self):
        assert not is_ollama_base_url("https://api.openai.com/v1")
        assert not is_ollama_base_url("http://localhost:11435/v1")
        assert not is_ollama_base_url("http://localhost")


class TestLLMProtocolRouting:
    """Tests protocol selection between OpenAI-compatible and Ollama-native APIs."""

    def test_uses_ollama_native_chat_api_for_port_11434(self):
        with patch("txt_process.core.llm_client.OpenAI") as mock_openai:
            with patch("txt_process.core.llm_client.httpx.Client") as mock_httpx_client:
                mock_client = MagicMock()
                mock_httpx_client.return_value = mock_client

                mock_response = MagicMock()
                mock_response.raise_for_status.return_value = None
                mock_response.json.return_value = {
                    "message": {"role": "assistant", "content": "result-text"}
                }
                mock_client.post.return_value = mock_response

                client = LLMClient(
                    base_url="http://localhost:11434/v1",
                    api_key="",
                    model="llama3.1",
                    temperature=0.2,
                    max_tokens=128,
                )
                output = client.chat("hello world")

                assert output == "result-text"
                mock_openai.assert_not_called()
                mock_client.post.assert_called_once()
                call_args = mock_client.post.call_args
                assert call_args.args[0] == "/api/chat"
                payload = call_args.kwargs["json"]
                assert payload["model"] == "llama3.1"
                assert payload["messages"] == [{"role": "user", "content": "hello world"}]
                assert payload["stream"] is False
                assert payload["think"] is False
                assert payload["options"]["temperature"] == 0.2
                assert payload["options"]["num_predict"] == 128

    def test_uses_openai_compatible_protocol_for_other_endpoints(self):
        with patch("txt_process.core.llm_client.OpenAI") as mock_openai:
            mock_openai_instance = MagicMock()
            mock_openai.return_value = mock_openai_instance

            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = "openai-result"
            mock_openai_instance.chat.completions.create.return_value = mock_response

            client = LLMClient(
                base_url="https://api.openai.com/v1",
                api_key="sk-test",
                model="gpt-4o-mini",
            )
            output = client.chat("hello")

            assert output == "openai-result"
            mock_openai.assert_called_once()
            mock_openai_instance.chat.completions.create.assert_called_once()
            kwargs = mock_openai_instance.chat.completions.create.call_args.kwargs
            assert kwargs["extra_body"]["think"] is False
