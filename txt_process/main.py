"""Application entrypoint."""

import sys

from PySide6.QtWidgets import QApplication

from txt_process.core.config import load_config
from txt_process.ui.main_window import MainWindow


def main() -> int:
    """Run the application."""
    app = QApplication(sys.argv)
    app.setApplicationName("Txt Character Renamer")
    app.setOrganizationName("txt-process")

    # Load config on startup
    config = load_config()

    window = MainWindow(config)
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
