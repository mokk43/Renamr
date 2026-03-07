"""Background worker threads for long-running operations."""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Signal

from txt_process.core.chunking import split_into_chunks
from txt_process.core.llm_client import LLMClient
from txt_process.core.name_extract import extract_names_from_response, dedupe_names

if TYPE_CHECKING:
    from txt_process.core.config import Config

# #region agent log
_DEBUG_LOG_PATH = "/Users/gary/git/Renamr/.cursor/debug.log"
def _dbg(loc, msg, data, hyp):
    open(_DEBUG_LOG_PATH, "a").write(json.dumps({"location": loc, "message": msg, "data": data, "hypothesisId": hyp, "timestamp": int(time.time()*1000), "sessionId": "debug-session"}) + "\n")
# #endregion


class ExtractNamesWorker(QObject):
    """Worker that extracts names from text using LLM."""

    # Signals
    progress = Signal(int, int, str)  # current, total, status
    chunk_names = Signal(int, list)  # chunk_index, names
    finished = Signal(list)  # deduplicated names
    error = Signal(str, str)  # message, details

    def __init__(self, text: str, config: "Config", api_key: str) -> None:
        super().__init__()
        self.text = text
        self.config = config
        self.api_key = api_key
        self._cancelled = False

    def cancel(self) -> None:
        """Request cancellation of the extraction."""
        self._cancelled = True

    def run(self) -> None:
        """Execute the extraction process."""
        try:
            # Split text into chunks
            self.progress.emit(0, 0, "Splitting text into chunks...")
            chunks = split_into_chunks(self.text, self.config.chunk_max_bytes)
            total_chunks = len(chunks)

            if total_chunks == 0:
                self.finished.emit([])
                return

            # Initialize LLM client
            # #region agent log
            _dbg(
                "workers.py:llm_config",
                "LLM config",
                {"base_url": self.config.base_url, "model": self.config.model},
                "H1,H2,H3",
            )
            # #endregion
            client = LLMClient(
                base_url=self.config.base_url,
                api_key=self.api_key,
                model=self.config.model,
                temperature=self.config.temperature,
                timeout=self.config.timeout_seconds,
                max_tokens=self.config.max_tokens,
            )

            all_names: list[str] = []
            last_response_time = 0.0
            interval = self.config.request_interval_seconds

            for i, chunk in enumerate(chunks):
                if self._cancelled:
                    self.error.emit("Cancelled", "Extraction was cancelled by user.")
                    return

                # Enforce minimum interval between requests (after previous response)
                elapsed = time.monotonic() - last_response_time
                if last_response_time > 0 and elapsed < interval:
                    wait_time = interval - elapsed
                    self.progress.emit(i, total_chunks, f"Waiting {wait_time:.1f}s...")
                    
                    # Check for cancellation during wait
                    wait_start = time.monotonic()
                    while time.monotonic() - wait_start < wait_time:
                        if self._cancelled:
                            self.error.emit("Cancelled", "Extraction was cancelled by user.")
                            return
                        time.sleep(0.1)

                # Call LLM
                self.progress.emit(i, total_chunks, "Calling model...")
                template = self.config.prompt_template
                # #region agent log
                _dbg("workers.py:prompt_template", "template loaded", {"template_len": len(template), "has_placeholder": "{chunk_text}" in template}, "H4")
                # #endregion
                prompt = template.replace("{chunk_text}", chunk)
                # #region agent log
                _dbg("workers.py:prompt", "prompt formatted", {"prompt_len": len(prompt), "chunk_len": len(chunk)}, "H4")
                # #endregion

                try:
                    response = client.chat(prompt)
                    # #region agent log
                    _dbg("workers.py:llm_response", "LLM responded", {"response_len": len(response) if response else 0, "response_preview": response[:200] if response else "NONE"}, "H3")
                    # #endregion
                    names = extract_names_from_response(response)
                    all_names.extend(names)
                    self.chunk_names.emit(i, names)
                except Exception as e:
                    # #region agent log
                    _dbg("workers.py:extract_error", "extraction failed", {"error_type": type(e).__name__, "error_msg": str(e)}, "H1,H2")
                    # #endregion
                    if _is_rate_limit_error(e):
                        wait_info = _extract_rate_limit_wait(str(e))
                        # #region agent log
                        _dbg("workers.py:rate_limit", "rate limit detected", {"wait_seconds": wait_info.get("wait_seconds"), "has_reset": wait_info.get("has_reset")}, "H1")
                        # #endregion
                        message = "Rate limit exceeded. Please wait and retry."
                        details = wait_info.get("message") or "Provider rate limit."
                        self.error.emit(message, details)
                        return

                    # Try one corrective retry
                    self.progress.emit(i, total_chunks, "Retrying with correction...")
                    time.sleep(interval)
                    try:
                        corrective_prompt = (
                            f"Your previous response was not valid JSON. "
                            f"Please output ONLY a JSON object in this format: "
                            f'{{\"names\": [\"Name1\", \"Name2\"]}}\n\n'
                            f"Original request:\n{prompt}"
                        )
                        response = client.chat(corrective_prompt)
                        names = extract_names_from_response(response)
                        all_names.extend(names)
                        self.chunk_names.emit(i, names)
                    except Exception as retry_error:
                        # Log but continue with other chunks
                        self.progress.emit(
                            i, total_chunks, f"Chunk {i+1} failed, continuing..."
                        )
                finally:
                    # Mark that the previous request has returned (success or error)
                    last_response_time = time.monotonic()

                self.progress.emit(i + 1, total_chunks, "Processing...")

            # Deduplicate and finish
            self.progress.emit(total_chunks, total_chunks, "Deduplicating...")
            deduped = dedupe_names(all_names)
            self.finished.emit(deduped)

        except Exception as e:
            # #region agent log
            _dbg("workers.py:fatal_error", "fatal extraction error", {"error_type": type(e).__name__, "error_msg": str(e)}, "H5")
            # #endregion
            self.error.emit("Extraction failed", str(e))


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
