"""AXIS OS — entry point."""
import sys
import os
import json

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QCoreApplication
from PyQt6.QtGui import QIcon


def load_config() -> dict:
    from core.paths import CONFIG_FILE, migrate_data
    migrate_data()
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def main():
    # Must be set before QApplication
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)

    app = QApplication(sys.argv)
    app.setApplicationName("AXIS OS")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("AXIS")

    config = load_config()

    # Import here so QApplication exists first
    from gui.main_window import AxisWindow
    window = AxisWindow(config)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
