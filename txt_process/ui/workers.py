"""Background worker threads for long-running operations."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Signal

from txt_process.core.api import (
    ExtractionCancelled,
    ProgressEvent,
    extract_names,
    load_document,
)
from txt_process.core.document import Document

if TYPE_CHECKING:
    from txt_process.core.config import Config


class LoadDocumentWorker(QObject):
    """Worker that loads a :class:`Document` off the GUI thread."""

    progress = Signal(int, int, str)  # current, total, status
    finished = Signal(object)  # Document instance
    error = Signal(str, str, str)  # kind, message, details

    def __init__(self, path: Path) -> None:
        super().__init__()
        self.path = path

    def run(self) -> None:
        """Load the document, emitting progress + finished signals."""
        try:
            self.progress.emit(0, 1, f"Loading {self.path.name}...")
            doc: Document = load_document(self.path)
            self.progress.emit(1, 1, "Done")
            self.finished.emit(doc)
        except Exception as exc:  # noqa: BLE001 - surface everything to UI
            self.error.emit(
                type(exc).__name__,
                str(exc) or "Failed to load document.",
                repr(exc),
            )


class ExtractNamesWorker(QObject):
    """Qt adapter around shared core extraction orchestration."""

    progress = Signal(int, int, str)  # current, total, status
    chunk_names = Signal(int, list)  # chunk_index, names
    chunk_error = Signal(int, str)  # chunk_index, error_message
    finished = Signal(list, dict)  # deduplicated names, occurrence counts
    error = Signal(str, str)  # message, details
    log = Signal(str)  # free-form log line

    def __init__(self, text: str, config: Config, api_key: str) -> None:
        super().__init__()
        self.text = text
        self.config = config
        self.api_key = api_key
        self._cancelled = False

    def cancel(self) -> None:
        """Request cancellation of the extraction."""
        self._cancelled = True

    def on_progress(self, event: ProgressEvent) -> None:
        """Forward progress callback from ``core.extraction`` to Qt signals."""
        self.progress.emit(event.current, event.total, event.detail or event.stage)

    def on_log(self, message: str) -> None:
        self.log.emit(message)

    def on_chunk_names(self, chunk_index: int, names: list[str]) -> None:
        self.chunk_names.emit(chunk_index, names)

    def on_chunk_error(self, chunk_index: int, message: str) -> None:
        self.chunk_error.emit(chunk_index, message)

    def should_cancel(self) -> bool:
        return self._cancelled

    def run(self) -> None:
        """Execute the extraction process."""
        try:
            result = extract_names(
                text=self.text,
                config=self.config,
                api_key=self.api_key,
                callbacks=self,
            )
            names = [name for name, _ in result.name_pairs]
            if not names and result.errors:
                self.error.emit(f"All {len(result.errors)} chunk(s) failed", result.errors[0])
                return
            self.finished.emit(names, result.counts)
        except ExtractionCancelled:
            self.error.emit("Cancelled", "Extraction was cancelled by user.")
        except Exception as exc:  # noqa: BLE001 - UI should surface unexpected failures
            if self._cancelled:
                self.error.emit("Cancelled", "Extraction was cancelled by user.")
            else:
                self.error.emit("Extraction failed", str(exc))
