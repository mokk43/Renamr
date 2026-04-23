"""Main application window."""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTableView,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from txt_process.core.config import Config, save_config
from txt_process.core.document import Document
from txt_process.core.epub_io import (
    EpubEmptyError,
    EpubEncryptedError,
    EpubParseError,
)
from txt_process.core.llm_client import is_ollama_base_url
from txt_process.core.name_cache import load_name_cache, merge_cached_names, save_name_cache
from txt_process.core.normalize_txt import normalize_text_file
from txt_process.core.replace import build_output_path
from txt_process.ui.delegates import ReplacementNameDelegate
from txt_process.ui.models import NameTableModel
from txt_process.ui.settings_dialog import SettingsDialog
from txt_process.ui.workers import ExtractNamesWorker, LoadDocumentWorker

if TYPE_CHECKING:
    from PySide6.QtCore import QThread


class MainWindow(QMainWindow):
    """Main application window."""

    _BUTTON_MIN_HEIGHT = 36
    _BUTTON_MIN_WIDTH = 140

    def __init__(self, config: Config) -> None:
        super().__init__()
        self.config = config
        self.current_doc: Document | None = None
        self._session_api_key: str | None = None
        self.worker: ExtractNamesWorker | None = None
        self.worker_thread: QThread | None = None
        self.load_worker: LoadDocumentWorker | None = None
        self.load_worker_thread: QThread | None = None
        self._extract_started_at: float | None = None
        self.cached_replacement_names: list[str] = load_name_cache()

        self._setup_ui()
        self._connect_signals()
        self._update_button_states()

    @property
    def current_file(self) -> Path | None:
        return self.current_doc.path if self.current_doc else None

    @property
    def current_text(self) -> str:
        return self.current_doc.text if self.current_doc else ""

    @property
    def current_encoding(self) -> str:
        if self.current_doc is None:
            return "utf-8"
        return self.current_doc.encoding or "utf-8"

    def _setup_ui(self) -> None:
        """Set up the user interface."""
        self.setWindowTitle("Txt Character Renamer")
        self.setMinimumSize(900, 700)
        self.resize(1125, 700)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # --- File selection group ---
        file_group = QGroupBox("File")
        file_layout = QHBoxLayout(file_group)

        self.btn_select_file = QPushButton("Select File...")
        self._style_button(self.btn_select_file, min_width=124)
        file_layout.addWidget(self.btn_select_file)

        self.lbl_file_info = QLabel("No file selected")
        self.lbl_file_info.setWordWrap(True)
        file_layout.addWidget(self.lbl_file_info, 1)

        layout.addWidget(file_group)

        # --- Action buttons ---
        btn_layout = QHBoxLayout()

        self.btn_normalize = QPushButton("Normalize Layout")
        self.btn_normalize.setEnabled(False)
        self._style_button(self.btn_normalize)
        btn_layout.addWidget(self.btn_normalize)

        self.btn_extract = QPushButton("Extract Names")
        self.btn_extract.setEnabled(False)
        self._style_button(self.btn_extract)
        btn_layout.addWidget(self.btn_extract)

        self.btn_replace = QPushButton("Replace && Export")
        self.btn_replace.setEnabled(False)
        self._style_button(self.btn_replace)
        btn_layout.addWidget(self.btn_replace)

        btn_layout.addStretch()

        self.btn_settings = QPushButton("Settings...")
        self._style_button(self.btn_settings)
        btn_layout.addWidget(self.btn_settings)

        layout.addLayout(btn_layout)

        # --- Progress area ---
        progress_layout = QHBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        progress_layout.addWidget(self.progress_bar)

        self.lbl_status = QLabel("")
        progress_layout.addWidget(self.lbl_status)
        progress_layout.addStretch()

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setObjectName("cancelButton")
        self.btn_cancel.setVisible(False)
        self._style_button(self.btn_cancel, min_width=120)
        progress_layout.addWidget(self.btn_cancel)

        layout.addLayout(progress_layout)

        # --- Splitter: Table + Log ---
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Name mapping table
        table_group = QGroupBox("Character Names")
        table_layout = QVBoxLayout(table_group)

        self.name_model = NameTableModel()
        self.table_view = QTableView()
        self.table_view.setModel(self.name_model)
        self.replacement_delegate = ReplacementNameDelegate(
            suggestions=self.cached_replacement_names,
            parent=self.table_view,
        )
        self.table_view.setItemDelegateForColumn(1, self.replacement_delegate)
        self.table_view.setAlternatingRowColors(True)
        self.table_view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table_view.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.table_view.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        table_layout.addWidget(self.table_view)

        # Table helper buttons
        table_btn_layout = QHBoxLayout()
        self.btn_add_name = QPushButton("Add Names")
        self.btn_add_name.setEnabled(False)
        self._style_button(self.btn_add_name, min_width=110)
        self.btn_add_name.setToolTip(
            "Append a row to enter custom find/replace text (both columns editable)."
        )
        table_btn_layout.addWidget(self.btn_add_name)

        self.btn_import_names = QPushButton("Import Names")
        self.btn_import_names.setEnabled(False)
        self._style_button(self.btn_import_names, min_width=110)
        self.btn_import_names.setToolTip(
            'Import name pairs from a CSV file ("source,target" per line).'
        )
        table_btn_layout.addWidget(self.btn_import_names)

        table_btn_layout.addStretch()

        self.btn_reset_all = QPushButton("Reset All")
        self.btn_reset_all.setEnabled(False)
        self._style_button(self.btn_reset_all, min_width=110)
        table_btn_layout.addWidget(self.btn_reset_all)
        table_layout.addLayout(table_btn_layout)

        splitter.addWidget(table_group)

        # Log panel
        log_group = QGroupBox("Log")
        log_layout = QVBoxLayout(log_group)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        log_layout.addWidget(self.log_text)
        splitter.addWidget(log_group)

        splitter.setSizes([400, 400])
        layout.addWidget(splitter, 1)

    def _style_button(
        self,
        button: QPushButton,
        *,
        min_width: int | None = None,
        min_height: int | None = None,
    ) -> None:
        """Apply consistent larger button sizing."""
        button.setMinimumHeight(min_height or self._BUTTON_MIN_HEIGHT)
        button.setMinimumWidth(min_width or self._BUTTON_MIN_WIDTH)

    def _connect_signals(self) -> None:
        """Connect UI signals to slots."""
        self.btn_select_file.clicked.connect(self._on_select_file)
        self.btn_extract.clicked.connect(self._on_extract)
        self.btn_normalize.clicked.connect(self._on_normalize)
        self.btn_replace.clicked.connect(self._on_replace)
        self.btn_settings.clicked.connect(self._on_settings)
        self.btn_cancel.clicked.connect(self._on_cancel)
        self.btn_reset_all.clicked.connect(self._on_reset_all)
        self.btn_add_name.clicked.connect(self._on_add_name_row)
        self.btn_import_names.clicked.connect(self._on_import_names)
        self.name_model.dataChanged.connect(self._on_table_changed)

    def _update_button_states(self) -> None:
        """Update button enabled states based on current state."""
        has_file = self.current_doc is not None
        has_names = self.name_model.rowCount() > 0
        is_working = self.worker is not None
        is_loading = self.load_worker is not None
        busy = is_working or is_loading

        supports_normalize = (
            self.current_doc.supports_normalize if self.current_doc else True
        )
        self.btn_normalize.setVisible(supports_normalize)

        self.btn_extract.setEnabled(has_file and not busy)
        self.btn_normalize.setEnabled(has_file and not busy and supports_normalize)
        self.btn_replace.setEnabled(has_names and not busy)
        self.btn_reset_all.setEnabled(has_names and not busy)
        self.btn_add_name.setEnabled(has_file and not busy)
        self.btn_import_names.setEnabled(has_file and not busy)
        self.btn_select_file.setEnabled(not busy)

    def _log(self, message: str) -> None:
        """Append message to log panel."""
        self.log_text.append(message)

    @Slot()
    def _on_select_file(self) -> None:
        """Handle file selection."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select File",
            "",
            "Supported (*.txt *.epub);;Text Files (*.txt);;"
            "EPUB Books (*.epub);;All Files (*)",
        )
        if file_path:
            self._start_load(Path(file_path))

    def _start_load(self, path: Path) -> None:
        """Kick off a :class:`LoadDocumentWorker` for ``path``."""
        from PySide6.QtCore import QThread

        self.load_worker = LoadDocumentWorker(path=path)
        self.load_worker_thread = QThread()
        self.load_worker.moveToThread(self.load_worker_thread)

        self.load_worker_thread.started.connect(self.load_worker.run)
        self.load_worker.progress.connect(self._on_load_progress)
        self.load_worker.finished.connect(self._on_load_finished)
        self.load_worker.error.connect(self._on_load_error)
        self.load_worker.finished.connect(self._cleanup_load_worker)
        self.load_worker.error.connect(self._cleanup_load_worker)

        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(0)  # indeterminate
        self.progress_bar.setValue(0)
        self.lbl_status.setText(f"Loading {path.name}...")
        self._update_button_states()

        self.load_worker_thread.start()

    @Slot(int, int, str)
    def _on_load_progress(self, current: int, total: int, status: str) -> None:
        if total > 0:
            self.progress_bar.setMaximum(total)
            self.progress_bar.setValue(current)
        self.lbl_status.setText(status)

    @Slot(object)
    def _on_load_finished(self, doc: object) -> None:
        if not isinstance(doc, Document):
            return
        self.progress_bar.setVisible(False)
        self.progress_bar.setMaximum(100)
        self.lbl_status.setText("")
        self._activate_document(doc)
        self._log(f"Loaded: {doc.path}")

    @Slot(str, str, str)
    def _on_load_error(self, kind: str, message: str, details: str) -> None:
        self.progress_bar.setVisible(False)
        self.progress_bar.setMaximum(100)
        self.lbl_status.setText("")
        friendly, title = self._friendly_load_error(kind, message)
        QMessageBox.critical(self, title, friendly)
        self._log(f"Error loading file: {message}")
        if details and details != message:
            self._log(f"Details: {details}")

    def _friendly_load_error(self, kind: str, message: str) -> tuple[str, str]:
        if kind == EpubEncryptedError.__name__:
            return (
                "This EPUB is DRM-protected or uses font obfuscation and "
                "cannot be processed.",
                "DRM-protected EPUB",
            )
        if kind == EpubEmptyError.__name__:
            return (
                "This EPUB contains no readable content.",
                "Empty EPUB",
            )
        if kind == EpubParseError.__name__:
            return (f"Failed to parse EPUB:\n{message}", "EPUB Parse Error")
        return (f"Failed to load file:\n{message}", "Error")

    def _activate_document(self, doc: Document) -> None:
        """Make ``doc`` the active document and refresh the UI."""
        self.current_doc = doc
        self.lbl_file_info.setText(doc.display_info)

        # Changing active file invalidates previous extracted names.
        self.name_model.set_names([])
        self.name_model.set_source_text(doc.text)
        self._on_table_changed()
        self._update_button_states()

    def _set_active_file(self, path: Path) -> None:
        """Synchronously load ``path`` (used after in-place normalize)."""
        from txt_process.core.document import load_document

        self._activate_document(load_document(path))

    def _build_normalized_path(self, input_path: Path) -> Path:
        """Build normalized output path with a _normalized suffix."""
        return input_path.parent / f"{input_path.stem}_normalized{input_path.suffix}"

    @Slot()
    def _on_normalize(self) -> None:
        """Normalize active file layout and switch follow-up operations to that output."""
        if self.current_doc is None or not self.current_doc.supports_normalize:
            return

        source_path = self.current_doc.path
        normalized_path = self._build_normalized_path(source_path)

        try:
            # Ensure output corresponds to this normalization attempt.
            if normalized_path.exists():
                normalized_path.unlink()

            normalize_text_file(str(source_path), str(normalized_path))

            if not normalized_path.exists():
                raise RuntimeError("Normalization did not produce an output file.")

            self._set_active_file(normalized_path)
            self._log(f"Normalized layout: {source_path} -> {normalized_path}")
            QMessageBox.information(
                self,
                "Normalization Complete",
                f"Saved normalized file:\n{normalized_path}\n\n"
                "Extract and export now use this normalized file.",
            )
        except Exception as e:
            QMessageBox.critical(self, "Normalization Error", f"Failed to normalize:\n{e}")
            self._log(f"Normalization error: {e}")

    def _is_ollama_endpoint(self, base_url: str) -> bool:
        """Check if base URL points to an Ollama endpoint."""
        return is_ollama_base_url(base_url)

    @Slot()
    def _on_extract(self) -> None:
        """Start name extraction."""
        if not self.current_text:
            return

        # Start each extraction click with a clean table.
        self.name_model.set_names([])
        self.name_model.set_source_text(self.current_text)
        self._on_table_changed()

        api_key = self._session_api_key or self.config.api_key
        if not api_key and not self._is_ollama_endpoint(self.config.base_url):
            QMessageBox.warning(
                self,
                "API Key Required",
                "Please configure your API key in Settings.",
            )
            self._on_settings()
            return
        if not api_key:
            api_key = "ollama"

        from PySide6.QtCore import QThread

        self.worker = ExtractNamesWorker(
            text=self.current_text,
            config=self.config,
            api_key=api_key,
        )
        self.worker_thread = QThread()
        self.worker.moveToThread(self.worker_thread)

        # Connect signals
        self.worker_thread.started.connect(self.worker.run)
        self.worker.progress.connect(self._on_extraction_progress)
        self.worker.chunk_names.connect(self._on_chunk_names)
        self.worker.chunk_error.connect(self._on_chunk_error)
        self.worker.log.connect(self._log)
        self.worker.finished.connect(self._on_extraction_finished)
        self.worker.error.connect(self._on_extraction_error)
        self.worker.finished.connect(self._cleanup_worker)
        self.worker.error.connect(self._cleanup_worker)

        # Update UI
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.btn_cancel.setVisible(True)
        self.lbl_status.setText("Starting extraction...")
        self._update_button_states()
        self._extract_started_at = time.monotonic()
        self._log("Starting name extraction...")

        self.worker_thread.start()

    @Slot(int, int, str)
    def _on_extraction_progress(self, current: int, total: int, status: str) -> None:
        """Update progress bar."""
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        self.lbl_status.setText(f"{current}/{total}: {status}")

    @Slot(int, list)
    def _on_chunk_names(self, chunk_idx: int, names: list[str]) -> None:
        """Handle names extracted from a chunk."""
        if names:
            self._log(f"Chunk {chunk_idx + 1}: found {len(names)} names")

    @Slot(int, str)
    def _on_chunk_error(self, chunk_idx: int, error_msg: str) -> None:
        """Log per-chunk extraction errors so the user sees what went wrong."""
        self._log(f"Chunk {chunk_idx + 1} error: {error_msg}")

    @Slot(list, dict)
    def _on_extraction_finished(self, names: list[str], counts: dict[str, int]) -> None:
        """Handle extraction completion."""
        self.name_model.set_names(names, counts)
        self.progress_bar.setVisible(False)
        self.btn_cancel.setVisible(False)
        kept_names = self.name_model.rowCount()
        filtered_out = max(0, len(names) - kept_names)
        total_mentions = sum(counts.values())
        self.lbl_status.setText(
            f"Extracted {len(names)} unique names; kept {kept_names} with >0 occurrences"
        )
        self._log(
            f"Extraction complete: {len(names)} unique names, {total_mentions} total occurrences, "
            f"{filtered_out} filtered with 0 occurrences"
        )
        self._log_extraction_duration()
        self._update_button_states()
        self._on_table_changed()

    @Slot(str, str)
    def _on_extraction_error(self, message: str, details: str) -> None:
        """Handle extraction error."""
        self.progress_bar.setVisible(False)
        self.btn_cancel.setVisible(False)
        self.lbl_status.setText(f"Error: {message}")
        self._log(f"Error: {message}")
        if details:
            self._log(f"Details: {details}")
        self._log_extraction_duration(prefix="Extraction stopped")
        self._update_button_states()
        QMessageBox.critical(self, "Extraction Error", f"{message}\n\n{details}")

    @Slot()
    def _cleanup_worker(self) -> None:
        """Clean up worker thread."""
        if self.worker_thread:
            self.worker_thread.quit()
            self.worker_thread.wait()
            self.worker_thread = None
        self.worker = None
        self._update_button_states()

    @Slot()
    def _cleanup_load_worker(self) -> None:
        """Clean up the document-load worker thread."""
        if self.load_worker_thread:
            self.load_worker_thread.quit()
            self.load_worker_thread.wait()
            self.load_worker_thread = None
        self.load_worker = None
        self._update_button_states()

    @Slot()
    def _on_cancel(self) -> None:
        """Cancel current extraction."""
        if self.worker:
            self.worker.cancel()
            self.lbl_status.setText("Cancelling...")
            self._log("Cancellation requested...")

    @Slot()
    def _on_replace(self) -> None:
        """Apply replacements and export."""
        if self.current_doc is None or not self.current_doc.text:
            return

        mappings = self.name_model.get_edited_mappings()
        if not mappings:
            QMessageBox.information(
                self,
                "No Changes",
                "No names have been edited. Please edit replacement names first.",
            )
            return

        doc = self.current_doc
        output_path = build_output_path(doc.path)
        save_filter = (
            "EPUB Books (*.epub);;All Files (*)"
            if doc.kind == "epub"
            else "Text Files (*.txt);;All Files (*)"
        )

        try:
            try:
                totals, per_item = doc.save_processed(mappings, output_path)
            except PermissionError:
                alt_path, _ = QFileDialog.getSaveFileName(
                    self,
                    "Save Processed File",
                    str(output_path),
                    save_filter,
                )
                if alt_path:
                    output_path = Path(alt_path)
                    totals, per_item = doc.save_processed(mappings, output_path)
                else:
                    return

            total_count = sum(totals.values())
            self._log(
                f"Replaced {total_count} occurrences across {len(totals)} names"
            )
            for name, count in totals.items():
                if count > 0:
                    self._log(f"  {name}: {count}")
            if per_item:
                for item_name, item_counts in per_item.items():
                    item_total = sum(item_counts.values())
                    if item_total:
                        self._log(f"  [{item_name}] {item_total} replacements")
            self._log(f"Saved to: {output_path}")

            QMessageBox.information(
                self,
                "Export Complete",
                f"Replaced {total_count} occurrences.\n\nSaved to:\n{output_path}",
            )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to export:\n{e}")
            self._log(f"Export error: {e}")

    @Slot()
    def _on_settings(self) -> None:
        """Open settings dialog."""
        dialog = SettingsDialog(
            self.config,
            self,
            session_api_key=self._session_api_key or "",
            cached_names=self.cached_replacement_names,
        )
        if dialog.exec():
            self.config = dialog.get_config()
            save_config(self.config)
            self.cached_replacement_names = save_name_cache(dialog.get_cached_names())
            self.replacement_delegate.set_suggestions(self.cached_replacement_names)
            entered = dialog.get_api_key_entered()
            if entered:
                self._session_api_key = entered
            else:
                self._session_api_key = None
            self._log("Settings saved")

    @Slot()
    def _on_add_name_row(self) -> None:
        """Append an empty row with editable find and replacement columns."""
        self.name_model.append_custom_row()
        self.table_view.scrollToBottom()
        last_row = self.name_model.rowCount() - 1
        if last_row >= 0:
            idx = self.name_model.index(last_row, 0)
            self.table_view.setCurrentIndex(idx)
            self.table_view.edit(idx)
        self._on_table_changed()
        self._update_button_states()

    @Slot()
    def _on_import_names(self) -> None:
        """Import name pairs from a CSV file (source,target per line)."""
        import csv
        import io

        if self.current_doc is None:
            QMessageBox.information(
                self,
                "No File Loaded",
                "Please select a .txt or .epub file before importing names.",
            )
            return

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Name List",
            "",
            "CSV Files (*.csv);;All Files (*)",
        )
        if not file_path:
            return

        try:
            raw = Path(file_path).read_text(encoding="utf-8-sig")
            reader = csv.reader(io.StringIO(raw))
            pairs: list[tuple[str, str]] = []
            skipped = 0
            for lineno, row in enumerate(reader, start=1):
                if not row or (len(row) == 1 and not row[0].strip()):
                    continue
                if len(row) < 2:
                    skipped += 1
                    self._log(f"CSV line {lineno}: skipped (expected 2 columns, got {len(row)})")
                    continue
                src, tgt = row[0].strip(), row[1].strip()
                if not src:
                    skipped += 1
                    continue
                pairs.append((src, tgt))

            if not pairs:
                QMessageBox.warning(
                    self,
                    "Import Failed",
                    "No valid name pairs found in the CSV file.\n"
                    'Expected format: "source,target" per line.',
                )
                return

            if self.current_doc:
                self.name_model.set_source_text(self.current_doc.text)
            self.name_model.set_name_pairs(pairs)
            self._on_table_changed()
            self._update_button_states()

            kept = self.name_model.rowCount()
            filtered_out = max(0, len(pairs) - kept)
            msg = f"Imported {kept} name pairs from {Path(file_path).name}"
            details: list[str] = []
            if filtered_out:
                details.append(f"{filtered_out} filtered with 0 occurrences")
            if skipped:
                details.append(f"{skipped} lines skipped")
            if details:
                msg += f" ({', '.join(details)})"
            self._log(msg)
            self.lbl_status.setText(msg)
        except Exception as e:
            QMessageBox.critical(self, "Import Error", f"Failed to read CSV:\n{e}")
            self._log(f"CSV import error: {e}")

    @Slot()
    def _on_reset_all(self) -> None:
        """Reset all replacement names."""
        self.name_model.reset_all()
        self._on_table_changed()

    @Slot()
    def _on_table_changed(self) -> None:
        """Sync replacement name cache when the table changes."""
        self._sync_replacement_name_cache()

    def _sync_replacement_name_cache(self) -> None:
        """Persist newly entered replacement names into local cache."""
        merged = merge_cached_names(
            self.cached_replacement_names,
            self.name_model.get_non_empty_replacements(),
        )
        if merged == self.cached_replacement_names:
            return
        self.cached_replacement_names = save_name_cache(merged)
        self.replacement_delegate.set_suggestions(self.cached_replacement_names)

    def _log_extraction_duration(self, prefix: str = "Extraction time cost") -> None:
        """Log elapsed extraction time if extraction was started."""
        if self._extract_started_at is None:
            return
        elapsed = time.monotonic() - self._extract_started_at
        self._extract_started_at = None
        self._log(f"{prefix}: {elapsed:.2f}s")
