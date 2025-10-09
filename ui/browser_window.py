from PySide6.QtWidgets import QMainWindow, QProgressBar, QVBoxLayout, QWidget
from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEngineSettings, QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView
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
        self.selected_profile = "Guest"
        self.settings.load_profile_settings()
        self.settings.load(self.selected_profile)

        self.storage_path = os.path.join(os.getcwd(), "profile_data")
        os.makedirs(self.storage_path, exist_ok=True)

        self.navbar = NavigationBar(self.settings.profiles_list)
        self.navbar.profile_selected.connect(self.on_profile_selected)

        self.browser = QWebEngineView()
        self.page = None
        self.change_profile(self.selected_profile)

        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximumHeight(5)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setValue(0)
        self.progress_bar.setStyleSheet(
            "QProgressBar {border: 0px;} QProgressBar::chunk {background-color: #29a3ef;}"
        )

        container = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.navbar)
        layout.addWidget(self.progress_bar)
        container.setLayout(layout)
        self.setMenuWidget(container)

        self.setCentralWidget(self.browser)
        self.setWindowTitle("R-Browser")
        self.resize(self.settings.window_width, self.settings.window_height)

        self.apply_theme()

        self.navbar.url_submitted.connect(self.navigate)
        self.navbar.home_clicked.connect(lambda: self.navigate(self.settings.homepage))
        self.navbar.back_btn.triggered.connect(self.browser.back)
        self.navbar.forward_btn.triggered.connect(self.browser.forward)
        self.navbar.reload_btn.triggered.connect(self.browser.reload)
        self.navbar.settings_btn.triggered.connect(self.open_settings)

        self.browser.loadStarted.connect(self._on_load_started)
        self.browser.loadProgress.connect(self._on_load_progress)
        self.browser.loadFinished.connect(self._on_load_finished)

        self.navigate(self.settings.homepage)

    def change_profile(self, profile_name: str):
        self.selected_profile = profile_name

        profile_dir = os.path.join(self.storage_path, profile_name)
        os.makedirs(profile_dir, exist_ok=True)

        self.profile = QWebEngineProfile(profile_name, self)
        self.profile.setPersistentCookiesPolicy(QWebEngineProfile.ForcePersistentCookies)
        self.profile.setCachePath(os.path.join(profile_dir, "cache"))
        self.profile.setPersistentStoragePath(os.path.join(profile_dir, "storage"))
        self.profile.setDownloadPath(os.path.join(profile_dir, "downloads"))

        s = self.profile.settings()
        s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.PluginsEnabled, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.FullScreenSupportEnabled, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.AutoLoadImages, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.FocusOnNavigationEnabled, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False)
        s.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.ScrollAnimatorEnabled, True)

        self.page = QWebEnginePage(self.profile, self)
        self.browser.setPage(self.page)

        self.navbar.change_profile_orders(self.selected_profile)
        self.navbar.clear_url_bar()

    def on_profile_selected(self, profile_name: str):
        self.settings.save(self.selected_profile)

        self.selected_profile = profile_name
        self.settings.load(profile_name)

        self.change_profile(profile_name)

        self.apply_theme()
        self.navigate(self.settings.homepage)

    def _on_load_started(self):
        self.progress_bar.setValue(0)
        self.progress_bar.show()

    def _on_load_progress(self, progress: int):
        self.progress_bar.setValue(progress)

    def _on_load_finished(self, ok: bool):
        self.progress_bar.setValue(100)
        self.progress_bar.hide()

    def navigate(self, url: str):
        url = url.strip()
        if not url:
            return
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        self.browser.setUrl(QUrl(url))

    def open_settings(self):
        dialog = SettingsWindow(self.settings, self.selected_profile, self)
        if dialog.exec():
            self.apply_theme()

    def apply_theme(self):
        if self.settings.dark_mode:
            self.setStyleSheet(dark_theme)
        else:
            self.setStyleSheet(light_theme)
