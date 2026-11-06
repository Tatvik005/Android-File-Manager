"""
main.py
Application entrypoint for Android File Manager.
"""

import sys
import traceback

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from adb_manager import AdbManager
from main_window import MainWindow
from styles import DARK_THEME_QSS


def exception_hook(exctype, value, tb):
    """Global exception hook to prevent silent crashes and print tracebacks."""
    print("Unhandled exception:", file=sys.stderr)
    traceback.print_exception(exctype, value, tb)
    sys.__excepthook__(exctype, value, tb)


def main():
    sys.excepthook = exception_hook

    # Enable high DPI attributes if supported
    app = QApplication(sys.argv)
    app.setApplicationName("Android File Manager")
    app.setApplicationDisplayName("Android File Manager")
    app.setOrganizationName("MacAndroidTools")

    # Apply Dark Mode Theme
    app.setStyleSheet(DARK_THEME_QSS)

    # Set Application Icon
    import os
    icon_path = os.path.join(os.path.dirname(__file__), "AppIcon.icns")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    # Initialize ADB and ensure daemon is started
    adb = AdbManager()
    adb.start_server()

    window = MainWindow(adb_manager=adb)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
