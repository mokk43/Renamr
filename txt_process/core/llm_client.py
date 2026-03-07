"""OpenAI-compatible LLM client wrapper."""

from __future__ import annotations

import json
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx
from openai import OpenAI

# #region agent log
_DEBUG_LOG_PATH = Path(__file__).resolve().parents[2] / ".cursor" / "debug.log"
def _dbg(loc, msg, data, hyp):
    try:
        _DEBUG_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _DEBUG_LOG_PATH.open("a", encoding="utf-8") as log_file:
            log_file.write(
                json.dumps(
                    {
                        "location": loc,
                        "message": msg,
                        "data": data,
                        "hypothesisId": hyp,
                        "timestamp": int(time.time() * 1000),
                        "sessionId": "debug-session",
                    }
                )
                + "\n"
            )
    except OSError:
        pass
# #endregion


def is_ollama_base_url(base_url: str) -> bool:
    """Return True when endpoint points to Ollama's default API port."""
    if not base_url:
        return False

    parsed = urlparse(base_url if "://" in base_url else f"http://{base_url}")
    try:
        port = parsed.port
    except ValueError:
        return False

    return port == 11434


def _ollama_root_url(base_url: str) -> str:
    """Normalize any Ollama URL variant to scheme://host:port."""
    parsed = urlparse(base_url if "://" in base_url else f"http://{base_url}")
    if not parsed.netloc:
        raise ValueError(f"Invalid Ollama base URL: {base_url}")
    return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")


class _OpenAIChatProtocol:
    """OpenAI-compatible chat.completions protocol."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        temperature: float,
        timeout: float,
        max_tokens: int | None,
    ) -> None:
        if not api_key:
            api_key = "ollama"

        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.client = OpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=timeout,
        )

    def chat(self, prompt: str) -> str:
        kwargs = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.temperature,
            "extra_body": {"think": False},
        }
        if self.max_tokens is not None:
            kwargs["max_tokens"] = self.max_tokens

        request_started = time.monotonic()
        request_id = int(time.time() * 1000)
        _dbg(
            "llm_client.py:openai_request",
            "calling openai-compatible chat.completions.create",
            {
                "request_id": request_id,
                "model": self.model,
                "temperature": self.temperature,
                "max_tokens": self.max_tokens,
                "prompt_len": len(prompt),
                "prompt_preview": prompt[:200],
                "extra_body": kwargs.get("extra_body"),
            },
            "LOG",
        )
        try:
            response = self.client.chat.completions.create(**kwargs)
            output = ""
            if response.choices and response.choices[0].message.content:
                output = response.choices[0].message.content
            _dbg(
                "llm_client.py:openai_response",
                "openai-compatible response received",
                {
                    "request_id": request_id,
                    "elapsed_ms": int((time.monotonic() - request_started) * 1000),
                    "response_len": len(output),
                    "response_preview": output[:200],
                    "has_choices": bool(response.choices),
                },
                "LOG",
            )
            return output
        except Exception as e:
            _dbg(
                "llm_client.py:openai_error",
                "openai-compatible request failed",
                {
                    "request_id": request_id,
                    "elapsed_ms": int((time.monotonic() - request_started) * 1000),
                    "error_type": type(e).__name__,
                    "error_msg": str(e),
                },
                "LOG",
            )
            raise


class _OllamaChatProtocol:
    """Ollama native /api/chat protocol with thinking disabled."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        temperature: float,
        timeout: float,
        max_tokens: int | None,
    ) -> None:
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.client = httpx.Client(base_url=_ollama_root_url(base_url), timeout=timeout)

    def chat(self, prompt: str) -> str:
        payload: dict[str, object] = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "think": False,
        }
        options: dict[str, object] = {"temperature": self.temperature}
        if self.max_tokens is not None:
            options["num_predict"] = self.max_tokens
        payload["options"] = options

        request_started = time.monotonic()
        request_id = int(time.time() * 1000)
        _dbg(
            "llm_client.py:ollama_request",
            "calling ollama /api/chat",
            {
                "request_id": request_id,
                "model": self.model,
                "temperature": self.temperature,
                "max_tokens": self.max_tokens,
                "prompt_len": len(prompt),
                "prompt_preview": prompt[:200],
                "payload": payload,
            },
            "LOG",
        )
        try:
            response = self.client.post("/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
            output = ""
            if isinstance(data, dict):
                message = data.get("message")
                if isinstance(message, dict):
                    content = message.get("content")
                    if isinstance(content, str):
                        output = content
            _dbg(
                "llm_client.py:ollama_response",
                "ollama response received",
                {
                    "request_id": request_id,
                    "elapsed_ms": int((time.monotonic() - request_started) * 1000),
                    "response_len": len(output),
                    "response_preview": output[:200],
                    "has_content": bool(output),
                },
                "LOG",
            )
            return output
        except Exception as e:
            _dbg(
                "llm_client.py:ollama_error",
                "ollama request failed",
                {
                    "request_id": request_id,
                    "elapsed_ms": int((time.monotonic() - request_started) * 1000),
                    "error_type": type(e).__name__,
                    "error_msg": str(e),
                },
                "LOG",
            )
            raise


class LLMClient:
    """Wrapper for protocol-routed LLM API calls."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        temperature: float = 0.1,
        timeout: float = 60.0,
        max_tokens: int | None = None,
    ) -> None:
        """
        Initialize the LLM client.

        Args:
            base_url: API base URL (e.g., https://api.openai.com/v1).
            api_key: API key for authentication.
            model: Model name to use.
            temperature: Sampling temperature (0-2).
            timeout: Request timeout in seconds.
            max_tokens: Maximum tokens in response (optional).
        """
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.uses_ollama_protocol = is_ollama_base_url(base_url)
        if self.uses_ollama_protocol:
            self.protocol = _OllamaChatProtocol(
                base_url=base_url,
                api_key=api_key,
                model=model,
                temperature=temperature,
                timeout=timeout,
                max_tokens=max_tokens,
            )
        else:
            self.protocol = _OpenAIChatProtocol(
                base_url=base_url,
                api_key=api_key,
                model=model,
                temperature=temperature,
                timeout=timeout,
                max_tokens=max_tokens,
            )
        # #region agent log
        _dbg(
            "llm_client.py:init",
            "client initialized",
            {
                "base_url": base_url,
                "model": self.model,
                "uses_ollama_protocol": self.uses_ollama_protocol,
            },
            "H1,H2",
        )
        # #endregion

    def chat(self, prompt: str) -> str:
        """
        Send a chat completion request.

        Args:
            prompt: The user prompt to send.

        Returns:
            The assistant's response text.

        Raises:
            Exception: If the API call fails.
        """
        return self.protocol.chat(prompt)
