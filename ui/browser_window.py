import os
import re
import time
import logging
from typing import List, Optional, Dict

from PySide6.QtCore import (
    Qt, QUrl, QTimer, Signal, QPoint, QPropertyAnimation,
)
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QProgressBar, QFrame, QSizePolicy,
    QScrollArea, QGraphicsOpacityEffect, QDockWidget
)
from PySide6.QtGui import QPixmap, QAction, QKeySequence
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineSettings
from PySide6.QtWebEngineCore import QWebEngineFullScreenRequest

from .settings import Settings
from .navigation_bar import NavigationBar
from .settings_window import SettingsWindow
from .history_window import HistoryWindow
from managers.history_manager import History
from .themes import light_theme, dark_theme
from .url_utils import URLInputError, resolve_address_input
from proxy.ui import Window

try:
    from managers.bookmarks_manager import BookmarksManager
except ModuleNotFoundError as exc:
    if exc.name != "managers.bookmarks_manager":
        raise
    BookmarksManager = None

try:
    from managers.download_manager import DownloadManager
except ModuleNotFoundError as exc:
    if exc.name != "managers.download_manager":
        raise
    DownloadManager = None

try:
    from .bookmarks_bar import BookmarksBar
except ModuleNotFoundError as exc:
    if exc.name != "ui.bookmarks_bar":
        raise
    BookmarksBar = None

try:
    from .bookmarks_dialog import BookmarksDialog
except ModuleNotFoundError as exc:
    if exc.name != "ui.bookmarks_dialog":
        raise
    BookmarksDialog = None

try:
    from .downloads_dialog import DownloadsDialog
except ModuleNotFoundError as exc:
    if exc.name != "ui.downloads_dialog":
        raise
    DownloadsDialog = None
TAB_WIDTH = 160
TAB_HEIGHT = 34
TAB_SPACING = 4
SCROLL_STEP = 140
logger = logging.getLogger(__name__)


class TabButton(QFrame):
    clicked = Signal()
    closed = Signal()
    requested_preview = Signal()

    def __init__(self, title: str = "New Tab"):
        super().__init__()
        # give each tab a unique objectName so stylesheet selectors targeting this id
        # affect only this frame (and not other tab instances)
        self.setObjectName(f"tab_{int(id(self))}")
        self.setFixedSize(TAB_WIDTH, TAB_HEIGHT)
        self.setCursor(Qt.PointingHandCursor)

        self._active = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 6, 2)
        layout.setSpacing(6)

        self.label = QLabel(title)
        self.label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)

        self.close_btn = QPushButton("❌")
        self.close_btn.setFixedSize(18, 18)
        self.close_btn.setFocusPolicy(Qt.NoFocus)
        self.close_btn.setToolTip("Close tab")

        layout.addWidget(self.label)
        layout.addWidget(self.close_btn)
        self.close_btn.clicked.connect(lambda: self.closed.emit())

        self._hover_timer = QTimer(self)
        self._hover_timer.setSingleShot(True)
        self._hover_timer.setInterval(500)
        self._hover_timer.timeout.connect(self._emit_preview)

        # child styling (keeps children borderless / transparent)
        self._child_css = """
            QLabel { padding-left: 4px; padding-right: 4px; }
            QPushButton { border: none; background: transparent; padding: 0px; }
            QPushButton:hover { background: rgba(0,0,0,0.03); border-radius: 2px; }
        """

        # initialize inactive style (no top border)
        self.set_active(False)

    def _emit_preview(self):
        self.requested_preview.emit()

    def enterEvent(self, event):
        self._hover_timer.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover_timer.stop()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            if not self.close_btn.underMouse():
                self.clicked.emit()
        super().mouseReleaseEvent(event)

    def set_active(self, active: bool):
        self._active = active
        color = "#d9534f" if active else "transparent"
        # Target only this frame by id so children (label/button) don't get the border.
        # This ensures a single red line appears at the top of the tab only.
        style = f"""
            QFrame#{self.objectName()} {{ border-top: 3px solid {color}; }}
            {self._child_css}
        """
        self.setStyleSheet(style)

    def set_title(self, title: str):
        self.label.setText(title[:30] if title else "New Tab")


class CustomTabBar(QFrame):
    tab_changed = Signal(int)
    tab_closed = Signal(int)
    new_tab_requested = Signal()
    tab_preview_requested = Signal(int)

    def __init__(self):
        super().__init__()
        self.setFixedHeight(TAB_HEIGHT)
        self.tabs: List[TabButton] = []
        self.active_index: int = -1
        self.plus_inside = True
        self._updating = False

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.btn_left = QPushButton("◀")
        self.btn_left.setFixedSize(26, TAB_HEIGHT)
        self.btn_left.setFocusPolicy(Qt.NoFocus)
        self.btn_left.clicked.connect(lambda: self._scroll(-SCROLL_STEP))
        self.btn_left.hide()

        self.btn_right = QPushButton("▶")
        self.btn_right.setFixedSize(26, TAB_HEIGHT)
        self.btn_right.setFocusPolicy(Qt.NoFocus)
        self.btn_right.clicked.connect(lambda: self._scroll(SCROLL_STEP))
        self.btn_right.hide()

        self.holder = QWidget()
        self.holder_layout = QHBoxLayout(self.holder)
        self.holder_layout.setContentsMargins(0, 0, 0, 0)
        self.holder_layout.setSpacing(0)
        self.holder_layout.setAlignment(Qt.AlignLeft)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setWidget(self.holder)
        self.scroll.setFixedHeight(TAB_HEIGHT)
        self.scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self.plus_tab = QPushButton("+")
        self.plus_tab.setFixedSize(28, TAB_HEIGHT)
        self.plus_tab.setFocusPolicy(Qt.NoFocus)
        self.plus_tab.setToolTip("New tab")
        self.plus_tab.clicked.connect(lambda: self.new_tab_requested.emit())

        self.external_plus = QPushButton("+")
        self.external_plus.setFixedSize(28, TAB_HEIGHT)
        self.external_plus.setFocusPolicy(Qt.NoFocus)
        self.external_plus.setToolTip("New tab")
        self.external_plus.clicked.connect(lambda: self.new_tab_requested.emit())
        self.external_plus.hide()

        self.holder_layout.addWidget(self.plus_tab)

        root.addWidget(self.btn_left)
        root.addWidget(self.scroll, 1)
        root.addWidget(self.btn_right)
        root.addWidget(self.external_plus)

    def add_tab(self, title: str = "New Tab", make_active: bool = True) -> int:
        tab = TabButton(title)
        tab.clicked.connect(lambda t=tab: self._on_tab_clicked(t))
        tab.closed.connect(lambda t=tab: self._on_tab_closed(t))
        tab.requested_preview.connect(lambda t=tab: self._on_tab_preview_requested(t))

        insert_pos = max(0, self.holder_layout.count() - (1 if self.plus_inside else 0))
        self.holder_layout.insertWidget(insert_pos, tab)
        self.tabs.append(tab)

        idx = len(self.tabs) - 1
        if make_active or self.active_index < 0:
            self.set_active(idx)
        QTimer.singleShot(0, self._update_overflow)
        return idx

    def remove_tab(self, index: int, activate: bool = True):
        if index < 0 or index >= len(self.tabs):
            return
        old_active_index = self.active_index
        tab = self.tabs.pop(index)
        self.holder_layout.removeWidget(tab)
        tab.setParent(None)
        tab.deleteLater()

        if len(self.tabs) == 0:
            self.active_index = -1
            if activate and old_active_index != -1:
                self.tab_changed.emit(-1)
            QTimer.singleShot(0, self._update_overflow)
            return

        if self.active_index == index:
            self.active_index = min(index, len(self.tabs) - 1)
        elif self.active_index > index:
            self.active_index -= 1
        for i, tab_button in enumerate(self.tabs):
            tab_button.set_active(i == self.active_index)
        if activate and self.active_index != old_active_index:
            self.tab_changed.emit(self.active_index)
        QTimer.singleShot(0, self._update_overflow)

    def set_active(self, index: int):
        if not self.tabs:
            self.active_index = -1
            self.tab_changed.emit(-1)
            return
        index = max(0, min(index, len(self.tabs) - 1))
        changed = index != self.active_index
        self.active_index = index
        for i, t in enumerate(self.tabs):
            t.set_active(i == index)
        if changed:
            self.tab_changed.emit(index)
        QTimer.singleShot(0, lambda: self.ensure_tab_visible(index))

    def set_title(self, index: int, title: str):
        if 0 <= index < len(self.tabs):
            self.tabs[index].set_title(title)

    def ensure_tab_visible(self, index: int):
        if index < 0 or index >= len(self.tabs):
            return
        tab = self.tabs[index]
        try:
            local_x = tab.mapTo(self.holder, tab.rect().topLeft()).x()
            tab_w = tab.width()
            view_w = self.scroll.viewport().width()
            cur = self.scroll.horizontalScrollBar().value()
            if local_x < cur:
                self.scroll.horizontalScrollBar().setValue(local_x)
            elif local_x + tab_w > cur + view_w:
                self.scroll.horizontalScrollBar().setValue(local_x + tab_w - view_w)
        except RuntimeError:
            logger.debug("Skipped tab visibility update for a widget being destroyed", exc_info=True)

    def _scroll(self, delta: int):
        bar = self.scroll.horizontalScrollBar()
        bar.setValue(max(0, bar.value() + delta))

    def _update_overflow(self):
        if self._updating:
            return
        self._updating = True
        try:
            viewport = self.scroll.viewport().width()
            needed = len(self.tabs) * (TAB_WIDTH + TAB_SPACING) + self.plus_tab.width()
            overflow = needed > viewport

            self.btn_left.setVisible(overflow)
            self.btn_right.setVisible(overflow)

            if overflow and self.plus_inside:
                self.holder_layout.removeWidget(self.plus_tab)
                self.plus_tab.setParent(None)
                self.external_plus.show()
                self.plus_inside = False
            elif not overflow and not self.plus_inside:
                self.holder_layout.addWidget(self.plus_tab)
                self.plus_tab.setParent(self.holder)
                self.external_plus.hide()
                self.plus_inside = True
        finally:
            self._updating = False

    def _on_tab_clicked(self, tab: TabButton):
        if tab in self.tabs:
            self.set_active(self.tabs.index(tab))

    def _on_tab_closed(self, tab: TabButton):
        if tab in self.tabs:
            self.tab_closed.emit(self.tabs.index(tab))

    def _on_tab_preview_requested(self, tab: TabButton):
        try:
            idx = self.tabs.index(tab)
        except ValueError:
            return
        if idx != self.active_index:
            self.tab_preview_requested.emit(idx)


class BrowserPage(QWebEnginePage):
    """Page that routes web requests for a new window into a browser tab."""

    def __init__(self, browser: "BrowserWindow", profile: QWebEngineProfile, parent):
        super().__init__(profile, parent)
        self.browser = browser

    def createWindow(self, window_type):
        index = self.browser.new_tab("about:blank", make_active=True)
        if 0 <= index < len(self.browser.views):
            return self.browser.views[index].page()
        return None


class BrowserWindow(QMainWindow):
    def __init__(self, proxy_port: Optional[int] = None):
        super().__init__()
        self.proxy_panel = Window(self, None)
        proxy_widget = self.proxy_panel.proxyWidget
        if proxy_port is not None:
            # main.py chooses this port and sets Chromium's flag before Qt starts.
            proxy_widget.proxy_port = proxy_port
            proxy_widget.proxy.port = proxy_port
        else:
            logger.warning(
                "BrowserWindow was created without a preconfigured Chromium proxy port; "
                "launch through main.py for proxy startup before Qt initialization."
            )
        try:
            proxy_widget.proxy.start()
        except OSError:
            logger.exception("Could not start the browser proxy listener")


        self.settings = Settings()
        self.settings.load_profile_settings()
        self.selected_profile = "Guest"
        if self.settings.profiles_list and self.selected_profile not in self.settings.profiles_list:
            self.selected_profile = self.settings.profiles_list[0]
        self.settings.load(self.selected_profile)

        self._closed_tab_urls: List[str] = []
        self._browser_shortcuts: Dict[QAction, list[QKeySequence]] = {}
        self._ui_shortcut_actions: set[QAction] = set()
        self._gaming_mode_active = False
        self._closing = False

        self.history: Optional[History] = None
        self._refresh_history()

        self.storage_path = os.path.join(os.getcwd(), "profile_data")
        if not self.settings.private_mode:
            os.makedirs(self.storage_path, exist_ok=True)

        self._profiles: Dict[tuple[str, bool], QWebEngineProfile] = {}
        self._profile_default_user_agents: Dict[int, str] = {}
        self.profile = self._get_profile(self.selected_profile)
        self._apply_profile_settings(self.profile)
        self._download_managers = {}
        self._setup_feature_managers()

        self.navbar = NavigationBar(self.settings.profiles_list, settings=self.settings)
        self.navbar.history = self.history.history if self.history else {}
        self.navbar.profile_selected.connect(self.on_profile_selected)
        self.navbar.new_tab_requested.connect(lambda: self.new_tab(self.settings.homepage))

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(4)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setStyleSheet("QProgressBar::chunk { background-color: #29a3ef; }")
        self.progress_bar.hide()

        self.tabbar = CustomTabBar()
        self.tabbar.new_tab_requested.connect(lambda: self.new_tab(self.settings.homepage))
        self.tabbar.tab_changed.connect(self._on_tab_changed)
        # connect to our custom close flow
        self.tabbar.tab_closed.connect(self.request_close_tab)
        self.tabbar.tab_preview_requested.connect(self._show_tab_preview)

        self.views: List[QWebEngineView] = []
        self._placeholders: Dict[QWebEngineView, QWidget] = {}
        self._snapshots: Dict[QWebEngineView, QPixmap] = {}
        self._recorded_history_urls: Dict[QWebEngineView, str] = {}
        self.current_index: int = -1
        self.view_container = QWidget()
        self.view_layout = QVBoxLayout(self.view_container)
        self.view_layout.setContentsMargins(0, 0, 0, 0)

        self._preview_label = QLabel(self)
        self._preview_label.setWindowFlags(Qt.ToolTip)
        self._preview_label.setStyleSheet("border:1px solid #222; background-color: white;")
        self._preview_label.setScaledContents(True)
        self._preview_label.hide()
        self._preview_animation = QPropertyAnimation(self._preview_label, b"windowOpacity")
        self._preview_animation.setDuration(180)

        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.navbar)
        if self.bookmarks_bar is not None:
            layout.addWidget(self.bookmarks_bar)
        layout.addWidget(self.tabbar)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.view_container)
        self.setCentralWidget(root)

        self.resize(self.settings.window_width, self.settings.window_height)
        self.setWindowTitle("R-Browser")
        self.apply_theme()

        try:
            self.navbar.url_submitted.connect(self.navigate)
            self.navbar.home_clicked.connect(lambda: self.navigate(self.settings.homepage))
            if hasattr(self.navbar, "back_btn"):
                self.navbar.back_btn.triggered.connect(lambda: self._do_on_current(lambda v: v.back()))
            if hasattr(self.navbar, "forward_btn"):
                self.navbar.forward_btn.triggered.connect(lambda: self._do_on_current(lambda v: v.forward()))
            if hasattr(self.navbar, "reload_btn"):
                self.navbar.reload_btn.triggered.connect(lambda: self._do_on_current(lambda v: v.reload()))
            if hasattr(self.navbar, "settings_btn"):
                self.navbar.settings_btn.triggered.connect(self.open_settings)
            if hasattr(self.navbar, "bookmark_requested"):
                self.navbar.bookmark_requested.connect(self._add_current_bookmark)
            if hasattr(self.navbar, "show_bookmarks_requested"):
                self.navbar.show_bookmarks_requested.connect(self.show_bookmarks)
            if hasattr(self.navbar, "show_history_requested"):
                self.navbar.show_history_requested.connect(self.show_history)
            if hasattr(self.navbar, "show_downloads_requested"):
                self.navbar.show_downloads_requested.connect(self.show_downloads)
        except (AttributeError, RuntimeError):
            logger.exception("Could not connect one or more navigation actions")

        QTimer.singleShot(0, lambda: self.new_tab(self.settings.homepage))
        self._last_progress_ts = 0
        
        self.dock = QDockWidget("Proxy", self)
        self.dock.setObjectName("proxyDock")
        self.dock.setMinimumWidth(300)
        self.dock.setMaximumWidth(400)
        self.dock.setWidget(self.proxy_panel)
        self.dock.setFloating(False)
        self.dock.setFeatures(QDockWidget.DockWidgetClosable)
        self.addDockWidget(Qt.RightDockWidgetArea, self.dock)
        self.dock.setVisible(bool(self.settings.proxy_panel_visible))
        self.dock.visibilityChanged.connect(self._on_proxy_visibility_changed)
        self.navbar.proxy_panel_requested.connect(self.show_proxy)
        self.navbar.gaming_mode_toggled.connect(self._set_gaming_mode)
        self._update_proxy_menu_action(bool(self.settings.proxy_panel_visible))
        self._install_browser_shortcuts()

    def show_proxy(self):
        self.dock.setVisible(not self.dock.isVisible())
        if self.dock.isVisible():
            self.dock.raise_()

    def _update_proxy_menu_action(self, visible: bool) -> None:
        self.navbar.proxy_panel_action.setText("Hide proxy panel" if visible else "Show proxy panel")

    def _on_proxy_visibility_changed(self, visible: bool) -> None:
        self._update_proxy_menu_action(visible)
        if self._closing or bool(self.settings.proxy_panel_visible) == bool(visible):
            return
        self.settings.proxy_panel_visible = bool(visible)
        try:
            self.settings.save(self.selected_profile)
        except (OSError, ValueError, TypeError):
            logger.exception("Could not save proxy panel visibility")

    def _install_browser_shortcuts(self) -> None:
        """Install Chrome-style browser shortcuts that Gaming mode can pause."""
        for action, sequences in (
            (self.navbar.new_tab_action, ["Ctrl+T"]),
            (self.navbar.bookmark_action, ["Ctrl+D"]),
            (self.navbar.show_history_action, ["Ctrl+H"]),
            (self.navbar.show_downloads_action, ["Ctrl+J"]),
            (self.navbar.settings_btn, ["Ctrl+,"]),
            (self.navbar.back_btn, ["Alt+Left"]),
            (self.navbar.forward_btn, ["Alt+Right"]),
            (self.navbar.reload_btn, ["Ctrl+R", "F5"]),
            (self.navbar.home_btn, ["Alt+Home"]),
        ):
            self._register_browser_shortcut(action, sequences, ui_action=True)

        self._add_shortcut("Close tab", ["Ctrl+W"], self._close_current_tab)
        self._add_shortcut("Reopen closed tab", ["Ctrl+Shift+T"], self._reopen_closed_tab)
        self._add_shortcut("Next tab", ["Ctrl+Tab", "Ctrl+PageDown"], lambda: self._cycle_tabs(1))
        self._add_shortcut(
            "Previous tab", ["Ctrl+Shift+Tab", "Ctrl+PageUp"], lambda: self._cycle_tabs(-1)
        )
        self._add_shortcut("Focus address bar", ["Ctrl+L", "Alt+D"], self.navbar._focus_url_bar)
        for number in range(1, 9):
            self._add_shortcut(
                f"Switch to tab {number}",
                [f"Ctrl+{number}"],
                lambda tab_number=number: self._switch_to_tab(tab_number),
            )
        self._add_shortcut("Switch to last tab", ["Ctrl+9"], lambda: self._switch_to_tab(9))

    def _register_browser_shortcut(
        self, action: QAction, sequences: list[str], *, ui_action: bool = False,
        callback=None,
    ) -> None:
        key_sequences = [QKeySequence(sequence) for sequence in sequences]
        action.setShortcuts(key_sequences)
        action.setShortcutContext(Qt.WindowShortcut)
        if callback is not None:
            action.triggered.connect(lambda _checked=False: callback())
        self.addAction(action)
        self._browser_shortcuts[action] = key_sequences
        if ui_action:
            self._ui_shortcut_actions.add(action)

    def _add_shortcut(self, label: str, sequences: list[str], callback) -> QAction:
        action = QAction(label, self)
        self._register_browser_shortcut(action, sequences, callback=callback)
        return action

    def _set_gaming_mode(self, enabled: bool) -> None:
        self._gaming_mode_active = bool(enabled)
        for action, sequences in self._browser_shortcuts.items():
            action.setShortcuts([] if enabled else sequences)
            if action not in self._ui_shortcut_actions:
                action.setEnabled(not enabled)

        self.navbar.menu_button.setProperty("gamingMode", bool(enabled))
        self.navbar.menu_button.setToolTip(
            "Gaming mode is on — browser shortcuts are paused" if enabled else "Browser menu"
        )
        self.navbar.menu_button.style().unpolish(self.navbar.menu_button)
        self.navbar.menu_button.style().polish(self.navbar.menu_button)
        self.statusBar().showMessage(
            "Gaming mode on · browser shortcuts paused" if enabled else "Gaming mode off",
            2500,
        )

    def _close_current_tab(self) -> None:
        if self.current_index >= 0:
            self.request_close_tab(self.current_index)

    def _reopen_closed_tab(self) -> None:
        if self._closed_tab_urls:
            self.new_tab(self._closed_tab_urls.pop())

    def _cycle_tabs(self, offset: int) -> None:
        if self.views:
            self.tabbar.set_active((self.current_index + offset) % len(self.views))

    def _switch_to_tab(self, number: int) -> None:
        if self.views:
            index = len(self.views) - 1 if number == 9 else number - 1
            if index < len(self.views):
                self.tabbar.set_active(index)

    def show_history(self) -> None:
        if self.history is None:
            self.statusBar().showMessage("History is unavailable in this session.", 3000)
            return
        HistoryWindow(self.selected_profile, self.history, self).exec()

    def _refresh_history(self):
        if self.settings.private_mode or not self.settings.save_history:
            self.history = None
        else:
            self.history = History(self.selected_profile)
        if hasattr(self, "navbar"):
            self.navbar.history = self.history.history if self.history else {}

    def _get_profile(self, profile_name: str) -> QWebEngineProfile:
        private_mode = bool(self.settings.private_mode)
        key = (profile_name, private_mode)
        profile = self._profiles.get(key)
        if profile is None:
            if private_mode:
                # The unnamed profile is off-the-record and keeps storage in memory.
                profile = QWebEngineProfile(self)
            else:
                profile = QWebEngineProfile(profile_name, self)
            self._profiles[key] = profile
        return profile

    def _apply_profile_settings(self, profile: QWebEngineProfile):
        private_mode = bool(self.settings.private_mode)
        persistent_cookies = (
            not private_mode and bool(self.settings.save_cookies)
        )
        policy = (
            QWebEngineProfile.ForcePersistentCookies
            if persistent_cookies
            else QWebEngineProfile.NoPersistentCookies
        )
        profile.setPersistentCookiesPolicy(policy)

        profile_key = id(profile)
        default_user_agent = self._profile_default_user_agents.setdefault(
            profile_key, profile.httpUserAgent()
        )
        if self.settings.site_compatibility_mode:
            compatible_user_agent = re.sub(
                r"\s+QtWebEngine/[^\s]+", "", default_user_agent, flags=re.IGNORECASE
            )
            profile.setHttpUserAgent(compatible_user_agent)
        else:
            profile.setHttpUserAgent(default_user_agent)

        if not private_mode:
            profile_dir = os.path.join(self.storage_path, self.selected_profile)
            os.makedirs(profile_dir, exist_ok=True)
            profile.setCachePath(os.path.join(profile_dir, "cache"))
            profile.setPersistentStoragePath(os.path.join(profile_dir, "storage"))
            download_dir = os.path.abspath(os.path.expanduser(self.settings.download_folder))
            os.makedirs(download_dir, exist_ok=True)
            profile.setDownloadPath(download_dir)

        settings = profile.settings()
        settings.setAttribute(QWebEngineSettings.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.LocalStorageEnabled, True)
        settings.setAttribute(QWebEngineSettings.FullScreenSupportEnabled, True)

    def _setup_feature_managers(self):
        self.bookmarks_manager = None
        if BookmarksManager is not None:
            try:
                self.bookmarks_manager = BookmarksManager(self.selected_profile)
            except Exception:
                logger.exception("Could not initialize bookmarks for profile %s", self.selected_profile)

        self.download_manager = None
        if DownloadManager is not None and not self.settings.private_mode:
            try:
                self.download_manager = self._download_managers.get(self.selected_profile)
                if self.download_manager is None:
                    self.download_manager = DownloadManager(
                        self.selected_profile,
                        download_dir=self.settings.download_folder,
                    )
                    self._download_managers[self.selected_profile] = self.download_manager
                self.download_manager.attach_profile(self.profile)
            except Exception:
                logger.exception("Could not initialize downloads for profile %s", self.selected_profile)
                self.download_manager = None

        if not hasattr(self, "bookmarks_bar"):
            self.bookmarks_bar = (
                BookmarksBar()
                if BookmarksBar is not None and self.bookmarks_manager is not None
                else None
            )
            if self.bookmarks_bar is not None:
                self.bookmarks_bar.url_activated.connect(self.navigate)
                self.bookmarks_bar.manage_requested.connect(self.show_bookmarks)
        self._refresh_bookmarks()

    def _refresh_bookmarks(self):
        if self.bookmarks_bar is None or self.bookmarks_manager is None:
            return
        try:
            self.bookmarks_bar.set_bookmarks(self.bookmarks_manager.list_bookmarks())
        except Exception:
            logger.exception("Could not refresh bookmarks for profile %s", self.selected_profile)
            self.statusBar().showMessage("Could not refresh bookmarks.", 3000)

    def _add_current_bookmark(self, *args):
        if self.bookmarks_manager is None:
            self.statusBar().showMessage("Bookmarks are unavailable.", 3000)
            return
        view = self.current_view()
        if view is None:
            return
        url = view.url().toString()
        title = view.title().strip() or url
        try:
            bookmark = self.bookmarks_manager.get_bookmark_for_url(url)
            if bookmark is not None:
                self.bookmarks_manager.remove_bookmark(bookmark["id"])
            else:
                self.bookmarks_manager.add_bookmark(title, url)
            self._refresh_bookmarks()
            self.navbar.set_bookmark_state(self.bookmarks_manager.is_bookmarked(url))
        except Exception:
            logger.exception("Could not toggle bookmark for %s", url)
            self.statusBar().showMessage("Could not update bookmark.", 3000)

    def show_bookmarks(self, *args):
        if BookmarksDialog is None or self.bookmarks_manager is None:
            self.statusBar().showMessage("Bookmarks are unavailable.", 3000)
            return
        try:
            dialog = BookmarksDialog(self.bookmarks_manager, self)
            dialog.url_activated.connect(self.navigate)
            dialog.exec()
            self._refresh_bookmarks()
        except Exception:
            logger.exception("Could not open bookmarks")
            self.statusBar().showMessage("Could not open bookmarks.", 3000)

    def show_downloads(self, *args):
        if DownloadsDialog is None or self.download_manager is None:
            self.statusBar().showMessage("Downloads are unavailable in this session.", 3000)
            return
        try:
            DownloadsDialog(self.download_manager, self).exec()
        except Exception:
            logger.exception("Could not open downloads")
            self.statusBar().showMessage("Could not open downloads.", 3000)

    def _capture_snapshot(self, view: QWebEngineView):
        if view not in self.views:
            return
        try:
            pix = view.grab()
            if pix and not pix.isNull():
                self._snapshots[view] = pix
        except RuntimeError:
            logger.debug("Skipped snapshot for a view being destroyed", exc_info=True)

    def _make_placeholder(self, url_text: str = "") -> QWidget:
        # lightweight placeholder shown until the QWebEngineView is ready
        lbl = QLabel()
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setText("Loading...")
        lbl.setFixedHeight(400)  # minimal size hint, will expand with layout
        # optional: add a small spinner using QMovie if desired (commented-out default)
        # movie = QMovie(":/icons/spinner.gif")
        # lbl.setMovie(movie)
        # movie.start()
        lbl.setStyleSheet("background: #f6f6f6; color: #444;")
        return lbl

    def new_tab(self, url: Optional[str] = None, make_active: bool = True) -> int:
        """Create one aligned tab, placeholder, view, and page before loading."""
        raw_url = url.toString() if isinstance(url, QUrl) else (url or "about:blank")
        try:
            resolved_url = resolve_address_input(raw_url, self.settings.default_search_engine)
        except URLInputError as exc:
            logger.warning("Rejected tab URL %r: %s", raw_url, exc)
            self.statusBar().showMessage(str(exc), 5000)
            resolved_url = "about:blank"
        url_q = QUrl(resolved_url)

        view = QWebEngineView(self.view_container)
        view.setVisible(False)
        view.setAttribute(Qt.WA_TranslucentBackground, True)
        page = BrowserPage(self, self.profile, view)
        view.setPage(page)
        self._connect_page(view, page)

        placeholder = self._make_placeholder(url_q.toString())
        self.views.append(view)
        self._placeholders[view] = placeholder
        self.view_layout.addWidget(placeholder)
        self.view_layout.addWidget(view)

        index = len(self.views) - 1
        self.tabbar.add_tab("New Tab", make_active=False)
        if make_active or self.current_index < 0:
            self.tabbar.set_active(index)
        else:
            self._set_tab_visibility()

        view.setUrl(url_q)
        return index

    def _connect_page(self, view: QWebEngineView, page: QWebEnginePage) -> None:
        page.titleChanged.connect(
            lambda title, v=view, p=page: self._on_title_changed(title, v)
            if self._page_is_current(v, p) else None
        )
        page.urlChanged.connect(
            lambda url, v=view, p=page: self._on_view_url_changed(url, v)
            if self._page_is_current(v, p) else None
        )
        page.loadStarted.connect(
            lambda v=view, p=page: self._on_load_started(v)
            if self._page_is_current(v, p) else None
        )
        page.loadProgress.connect(
            lambda progress, v=view, p=page: self._on_load_progress(progress, v)
            if self._page_is_current(v, p) else None
        )
        page.loadFinished.connect(
            lambda ok, v=view, p=page: self._on_load_finished_with_swap(ok, v, p)
            if self._page_is_current(v, p) else None
        )
        page.fullScreenRequested.connect(
            lambda request, v=view, p=page: self._handle_page_fullscreen(request, v, p)
        )
        page.windowCloseRequested.connect(
            lambda v=view, p=page: self.request_close_tab(self.views.index(v))
            if self._page_is_current(v, p) else None
        )

    def _page_is_current(self, view: QWebEngineView, page: QWebEnginePage) -> bool:
        return view in self.views and view.page() is page

    def request_close_tab(self, index: int):
        """Remove a tab and all of its widgets as one GUI-thread transition."""
        if index < 0 or index >= len(self.views):
            return

        closing_view = self.views.pop(index)
        closed_url = closing_view.url().toString().strip()
        if closed_url and closed_url != "about:blank":
            self._closed_tab_urls.append(closed_url)
            self._closed_tab_urls = self._closed_tab_urls[-10:]
        was_active = index == self.current_index
        self.tabbar.remove_tab(index, activate=False)
        placeholder = self._placeholders.pop(closing_view, None)
        if placeholder is not None:
            self.view_layout.removeWidget(placeholder)
            placeholder.hide()
            placeholder.deleteLater()

        self.view_layout.removeWidget(closing_view)
        closing_view.stop()
        closing_view.hide()
        closing_view.deleteLater()
        self._snapshots.pop(closing_view, None)
        self._recorded_history_urls.pop(closing_view, None)

        if not self.views:
            # Keep the browser usable when the last tab is closed.
            self.current_index = -1
            self.new_tab(self.settings.homepage)
            return

        if was_active:
            next_index = min(index, len(self.views) - 1)
        elif index < self.current_index:
            next_index = self.current_index - 1
        else:
            next_index = self.current_index
        self.current_index = -1
        self.tabbar.set_active(next_index)
        self._activate(next_index)

    def close_tab(self, index: int):
        """
        Backwards-compatible external call — redirect to request_close_tab
        """
        self.request_close_tab(index)

    def _activate(self, index: int):
        if index < 0 or index >= len(self.views):
            return
        prev_index = self.current_index
        if prev_index is not None and prev_index != -1 and prev_index != index:
            self._capture_snapshot(self.views[prev_index])

        self.current_index = index
        self._set_tab_visibility()
        view = self.views[index]
        self.navbar.url_bar.setText(view.url().toString())
        if self.bookmarks_manager is not None:
            self.navbar.set_bookmark_state(self.bookmarks_manager.is_bookmarked(view.url().toString()))
        self._update_navigation_actions(view)
        self.tabbar.set_active(index)

    def _set_tab_visibility(self):
        for index, view in enumerate(self.views):
            placeholder = self._placeholders.get(view)
            is_active = index == self.current_index
            if placeholder is not None:
                placeholder.setVisible(is_active)
                view.setVisible(is_active and view.graphicsEffect() is not None)
            else:
                view.setVisible(is_active)

    def _on_tab_changed(self, index: int):
        if index >= 0 and index != self.current_index:
            self._activate(index)

    def _on_title_changed(self, title: str, view: QWebEngineView):
        if view not in self.views:
            return
        self.tabbar.set_title(self.views.index(view), title)

    def _on_view_url_changed(self, url: QUrl, view: QWebEngineView):
        if view is self.current_view():
            self.navbar.url_bar.setText(url.toString())
            if self.bookmarks_manager is not None:
                self.navbar.set_bookmark_state(self.bookmarks_manager.is_bookmarked(url.toString()))
            self._update_navigation_actions(view)

    def _on_load_started(self, view: QWebEngineView):
        if view not in self.views:
            return
        if view is self.current_view():
            self.progress_bar.setRange(0, 0)
            self.progress_bar.show()
            self.statusBar().showMessage("Loading...", 0)

    def _on_load_progress(self, progress: int, view):
        if view is not self.current_view():
            return

        now = time.monotonic()
        if now - self._last_progress_ts < 0.05:  # 50ms
            return
        self._last_progress_ts = now

        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(progress)


    def _on_load_finished_with_swap(self, ok: bool, view: QWebEngineView, page: QWebEnginePage):
        if not self._page_is_current(view, page):
            return

        if view is self.current_view():
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(100)
            QTimer.singleShot(300, lambda v=view: self._hide_progress_if_current(v))
            self.statusBar().showMessage("Loaded" if ok else "Load failed", 1500 if ok else 3000)

        if ok and self.history is not None:
            url_text = view.url().toString()
            if url_text.startswith(("http://", "https://")) and self._recorded_history_urls.get(view) != url_text:
                try:
                    self.history.add(url_text)
                    self._recorded_history_urls[view] = url_text
                except OSError:
                    logger.exception("Could not save browsing history for %s", url_text)

        self._update_navigation_actions(view)
        QTimer.singleShot(100, lambda v=view: self._capture_snapshot(v))
        placeholder = self._placeholders.get(view)
        if placeholder is None:
            view.setVisible(view is self.current_view())
            return

        view_effect = QGraphicsOpacityEffect(view)
        view.setGraphicsEffect(view_effect)
        view_effect.setOpacity(0.0)
        placeholder_effect = QGraphicsOpacityEffect(placeholder)
        placeholder.setGraphicsEffect(placeholder_effect)
        placeholder_effect.setOpacity(1.0)
        view.setVisible(view is self.current_view())

        anim_out = QPropertyAnimation(placeholder_effect, b"opacity", self)
        anim_out.setDuration(220)
        anim_out.setStartValue(1.0)
        anim_out.setEndValue(0.0)
        anim_in = QPropertyAnimation(view_effect, b"opacity", self)
        anim_in.setDuration(260)
        anim_in.setStartValue(0.0)
        anim_in.setEndValue(1.0)

        def finish_swap():
            if self._placeholders.get(view) is not placeholder:
                return
            self._placeholders.pop(view, None)
            self.view_layout.removeWidget(placeholder)
            placeholder.deleteLater()
            view.setGraphicsEffect(None)
            self._set_tab_visibility()

        anim_out.finished.connect(anim_in.start)
        anim_in.finished.connect(finish_swap)
        anim_out.start()

    def _hide_progress_if_current(self, view: QWebEngineView) -> None:
        if view in self.views and view is self.current_view() and not view.page().isLoading():
            self.progress_bar.hide()

    def _update_navigation_actions(self, view: QWebEngineView) -> None:
        if view is not self.current_view():
            return
        history = view.history()
        self.navbar.back_btn.setEnabled(history.canGoBack())
        self.navbar.forward_btn.setEnabled(history.canGoForward())

    def _handle_page_fullscreen(self, request, view: QWebEngineView, page: QWebEnginePage):
        if not self._page_is_current(view, page):
            request.reject()
            return
        self.handle_fullscreen(request)

    def _show_tab_preview(self, index: int):
        if index < 0 or index >= len(self.views) or index == self.current_index:
            return

        view = self.views[index]
        pix = self._snapshots.get(view)
        if pix is None:
            try:
                pix = view.grab()
            except RuntimeError:
                logger.debug("Skipped preview for a view being destroyed", exc_info=True)
                pix = None

        if pix is None or pix.isNull():
            pix = QPixmap(TAB_WIDTH * 2, 120)
            pix.fill(Qt.gray)

        scaled = pix.scaled(320, 220, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self._preview_label.setPixmap(scaled)
        self._preview_label.adjustSize()

        try:
            tab_widget = self.tabbar.tabs[index]
            global_pos = tab_widget.mapToGlobal(tab_widget.rect().bottomLeft())
            x = global_pos.x()
            y = global_pos.y() + 8

            screen_rect = self.screen().availableGeometry()
            if x + self._preview_label.width() > screen_rect.right():
                x = screen_rect.right() - self._preview_label.width() - 8
            if y + self._preview_label.height() > screen_rect.bottom():
                y = global_pos.y() - self._preview_label.height() - 8
            if x < screen_rect.left():
                x = screen_rect.left() + 8
            if y < screen_rect.top():
                y = screen_rect.top() + 8

            self._preview_label.move(x, y)
        except RuntimeError:
            center = self.mapToGlobal(self.rect().center())
            self._preview_label.move(center + QPoint(-160, 40))

        self._preview_label.setWindowOpacity(0.0)
        self._preview_label.show()
        self._preview_animation.stop()
        self._preview_animation.setStartValue(0.0)
        self._preview_animation.setEndValue(1.0)
        self._preview_animation.start()
        QTimer.singleShot(1500, lambda: self._fade_out_preview())

    def _fade_out_preview(self):
        self._preview_animation.stop()
        self._preview_animation.setStartValue(1.0)
        self._preview_animation.setEndValue(0.0)
        self._preview_animation.start()
        QTimer.singleShot(200, self._preview_label.hide)

    def _do_on_current(self, func):
        v = self.current_view()
        if v:
            try:
                func(v)
            except RuntimeError:
                logger.exception("Navigation action failed because its page was destroyed")

    def current_view(self) -> Optional[QWebEngineView]:
        if 0 <= self.current_index < len(self.views):
            return self.views[self.current_index]
        return None

    def change_profile(self, profile_name: str):
        self.selected_profile = profile_name
        self._refresh_history()
        self.profile = self._get_profile(profile_name)
        self._apply_profile_settings(self.profile)
        self.proxy_panel.profile = self.profile
        self._setup_feature_managers()

        for view in list(self.views):
            old_page = view.page()
            current_url = view.url()
            new_page = BrowserPage(self, self.profile, view)
            view.setPage(new_page)
            self._connect_page(view, new_page)
            if old_page is not None:
                try:
                    old_page.deleteLater()
                except RuntimeError:
                    logger.debug("Old profile page was already destroyed", exc_info=True)
            view.setUrl(current_url if current_url.isValid() else QUrl("about:blank"))
            self._recorded_history_urls.pop(view, None)

        self.navbar.history = self.history.history if self.history else {}
        self.navbar.change_profile_orders(self.selected_profile)
        self.navbar.clear_url_bar()
        if self.current_view() is not None:
            self.navbar.url_bar.setText(self.current_view().url().toString())
            self._update_navigation_actions(self.current_view())

    def on_profile_selected(self, profile_name: str):
        try:
            self.settings.save(self.selected_profile)
        except (OSError, ValueError):
            logger.exception("Could not save settings for profile %s", self.selected_profile)
        self.selected_profile = profile_name
        new_settings = Settings(file_path=self.settings.file_path, profiles_list=self.settings.profiles_list)
        new_settings.load(profile_name)
        self.settings = new_settings
        self.navbar.settings = new_settings
        self.change_profile(profile_name)
        self.dock.setVisible(bool(self.settings.proxy_panel_visible))
        self.apply_theme()
        self.new_tab(self.settings.homepage)

    def navigate(self, url: str):
        if isinstance(url, QUrl):
            url = url.toString()
        if not isinstance(url, str):
            self.statusBar().showMessage("The selected address is invalid.", 5000)
            return
        try:
            resolved_url = resolve_address_input(url, self.settings.default_search_engine)
        except URLInputError as exc:
            self.statusBar().showMessage(str(exc), 5000)
            logger.info("Rejected address bar input %r: %s", url, exc)
            return
        view = self.current_view()
        if view:
            view.setUrl(QUrl(resolved_url))
            self.navbar.url_bar.setText(resolved_url)

    def update_url_bar(self, qurl: QUrl):
        self.navbar.url_bar.setText(qurl.toString())

    def open_settings(self):
        dialog = SettingsWindow(self.settings, self.selected_profile, self.history, self)
        if self.settings.private_mode:
            dialog.history_btn.setEnabled(False)
            dialog.history_btn.setToolTip("History is unavailable in a private session.")
        if dialog.exec():
            previous_private_mode = bool(self.settings.private_mode)
            self.settings.load(self.selected_profile)
            self._refresh_history()
            self.dock.setVisible(bool(self.settings.proxy_panel_visible))
            if previous_private_mode != bool(self.settings.private_mode):
                self.change_profile(self.selected_profile)
            else:
                self._apply_profile_settings(self.profile)
                self._setup_feature_managers()
            self.apply_theme()

    def apply_theme(self):
        try:
            theme = dark_theme if getattr(self.settings, "dark_mode", False) else light_theme
            self.setStyleSheet(theme)
            if hasattr(self.navbar, "apply_theme"):
                self.navbar.apply_theme()
        except RuntimeError:
            logger.exception("Could not apply the current browser theme")
    
    def closeEvent(self, event):
        self._closing = True
        for download_manager in self._download_managers.values():
            download_manager.shutdown()
        views = list(self.views)
        self.views.clear()
        self._placeholders.clear()
        for view in views:
            view.stop()
            self.view_layout.removeWidget(view)
            view.deleteLater()
        try:
            self.proxy_panel.close()
            self.proxy_panel.proxyWidget._stop_services()
            self.proxy_panel.proxyWidget.stop_timer.emit()
            for tab in self.tabbar.tabs:
                tab._hover_timer.stop()
            proxy_runner = self.proxy_panel.proxyWidget.proxy
            if proxy_runner.started and proxy_runner.server is not None:
                proxy_runner.stop()
        except (AttributeError, OSError, RuntimeError):
            logger.exception("Error while shutting down browser services")
        finally:
            event.accept()

    def reload_engine(self):
        for view in tuple(self.views):
            view.reload()
    

    def handle_fullscreen(self, request: QWebEngineFullScreenRequest):
        if request.toggleOn():
            # hide navigation / tab bar
            self.navbar.hide()
            self.tabbar.hide()
            self.progress_bar.hide()
            self.showFullScreen()
        else:
            self.showNormal()
            # restore UI
            self.navbar.show()
            self.tabbar.show()
            view = self.current_view()
            self.progress_bar.setVisible(bool(view and view.page().isLoading()))
        request.accept()
