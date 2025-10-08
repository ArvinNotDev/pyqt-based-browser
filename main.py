from ui.browser_window import BrowserWindow
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
import sys
import os


if __name__ == "__main__":
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--no-sandbox --disable-gpu --disable-software-rasterizer"
    os.environ["QT_OPENGL"] = "software"
    os.environ["QTWEBENGINE_DISABLE_SANDBOX"] = "1"
    app = QApplication(sys.argv)
    window = BrowserWindow()
    window.showMaximized()
    sys.exit(app.exec())