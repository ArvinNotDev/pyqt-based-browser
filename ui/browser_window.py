from PySide6.QtWidgets import QMainWindow
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage
from PySide6.QtCore import QUrl
from .settings import Settings
from .navigation_bar import NavigationBar
from .settings_window import SettingsWindow
from .themes import light_theme, dark_theme
import os

class BrowserWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = Settings()
        self.settings.load(self.settings.profile.machine_id)

        os.makedirs("browser_cache", exist_ok=True)
        os.makedirs("browser_storage", exist_ok=True)

        self.profile = QWebEngineProfile(self.settings.profile.machine_id, self)
        self.profile.setPersistentCookiesPolicy(QWebEngineProfile.ForcePersistentCookies)
        self.profile.setCachePath("browser_cache")
        self.profile.setPersistentStoragePath("browser_storage")

        self.browser = QWebEngineView()
        page = QWebEnginePage(self.profile, self.browser)
        self.browser.setPage(page)
        self.setCentralWidget(self.browser)

        self.setWindowTitle("R-Browser")
        self.resize(self.settings.window_width, self.settings.window_height)
        self.navbar = NavigationBar()
        self.addToolBar(self.navbar)

        self.apply_theme()

        self.navbar.url_submitted.connect(self.navigate)
        self.navbar.home_clicked.connect(lambda: self.navigate(self.settings.homepage))
        self.navbar.back_btn.triggered.connect(self.browser.back)
        self.navbar.forward_btn.triggered.connect(self.browser.forward)
        self.navbar.reload_btn.triggered.connect(self.browser.reload)
        self.navbar.settings_btn.triggered.connect(self.open_settings)

        self.navigate(self.settings.homepage)

    def navigate(self, text):
        text = text.strip()
        if not text:
            return

        if " " in text or not "." in text:
            url = self.settings.default_search_engine + text.replace(" ", "+")
        else:
            if not text.startswith(("http://", "https://")):
                url = "https://" + text
            else:
                url = text

        self.browser.setUrl(QUrl(url))

    def open_settings(self):
        dialog = SettingsWindow(self.settings, self)
        if dialog.exec():
            self.apply_theme()
            self.navigate(self.settings.homepage)

    def apply_theme(self):
        """Apply full stylesheet from themes.py"""
        if self.settings.dark_mode:
            self.setStyleSheet(dark_theme)
        else:
            self.setStyleSheet(light_theme)
