"""OpenAI-compatible LLM client wrapper."""

from __future__ import annotations

import json
import time

from openai import OpenAI

# #region agent log
_DEBUG_LOG_PATH = "/Users/gary/git/txt-process/.cursor/debug.log"
def _dbg(loc, msg, data, hyp):
    open(_DEBUG_LOG_PATH, "a").write(json.dumps({"location": loc, "message": msg, "data": data, "hypothesisId": hyp, "timestamp": int(time.time()*1000), "sessionId": "debug-session"}) + "\n")
# #endregion


class LLMClient:
    """Wrapper for OpenAI-compatible API calls."""

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

        if not api_key:
            api_key = "ollama"

        self.client = OpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=timeout,
        )
        # #region agent log
        _dbg("llm_client.py:init", "client initialized", {"base_url": base_url, "model": self.model}, "H1,H2")
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
        kwargs = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.temperature,
            "extra_body": {"think": False}
        }

        if self.max_tokens is not None:
            kwargs["max_tokens"] = self.max_tokens

        response = self.client.chat.completions.create(**kwargs)

        if response.choices and response.choices[0].message.content:
            return response.choices[0].message.content

        return ""
