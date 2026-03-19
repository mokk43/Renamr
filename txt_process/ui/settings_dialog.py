"""Settings dialog for LLM and prompt configuration."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from txt_process.core.config import Config, DEFAULT_PROMPT_TEMPLATE


class SettingsDialog(QDialog):
    """Dialog for editing LLM and prompt settings."""

    _BUTTON_MIN_HEIGHT = 36
    _BUTTON_MIN_WIDTH = 130
    _MODEL_INPUT_MIN_WIDTH = 460

    def __init__(self, config: Config, parent=None, session_api_key: str = "") -> None:
        super().__init__(parent)
        self.config = config
        self._session_api_key_hint = session_api_key
        self._setup_ui()
        self._load_values()

    def _setup_ui(self) -> None:
        """Set up the dialog UI."""
        self.setWindowTitle("Settings")
        self.setMinimumWidth(760)
        self.setMinimumHeight(500)

        layout = QVBoxLayout(self)

        # --- LLM Connection Group ---
        llm_group = QGroupBox("LLM Connection")
        llm_layout = QFormLayout(llm_group)

        self.edit_base_url = QLineEdit()
        self.edit_base_url.setPlaceholderText("https://api.openai.com/v1")
        self.edit_base_url.setMinimumWidth(self._MODEL_INPUT_MIN_WIDTH)
        llm_layout.addRow("Base URL:", self.edit_base_url)

        self.edit_api_key = QLineEdit()
        self.edit_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.edit_api_key.setPlaceholderText("sk-...")
        self.edit_api_key.setMinimumWidth(self._MODEL_INPUT_MIN_WIDTH)
        llm_layout.addRow("API Key:", self.edit_api_key)

        api_hint = QLabel(
            "For local Ollama, API key can be empty and Base URL should be "
            "http://localhost:11434 (port 11434 auto-selects Ollama protocol)"
        )
        api_hint.setWordWrap(True)
        api_hint.setStyleSheet("color: gray; font-size: 11px;")
        llm_layout.addRow("", api_hint)

        self.chk_remember_key = QCheckBox("Remember API key (saved in config file)")
        llm_layout.addRow("", self.chk_remember_key)

        self.edit_model = QLineEdit()
        self.edit_model.setPlaceholderText("gpt-4o-mini")
        self.edit_model.setMinimumWidth(self._MODEL_INPUT_MIN_WIDTH)
        llm_layout.addRow("Model:", self.edit_model)

        self.spin_temperature = QDoubleSpinBox()
        self.spin_temperature.setRange(0.0, 2.0)
        self.spin_temperature.setSingleStep(0.1)
        self.spin_temperature.setDecimals(2)
        llm_layout.addRow("Temperature:", self.spin_temperature)

        self.spin_timeout = QSpinBox()
        self.spin_timeout.setRange(10, 600)
        self.spin_timeout.setSuffix(" seconds")
        llm_layout.addRow("Timeout:", self.spin_timeout)

        self.spin_max_tokens = QSpinBox()
        self.spin_max_tokens.setRange(0, 4096)
        self.spin_max_tokens.setSingleStep(32)
        self.spin_max_tokens.setSpecialValueText("Auto")
        llm_layout.addRow("Max output tokens:", self.spin_max_tokens)

        self.spin_chunk_bytes = QSpinBox()
        self.spin_chunk_bytes.setRange(1024, 65536)
        self.spin_chunk_bytes.setSingleStep(512)
        self.spin_chunk_bytes.setSuffix(" bytes")
        llm_layout.addRow("Chunk max bytes:", self.spin_chunk_bytes)

        layout.addWidget(llm_group)

        # --- Prompt Group ---
        prompt_group = QGroupBox("Extraction Prompt")
        prompt_layout = QVBoxLayout(prompt_group)

        prompt_hint = QLabel(
            "Use {chunk_text} as placeholder for the text chunk. "
            "Output format must be JSON: {\"names\": [...]}"
        )
        prompt_hint.setWordWrap(True)
        prompt_hint.setStyleSheet("color: gray; font-size: 11px;")
        prompt_layout.addWidget(prompt_hint)

        self.edit_prompt = QPlainTextEdit()
        self.edit_prompt.setMinimumHeight(150)
        prompt_layout.addWidget(self.edit_prompt)

        btn_reset_prompt = QPushButton("Reset to Default")
        self._style_button(btn_reset_prompt)
        btn_reset_prompt.clicked.connect(self._reset_prompt)
        prompt_layout.addWidget(btn_reset_prompt, alignment=Qt.AlignmentFlag.AlignRight)

        layout.addWidget(prompt_group)

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
        self.edit_prompt.setPlainText(self.config.prompt_template)
        self.chk_remember_key.setChecked(self.config.remember_api_key)

        api_key = self.config.api_key or self._session_api_key_hint
        if api_key:
            self.edit_api_key.setText(api_key)

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
            remember_api_key=remember,
            api_key=api_key,
        )
