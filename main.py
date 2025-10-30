from ui.browser_window import BrowserWindow
from PySide6.QtWidgets import QApplication
import sys


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = BrowserWindow()
    window.showMaximized()
    sys.exit(app.exec())