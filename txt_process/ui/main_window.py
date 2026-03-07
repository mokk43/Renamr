"""Main application window."""

from __future__ import annotations

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

from txt_process.core.config import Config, save_config, get_api_key
from txt_process.core.io import load_text_file, save_text_file
from txt_process.core.llm_client import is_ollama_base_url
from txt_process.core.replace import apply_replacements, build_output_path
from txt_process.ui.models import NameTableModel
from txt_process.ui.settings_dialog import SettingsDialog
from txt_process.ui.workers import ExtractNamesWorker

if TYPE_CHECKING:
    from PySide6.QtCore import QThread


class MainWindow(QMainWindow):
    """Main application window."""

    _BUTTON_MIN_HEIGHT = 36
    _BUTTON_MIN_WIDTH = 140

    def __init__(self, config: Config) -> None:
        super().__init__()
        self.config = config
        self.current_file: Path | None = None
        self.current_text: str = ""
        self.current_encoding: str = "utf-8"
        self.worker: ExtractNamesWorker | None = None
        self.worker_thread: QThread | None = None

        self._setup_ui()
        self._connect_signals()
        self._update_button_states()

    def _setup_ui(self) -> None:
        """Set up the user interface."""
        self.setWindowTitle("Txt Character Renamer")
        self.setMinimumSize(900, 700)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # --- File selection group ---
        file_group = QGroupBox("File")
        file_layout = QHBoxLayout(file_group)

        self.btn_select_file = QPushButton("Select File...")
        self._style_button(self.btn_select_file, min_width=160)
        file_layout.addWidget(self.btn_select_file)

        self.lbl_file_info = QLabel("No file selected")
        self.lbl_file_info.setWordWrap(True)
        file_layout.addWidget(self.lbl_file_info, 1)

        layout.addWidget(file_group)

        # --- Action buttons ---
        btn_layout = QHBoxLayout()

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
        self.btn_reset_all = QPushButton("Reset All")
        self.btn_reset_all.setEnabled(False)
        self._style_button(self.btn_reset_all, min_width=130)
        table_btn_layout.addWidget(self.btn_reset_all)
        table_btn_layout.addStretch()

        self.lbl_edited_count = QLabel("Edited: 0")
        table_btn_layout.addWidget(self.lbl_edited_count)
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
        self.btn_replace.clicked.connect(self._on_replace)
        self.btn_settings.clicked.connect(self._on_settings)
        self.btn_cancel.clicked.connect(self._on_cancel)
        self.btn_reset_all.clicked.connect(self._on_reset_all)
        self.name_model.dataChanged.connect(self._on_table_changed)

    def _update_button_states(self) -> None:
        """Update button enabled states based on current state."""
        has_file = self.current_file is not None
        has_names = self.name_model.rowCount() > 0
        is_working = self.worker is not None

        self.btn_extract.setEnabled(has_file and not is_working)
        self.btn_replace.setEnabled(has_names and not is_working)
        self.btn_reset_all.setEnabled(has_names and not is_working)
        self.btn_select_file.setEnabled(not is_working)

    def _log(self, message: str) -> None:
        """Append message to log panel."""
        self.log_text.append(message)

    @Slot()
    def _on_select_file(self) -> None:
        """Handle file selection."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Text File",
            "",
            "All Files (*)",
        )
        if file_path:
            path = Path(file_path)
            try:
                text, encoding = load_text_file(path)
                self.current_file = path
                self.current_text = text
                self.current_encoding = encoding

                size_kb = path.stat().st_size / 1024
                line_count = text.count("\n") + 1
                self.lbl_file_info.setText(
                    f"{path.name} | {size_kb:.1f} KB | {line_count} lines | {encoding}"
                )
                self._log(f"Loaded: {path}")

                # Clear previous results
                self.name_model.set_names([])
                self._update_button_states()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load file:\n{e}")
                self._log(f"Error loading file: {e}")

    def _is_ollama_endpoint(self, base_url: str) -> bool:
        """Check if base URL points to an Ollama endpoint."""
        return is_ollama_base_url(base_url)

    @Slot()
    def _on_extract(self) -> None:
        """Start name extraction."""
        if not self.current_text:
            return

        api_key = get_api_key()
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

    @Slot(list)
    def _on_extraction_finished(self, names: list[str]) -> None:
        """Handle extraction completion."""
        self.name_model.set_names(names)
        self.progress_bar.setVisible(False)
        self.btn_cancel.setVisible(False)
        self.lbl_status.setText(f"Extracted {len(names)} unique names")
        self._log(f"Extraction complete: {len(names)} unique names")
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
    def _on_cancel(self) -> None:
        """Cancel current extraction."""
        if self.worker:
            self.worker.cancel()
            self.lbl_status.setText("Cancelling...")
            self._log("Cancellation requested...")

    @Slot()
    def _on_replace(self) -> None:
        """Apply replacements and export."""
        if not self.current_file or not self.current_text:
            return

        mappings = self.name_model.get_edited_mappings()
        if not mappings:
            QMessageBox.information(
                self,
                "No Changes",
                "No names have been edited. Please edit replacement names first.",
            )
            return

        try:
            result_text, counts = apply_replacements(self.current_text, mappings)
            output_path = build_output_path(self.current_file)

            # Try to save to default location
            try:
                save_text_file(output_path, result_text, self.current_encoding)
            except PermissionError:
                # Ask user for alternate location
                alt_path, _ = QFileDialog.getSaveFileName(
                    self,
                    "Save Processed File",
                    str(output_path),
                    "Text Files (*.txt);;All Files (*)",
                )
                if alt_path:
                    output_path = Path(alt_path)
                    save_text_file(output_path, result_text, self.current_encoding)
                else:
                    return

            # Report results
            total_count = sum(counts.values())
            self._log(f"Replaced {total_count} occurrences across {len(counts)} names")
            for name, count in counts.items():
                if count > 0:
                    self._log(f"  {name}: {count}")
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
        dialog = SettingsDialog(self.config, self)
        if dialog.exec():
            self.config = dialog.get_config()
            save_config(self.config)
            self._log("Settings saved")

    @Slot()
    def _on_reset_all(self) -> None:
        """Reset all replacement names."""
        self.name_model.reset_all()
        self._on_table_changed()

    @Slot()
    def _on_table_changed(self) -> None:
        """Update edited count label."""
        count = len(self.name_model.get_edited_mappings())
        self.lbl_edited_count.setText(f"Edited: {count}")
