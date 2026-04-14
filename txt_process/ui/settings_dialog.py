"""Settings dialog for LLM and prompt configuration."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from txt_process.core.config import DEFAULT_PROMPT_TEMPLATE, Config


class SettingsDialog(QDialog):
    """Dialog for editing LLM and prompt settings."""

    _BUTTON_MIN_HEIGHT = 36
    _BUTTON_MIN_WIDTH = 130
    _CONTROL_MIN_HEIGHT = 30

    def __init__(
        self,
        config: Config,
        parent=None,
        session_api_key: str = "",
        cached_names: list[str] | None = None,
    ) -> None:
        super().__init__(parent)
        self.config = config
        self._session_api_key_hint = session_api_key
        self._cached_names = cached_names or []
        self._setup_ui()
        self._load_values()

    def _setup_ui(self) -> None:
        """Set up the dialog UI."""
        self.setWindowTitle("Settings")
        self.setMinimumWidth(760)
        self.setMinimumHeight(500)

        layout = QVBoxLayout(self)

        # --- LLM Connection Group (unified 2-column grid) ---
        # Grid columns: 0=labelL, 1=ctrlL, 2=spacing, 3=labelR, 4=ctrlR
        llm_group = QGroupBox("LLM Connection")
        g = QGridLayout(llm_group)
        g.setContentsMargins(12, 12, 12, 12)
        g.setVerticalSpacing(10)
        g.setHorizontalSpacing(10)
        g.setColumnStretch(1, 1)
        g.setColumnMinimumWidth(2, 20)
        g.setColumnStretch(4, 1)
        row = 0

        def _pair(r, l1, w1, l2, w2):
            self._apply_control_height(w1)
            self._apply_control_height(w2)
            g.addWidget(self._label(l1), r, 0, Qt.AlignmentFlag.AlignRight)
            g.addWidget(w1, r, 1)
            g.addWidget(self._label(l2), r, 3, Qt.AlignmentFlag.AlignRight)
            g.addWidget(w2, r, 4)

        self.edit_base_url = QLineEdit()
        self.edit_base_url.setPlaceholderText("https://api.openai.com/v1")
        self.edit_api_key = QLineEdit()
        self.edit_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.edit_api_key.setPlaceholderText("sk-...")
        _pair(row, "Base URL:", self.edit_base_url,
              "API Key:", self.edit_api_key)
        row += 1

        api_hint = QLabel(
            "For local Ollama, API key can be empty; "
            "use http://localhost:11434 to auto-select Ollama protocol."
        )
        api_hint.setWordWrap(True)
        api_hint.setStyleSheet("color: gray; font-size: 11px;")
        self.chk_remember_key = QCheckBox("Remember API key (saved in config file)")
        g.addWidget(api_hint, row, 0, 1, 2)
        g.addWidget(self.chk_remember_key, row, 3, 1, 2)
        row += 1

        self.edit_model = QLineEdit()
        self.edit_model.setPlaceholderText("gpt-4o-mini")
        self.spin_temperature = QDoubleSpinBox()
        self.spin_temperature.setRange(0.0, 2.0)
        self.spin_temperature.setSingleStep(0.1)
        self.spin_temperature.setDecimals(2)
        _pair(row, "Model:", self.edit_model,
              "Temperature:", self.spin_temperature)
        row += 1

        self.spin_timeout = QSpinBox()
        self.spin_timeout.setRange(10, 600)
        self.spin_timeout.setSuffix(" seconds")
        self.spin_max_tokens = QSpinBox()
        self.spin_max_tokens.setRange(0, 4096)
        self.spin_max_tokens.setSingleStep(32)
        self.spin_max_tokens.setSpecialValueText("Auto")
        _pair(row, "Timeout:", self.spin_timeout,
              "Max output tokens:", self.spin_max_tokens)
        row += 1

        self.spin_chunk_bytes = QSpinBox()
        self.spin_chunk_bytes.setRange(1024, 65536)
        self.spin_chunk_bytes.setSingleStep(512)
        self.spin_chunk_bytes.setSuffix(" bytes")
        self.spin_begin_scan = QSpinBox()
        self.spin_begin_scan.setRange(5, 500)
        self.spin_begin_scan.setSingleStep(5)
        self.spin_begin_scan.setSuffix(" chunks")
        self.spin_begin_scan.setToolTip(
            "When total chunks exceed this value, switch to sampled extraction "
            "(all first N chunks are fully scanned, then only every Kth chunk)."
        )
        _pair(row, "Chunk max bytes:", self.spin_chunk_bytes,
              "Full-scan threshold:", self.spin_begin_scan)
        row += 1

        self.spin_scan_interval = QSpinBox()
        self.spin_scan_interval.setRange(2, 10)
        self.spin_scan_interval.setSingleStep(1)
        self.spin_scan_interval.setToolTip(
            "After the full-scan threshold, send every Nth chunk to the LLM. "
            "Skipped chunks are scanned locally; those with <2 known names "
            "are sent to the LLM in a follow-up pass."
        )
        self._apply_control_height(self.spin_scan_interval)
        g.addWidget(self._label("Scan interval:"), row, 0,
                    Qt.AlignmentFlag.AlignRight)
        g.addWidget(self.spin_scan_interval, row, 1)
        scan_hint = QLabel(
            "For large files: chunks beyond the threshold are sampled; "
            "skipped chunks with <2 known names get a follow-up pass."
        )
        scan_hint.setWordWrap(True)
        scan_hint.setStyleSheet("color: gray; font-size: 11px;")
        g.addWidget(scan_hint, row, 3, 1, 2)
        row += 1

        layout.addWidget(llm_group)

        # --- Prompt Group ---
        prompt_group = QGroupBox("Extraction Prompt")
        prompt_layout = QVBoxLayout(prompt_group)

        prompt_hint = QLabel(
            "Use {chunk_text} as placeholder for the text chunk. "
            "Output format must be JSON: {\"names\": [...]}"
        )
        prompt_hint.setWordWrap(True)
        prompt_hint.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        prompt_hint.setStyleSheet("color: gray; font-size: 11px;")
        prompt_layout.addWidget(prompt_hint)

        self.edit_prompt = QPlainTextEdit()
        self.edit_prompt.setMinimumHeight(150)
        prompt_layout.addWidget(self.edit_prompt)

        btn_reset_prompt = QPushButton("Reset to Default")
        self._style_button(btn_reset_prompt)
        btn_reset_prompt.clicked.connect(self._reset_prompt)
        prompt_layout.addWidget(btn_reset_prompt, alignment=Qt.AlignmentFlag.AlignRight)

        # --- Name Cache Group ---
        cache_group = QGroupBox("Replacement Name Cache")
        cache_layout = QVBoxLayout(cache_group)

        cache_hint = QLabel(
            "One name per line. These values appear as dropdown suggestions in "
            "the replacement column."
        )
        cache_hint.setWordWrap(True)
        cache_hint.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        cache_hint.setStyleSheet("color: gray; font-size: 11px;")
        cache_layout.addWidget(cache_hint)

        self.edit_cached_names = QPlainTextEdit()
        self.edit_cached_names.setMinimumHeight(120)
        cache_layout.addWidget(self.edit_cached_names)

        # Prompt + cache in two columns
        prompt_cache_layout = QHBoxLayout()
        prompt_cache_layout.addWidget(prompt_group, 1)
        prompt_cache_layout.addWidget(cache_group, 1)
        layout.addLayout(prompt_cache_layout)

        # --- Dialog buttons ---
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        for button in button_box.buttons():
            if (
                button_box.standardButton(button)
                == QDialogButtonBox.StandardButton.Cancel
            ):
                button.setObjectName("cancelButton")
            self._style_button(button)
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _label(self, text: str) -> QLabel:
        """Create a right-aligned label with consistent styling."""
        lbl = QLabel(text)
        lbl.setMinimumHeight(self._CONTROL_MIN_HEIGHT)
        return lbl

    def _apply_control_height(self, widget) -> None:
        """Apply consistent minimum height to input controls."""
        widget.setMinimumHeight(self._CONTROL_MIN_HEIGHT)

    def _style_button(self, button: QPushButton) -> None:
        """Apply consistent larger button sizing."""
        button.setMinimumHeight(self._BUTTON_MIN_HEIGHT)
        button.setMinimumWidth(self._BUTTON_MIN_WIDTH)

    def _load_values(self) -> None:
        """Load current config values into the UI."""
        self.edit_base_url.setText(self.config.base_url)
        self.edit_model.setText(self.config.model)
        self.spin_temperature.setValue(self.config.temperature)
        self.spin_timeout.setValue(int(self.config.timeout_seconds))
        self.spin_max_tokens.setValue(int(self.config.max_tokens or 0))
        self.spin_chunk_bytes.setValue(int(self.config.chunk_max_bytes))
        self.spin_begin_scan.setValue(self.config.begin_scan_chunks)
        self.spin_scan_interval.setValue(self.config.scan_interval)
        self.edit_prompt.setPlainText(self.config.prompt_template)
        self.chk_remember_key.setChecked(self.config.remember_api_key)

        api_key = self.config.api_key or self._session_api_key_hint
        if api_key:
            self.edit_api_key.setText(api_key)
        self.edit_cached_names.setPlainText("\n".join(self._cached_names))

    def _reset_prompt(self) -> None:
        """Reset prompt to default template."""
        self.edit_prompt.setPlainText(DEFAULT_PROMPT_TEMPLATE)

    def _on_accept(self) -> None:
        """Handle OK button."""
        self.accept()

    def get_api_key_entered(self) -> str:
        """Return the API key as entered in the dialog (for session use)."""
        return self.edit_api_key.text().strip()

    def get_config(self) -> Config:
        """Get the updated config from the dialog values."""
        remember = self.chk_remember_key.isChecked()
        api_key = self.edit_api_key.text().strip() if remember else ""
        return Config(
            base_url=self.edit_base_url.text().strip() or self.config.base_url,
            model=self.edit_model.text().strip() or self.config.model,
            temperature=self.spin_temperature.value(),
            timeout_seconds=float(self.spin_timeout.value()),
            max_tokens=(
                int(self.spin_max_tokens.value())
                if int(self.spin_max_tokens.value()) > 0
                else None
            ),
            prompt_template=self.edit_prompt.toPlainText() or DEFAULT_PROMPT_TEMPLATE,
            chunk_max_bytes=int(self.spin_chunk_bytes.value()),
            request_interval_seconds=self.config.request_interval_seconds,
            begin_scan_chunks=self.spin_begin_scan.value(),
            scan_interval=self.spin_scan_interval.value(),
            remember_api_key=remember,
            api_key=api_key,
        )

    def get_cached_names(self) -> list[str]:
        """Get manually edited cached replacement names from dialog."""
        lines = self.edit_cached_names.toPlainText().splitlines()
        normalized: list[str] = []
        seen: set[str] = set()
        for line in lines:
            name = line.strip()
            if not name or name in seen:
                continue
            seen.add(name)
            normalized.append(name)
        return normalized
