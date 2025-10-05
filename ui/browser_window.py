from PySide6.QtWidgets import QMainWindow
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtCore import QUrl
from .settings import Settings
from .navigation_bar import NavigationBar
from .settings_window import SettingsWindow
from .themes import light_theme, dark_theme

class BrowserWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = Settings()
        self.settings.load()

        # Window setup
        self.setWindowTitle("R-Browser")
        self.resize(self.settings.window_width, self.settings.window_height)

        # --- Browser setup ---
        self.browser = QWebEngineView()
        self.setCentralWidget(self.browser)

        # --- Navigation bar setup ---
        self.navbar = NavigationBar()
        self.addToolBar(self.navbar)

        # --- Applying theme ---
        self.apply_theme()

        # --- Signal connections ---
        self.navbar.url_submitted.connect(self.navigate)
        self.navbar.home_clicked.connect(lambda: self.navigate(self.settings.homepage))
        self.navbar.back_btn.triggered.connect(self.browser.back)
        self.navbar.forward_btn.triggered.connect(self.browser.forward)
        self.navbar.reload_btn.triggered.connect(self.browser.reload)
        self.navbar.settings_btn.triggered.connect(self.open_settings)

        # --- Load homepage ---
        self.navigate(self.settings.homepage)

    def navigate(self, url):
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        self.browser.setUrl(QUrl(url))
    
    def open_settings(self):
        dialog = SettingsWindow(self.settings, self)
        if dialog.exec():  # Note: exec_() in PyQt5 → exec() in PySide6
            self.apply_theme()
            self.navigate(self.settings.homepage)

    def apply_theme(self):
        if self.settings.dark_mode:
            window_bg = "#121212"
            toolbar_bg = "#1f1f1f"
            url_bg = "#2c2c2c"
            url_text = "#ffffff"
        else:
            window_bg = "#ffffff"
            toolbar_bg = "#f2f2f2"
            url_bg = "#ffffff"
            url_text = "#000000"

        # Apply to main window
        self.setStyleSheet(f"QMainWindow {{ background-color: {window_bg}; }}")

        # Apply to navigation bar
        self.navbar.apply_theme(toolbar_bg, url_bg, url_text)
