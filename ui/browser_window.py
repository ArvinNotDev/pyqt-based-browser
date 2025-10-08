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
        self.settings.load(self.settings.profile.machine_id)

        storage_path = os.path.join(os.getcwd(), "profile_data")
        os.makedirs(storage_path, exist_ok=True)


        self.profile = QWebEngineProfile(self.settings.profile.machine_id, self)
        self.profile.setPersistentCookiesPolicy(QWebEngineProfile.ForcePersistentCookies)
        self.profile.setCachePath(os.path.join(storage_path, "cache"))
        self.profile.setPersistentStoragePath(os.path.join(storage_path, "storage"))
        self.profile.setDownloadPath(os.path.join(storage_path, "downloads"))

        # === Set default browser-like behavior ===
        settings = self.profile.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.PluginsEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.FullScreenSupportEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.AutoLoadImages, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.FocusOnNavigationEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.ScrollAnimatorEnabled, True)

        self.page = QWebEnginePage(self.profile, self)
        self.browser = QWebEngineView()
        self.browser.setPage(self.page)

        # --- Navigation bar ---
        self.navbar = NavigationBar()

        # --- Progress bar under navbar ---
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximumHeight(5)  # thin bar
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setValue(0)
        self.progress_bar.setStyleSheet("QProgressBar {border: 0px;} QProgressBar::chunk {background-color: #29a3ef;}")

        # --- Layout for toolbar + progress bar ---
        container = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.navbar)
        layout.addWidget(self.progress_bar)
        container.setLayout(layout)
        self.setMenuWidget(container)  # top widget

        self.setCentralWidget(self.browser)
        self.setWindowTitle("R-Browser")
        self.resize(self.settings.window_width, self.settings.window_height)

        self.apply_theme()

        # --- Connect navbar ---
        self.navbar.url_submitted.connect(self.navigate)
        self.navbar.home_clicked.connect(lambda: self.navigate(self.settings.homepage))
        self.navbar.back_btn.triggered.connect(self.browser.back)
        self.navbar.forward_btn.triggered.connect(self.browser.forward)
        self.navbar.reload_btn.triggered.connect(self.browser.reload)
        self.navbar.settings_btn.triggered.connect(self.open_settings)

        # --- Connect loading signals to progress bar ---
        self.browser.loadStarted.connect(self._on_load_started)
        self.browser.loadProgress.connect(self._on_load_progress)
        self.browser.loadFinished.connect(self._on_load_finished)

        self.navigate(self.settings.homepage)

    def _on_load_started(self):
        self.progress_bar.setValue(0)
        self.progress_bar.show()

    def _on_load_progress(self, progress: int):
        self.progress_bar.setValue(progress)

    def _on_load_finished(self, ok: bool):
        self.progress_bar.setValue(100)
        self.progress_bar.hide()

    def navigate(self, url):
        url = url.strip()
        if not url:
            return

        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        self.browser.setUrl(QUrl(url))


    def open_settings(self):
        dialog = SettingsWindow(self.settings, self)
        if dialog.exec():
            self.apply_theme()
            self.navigate(self.settings.homepage)

    def apply_theme(self):
        if self.settings.dark_mode:
            self.setStyleSheet(dark_theme)
        else:
            self.setStyleSheet(light_theme)
