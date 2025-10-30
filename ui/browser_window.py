from PySide6.QtWidgets import (
    QMainWindow, QProgressBar, QVBoxLayout, QWidget, QTabWidget
)
from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEngineSettings, QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtCore import QUrl, QTimer
from .settings import Settings
from .navigation_bar import NavigationBar
from .settings_window import SettingsWindow
from managers.history_manager import History
from .themes import light_theme, dark_theme
import os


class BrowserWindow(QMainWindow):
    def __init__(self):
        self.settings = Settings()
        self.settings.load_profile_settings()
        self.selected_profile = "Guest"
        self.history = History(self.selected_profile)
        if self.settings.profiles_list:
            if self.selected_profile not in self.settings.profiles_list:
                self.selected_profile = self.settings.profiles_list[0]
        self.settings.load(self.selected_profile)

        if self.settings.hardware_acceleration:
            self.settings.disable_hardware_acceleration()
        else:
            os.environ.pop("QTWEBENGINE_CHROMIUM_FLAGS", None)
            os.environ.pop("QTWEBENGINE_DISABLE_SANDBOX", None)
            os.environ["QT_OPENGL"] = "desktop"

        super().__init__()

        self.storage_path = os.path.join(os.getcwd(), "profile_data")
        os.makedirs(self.storage_path, exist_ok=True)

        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self.on_tab_changed)

        self.navbar = NavigationBar(self.settings.profiles_list, settings=self.settings)
        self.navbar.profile_selected.connect(self.on_profile_selected)
        self.navbar.new_tab_requested.connect(lambda: self.new_tab(self.settings.homepage))

        self.change_profile(self.selected_profile)

        self.new_tab(self.settings.homepage)

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

        self.setCentralWidget(self.tabs)
        self.setWindowTitle("R-Browser")
        self.resize(self.settings.window_width, self.settings.window_height)

        self.apply_theme()

        self.navbar.url_submitted.connect(self.navigate)
        self.navbar.home_clicked.connect(lambda: self.navigate(self.settings.homepage))
        self.navbar.back_btn.triggered.connect(lambda: self._do_on_current(lambda v: v.back()))
        self.navbar.forward_btn.triggered.connect(lambda: self._do_on_current(lambda v: v.forward()))
        self.navbar.reload_btn.triggered.connect(lambda: self._do_on_current(lambda v: v.reload()))
        self.navbar.settings_btn.triggered.connect(self.open_settings)
        self.navigate(self.settings.homepage)
        

    def new_tab(self, url):
        """Open a new tab with the current profile applied."""
        if isinstance(url, QUrl):
            url_q = url
        else:
            if not url.startswith(("http://", "https://")):
                url = "https://" + url
            url_q = QUrl(url)

        view = QWebEngineView()

        page = QWebEnginePage(self.profile, view)
        view.setPage(page)

        view.loadStarted.connect(lambda v=view: self._on_load_started(v))
        view.loadProgress.connect(lambda p, v=view: self._on_load_progress(p, v))
        view.loadFinished.connect(lambda ok, v=view: self._on_load_finished(ok, v))


        view.titleChanged.connect(lambda title, v=view: self.tabs.setTabText(self.tabs.indexOf(v), title[:30]))

        view.urlChanged.connect(lambda qurl, v=view: self._on_view_url_changed(qurl, v))

        index = self.tabs.addTab(view, "New Tab")
        self.tabs.setCurrentIndex(index)

        view.setUrl(url_q)

    def close_tab(self, index):
        if self.tabs.count() > 1:
            self.tabs.removeTab(index)
        else:
            self.close()

    def on_tab_changed(self, index):
        current_view = self.current_view()
        if current_view:
            self.update_url_bar(current_view.url())

    def current_view(self) -> QWebEngineView | None:
        widget = self.tabs.currentWidget()
        if isinstance(widget, QWebEngineView):
            return widget
        return None

    def _on_view_url_changed(self, qurl: QUrl, view):
        """Update url bar only if the view that changed is the active tab."""
        if view is self.current_view():
            self.update_url_bar(qurl)

    def _do_on_current(self, func):
        """Helper: execute func(current_view) if available."""
        v = self.current_view()
        if v:
            try:
                func(v)
            except Exception:
                pass

    def change_profile(self, profile_name: str):
        """Create or switch to a QWebEngineProfile and apply it to all open tabs."""
        self.selected_profile = profile_name
        self.history = History(self.selected_profile)

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

        for i in range(self.tabs.count()):
            view = self.tabs.widget(i)
            if isinstance(view, QWebEngineView):
                try:
                    new_page = QWebEnginePage(self.profile, view)
                    view.setPage(new_page)
                except Exception:
                    pass

        self.navbar.change_profile_orders(self.selected_profile)
        self.navbar.clear_url_bar()

    def on_profile_selected(self, profile_name: str):
        try:
            self.settings.save(self.selected_profile)
        except Exception:
            pass

        self.selected_profile = profile_name
        self.settings.load(profile_name)

        self.change_profile(profile_name)
        self.apply_theme()
        self.navigate(self.settings.homepage)

    def _on_load_started(self, view):
        if view is not self.current_view():
            return
        self.progress_bar.setRange(0, 0)
        self.progress_bar.show()
        try:
            self.statusBar().showMessage("Loading...", 0)
        except Exception:
            pass

    def _on_load_progress(self, progress: int, view):
        if view is not self.current_view():
            return
        if self.progress_bar.minimum() == 0 and self.progress_bar.maximum() == 0:
            self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(progress)
        if not self.progress_bar.isVisible():
            self.progress_bar.show()
        try:
            self.statusBar().showMessage(f"Loading... {progress}%")
        except Exception:
            pass

    def _on_load_finished(self, ok: bool, view):
        if view is not self.current_view():
            return
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        QTimer.singleShot(300, self.progress_bar.hide)
        if ok:
            try:
                self.statusBar().showMessage("Loaded", 1500)
            except Exception:
                pass
        else:
            try:
                self.statusBar().showMessage("Load failed", 3000)
            except Exception:
                pass

    def navigate(self, url: str):
        url = url.strip()
        if not url:
            return
        if " " in url or "." not in url:
            url = f"{self.settings.default_search_engine}{url.replace(' ', '+')}"
        else:
            if not url.startswith(("http://", "https://")):
                url = "https://" + url

        view = self.current_view()
        if view:
            self.history.add(url)
            view.setUrl(QUrl(url))
            self.update_url_bar(QUrl(url))

    def update_url_bar(self, qurl: QUrl):
        self.navbar.url_bar.setText(qurl.toString())

    def open_settings(self):
        dialog = SettingsWindow(self.settings, self.selected_profile, self)
        if dialog.exec():
            self.settings.load(self.selected_profile)
            self.apply_theme()

    def apply_theme(self):
        if self.settings.dark_mode:
            self.setStyleSheet(dark_theme)
        else:
            self.setStyleSheet(light_theme)
        try:
            self.navbar.apply_theme()
        except Exception:
            pass
