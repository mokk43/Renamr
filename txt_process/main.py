"""Application entrypoint."""

import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from txt_process.core.config import load_config
from txt_process.ui.main_window import MainWindow


def _configure_app_icon(app: QApplication) -> None:
    """Set a custom application icon when available."""
    resources_dir = Path(__file__).resolve().parent / "resources"
    icon_candidates = [
        resources_dir / "app_icon.icns",
        resources_dir / "app_icon_1024.png",
        resources_dir / "app_icon_512.png",
    ]

    for icon_path in icon_candidates:
        if not icon_path.exists():
            continue
        icon = QIcon(str(icon_path))
        if not icon.isNull():
            app.setWindowIcon(icon)
            return


def main() -> int:
    """Run the application."""
    app = QApplication(sys.argv)
    app.setApplicationName("Txt Character Renamer")
    app.setOrganizationName("Renamr")
    _configure_app_icon(app)
    app.setStyleSheet(
        """
        QPushButton {
            background-color: #4f6bed;
            color: #ffffff;
            border: 1px solid #3f55be;
            border-radius: 6px;
            padding: 6px 12px;
        }
        QPushButton:hover {
            background-color: #5d79f0;
        }
        QPushButton:pressed {
            background-color: #3f55be;
        }
        QPushButton:disabled {
            background-color: #c3cadb;
            color: #6b7280;
            border-color: #aeb6c8;
        }
        QPushButton#cancelButton,
        QPushButton#cancelButton:hover,
        QPushButton#cancelButton:pressed,
        QPushButton#cancelButton:disabled {
            background-color: transparent;
            color: #1f2937;
            border: 1px solid #aeb6c8;
        }
        """
    )

    # Load config on startup
    config = load_config()

    window = MainWindow(config)
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
