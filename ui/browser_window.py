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
        self.settings.load(self.settings.profile.machine_id)

        self.setWindowTitle("R-Browser")
        self.resize(self.settings.window_width, self.settings.window_height)

        self.browser = QWebEngineView()
        self.setCentralWidget(self.browser)

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

    def navigate(self, url):
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
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
