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
    """Worker that extracts names from text using LLM."""

    # Signals
    progress = Signal(int, int, str)  # current, total, status
    chunk_names = Signal(int, list)  # chunk_index, names
    chunk_error = Signal(int, str)  # chunk_index, error_message
    finished = Signal(list, dict)  # deduplicated names, occurrence counts
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
                self.finished.emit([], {})
                return

            # Initialize LLM client
            client = LLMClient(
                base_url=self.config.base_url,
                api_key=self.api_key,
                model=self.config.model,
                temperature=self.config.temperature,
                timeout=self.config.timeout_seconds,
                max_tokens=self.config.max_tokens,
            )

            all_names: list[str] = []
            failed_chunks: list[tuple[int, str]] = []
            last_request_start = 0.0
            interval = self.config.request_interval_seconds

            for i, chunk in enumerate(chunks):
                if self._cancelled:
                    self.error.emit("Cancelled", "Extraction was cancelled by user.")
                    return

                # Enforce minimum interval between request starts.
                elapsed = time.monotonic() - last_request_start
                if last_request_start > 0 and elapsed < interval:
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
                prompt = template.replace("{chunk_text}", chunk)

                try:
                    last_request_start = time.monotonic()
                    response = client.chat(prompt)
                    names = extract_names_from_response(response)
                    all_names.extend(names)
                    self.chunk_names.emit(i, names)
                except Exception as e:
                    if _is_rate_limit_error(e):
                        wait_info = _extract_rate_limit_wait(str(e))
                        message = "Rate limit exceeded. Please wait and retry."
                        details = wait_info.get("message") or "Provider rate limit."
                        self.error.emit(message, details)
                        return

                    failed_chunks.append((i, str(e)))
                    self.chunk_error.emit(i, str(e))
                    self.progress.emit(i, total_chunks, f"Chunk {i+1} failed, continuing...")

                self.progress.emit(i + 1, total_chunks, "Processing...")

            if not all_names and failed_chunks:
                _, first_error = failed_chunks[0]
                self.error.emit(
                    f"All {len(failed_chunks)} chunk(s) failed",
                    first_error,
                )
                return

            # Deduplicate and finish
            self.progress.emit(total_chunks, total_chunks, "Deduplicating...")
            deduped = dedupe_names(all_names)
            counts = count_name_occurrences(self.text, deduped)
            self.finished.emit(deduped, counts)

        except Exception as e:
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
