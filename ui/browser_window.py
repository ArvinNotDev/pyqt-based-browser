import os
import time
from typing import List, Optional, Dict

from PySide6.QtCore import (
    Qt, QUrl, QTimer, Signal, QPoint, QPropertyAnimation,
    QThreadPool, QRunnable, QMetaObject, QObject
)
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QProgressBar, QFrame, QSizePolicy,
    QScrollArea, QGraphicsOpacityEffect, QDockWidget
)
from PySide6.QtGui import QPixmap, QMovie, QAction
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineSettings
from PySide6.QtWebEngineCore import QWebEngineFullScreenRequest

from .settings import Settings
from .navigation_bar import NavigationBar
from .settings_window import SettingsWindow
from managers.history_manager import History
from .themes import light_theme, dark_theme
from proxy.ui import Window
TAB_WIDTH = 160
TAB_HEIGHT = 34
TAB_SPACING = 4
SCROLL_STEP = 140


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

    def add_tab(self, title: str = "New Tab") -> int:
        tab = TabButton(title)
        tab.clicked.connect(lambda t=tab: self._on_tab_clicked(t))
        tab.closed.connect(lambda t=tab: self._on_tab_closed(t))
        tab.requested_preview.connect(lambda t=tab: self._on_tab_preview_requested(t))

        insert_pos = max(0, self.holder_layout.count() - (1 if self.plus_inside else 0))
        self.holder_layout.insertWidget(insert_pos, tab)
        self.tabs.append(tab)

        idx = len(self.tabs) - 1
        self.set_active(idx)
        QTimer.singleShot(0, self._update_overflow)
        return idx

    def remove_tab(self, index: int):
        if index < 0 or index >= len(self.tabs):
            return
        tab = self.tabs.pop(index)
        try:
            self.holder_layout.removeWidget(tab)
        except Exception:
            pass
        tab.setParent(None)
        tab.deleteLater()

        if len(self.tabs) == 0:
            self.active_index = -1
            self.tab_changed.emit(-1)
            QTimer.singleShot(0, self._update_overflow)
            return

        if self.active_index == index:
            self.set_active(max(0, index - 1))
        elif self.active_index > index:
            self.active_index -= 1
            self.set_active(self.active_index)
        QTimer.singleShot(0, self._update_overflow)

    def set_active(self, index: int):
        if not self.tabs:
            self.active_index = -1
            self.tab_changed.emit(-1)
            return
        index = max(0, min(index, len(self.tabs) - 1))
        self.active_index = index
        for i, t in enumerate(self.tabs):
            t.set_active(i == index)
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
        except Exception:
            pass

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
                try:
                    self.holder_layout.removeWidget(self.plus_tab)
                    self.plus_tab.setParent(None)
                except Exception:
                    pass
                self.external_plus.show()
                self.plus_inside = False
            elif not overflow and not self.plus_inside:
                try:
                    self.holder_layout.addWidget(self.plus_tab)
                    self.plus_tab.setParent(self.holder)
                except Exception:
                    pass
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


# Background runnable to perform delayed deletion / stop operations without blocking UI
class DelayedCleanupRunnable(QRunnable):
    def __init__(self, view: QWebEngineView, wait_seconds: float = 0.6):
        super().__init__()
        self.view = view
        self.wait_seconds = wait_seconds
        self.setAutoDelete(True)

    def run(self):
        # Give a small grace period (user will perceive immediate close due to UI removal).
        # Then ensure loading is stopped and schedule safe deletion on main thread.
        try:
            # Stop loading in the view (queued to main thread)
            QMetaObject.invokeMethod(self.view, "stop", Qt.QueuedConnection)
        except Exception:
            pass
        # wait in background
        time.sleep(self.wait_seconds)
        # Finally request deleteLater on the view in main thread
        try:
            QMetaObject.invokeMethod(self.view, "deleteLater", Qt.QueuedConnection)
        except Exception:
            pass


class BrowserWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.proxy_panel = Window(self, None)
        self.proxy_panel.proxyWidget.proxy.start()
        import os
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = f"--proxy-server=127.0.0.1:{self.proxy_panel.proxyWidget.proxy_port}"


        self.settings = Settings()
        self.settings.load_profile_settings()
        self.selected_profile = "Guest"
        if self.settings.profiles_list and self.selected_profile not in self.settings.profiles_list:
            self.selected_profile = self.settings.profiles_list[0]
        self.settings.load(self.selected_profile)

        self.history = History(self.selected_profile)

        self.storage_path = os.path.join(os.getcwd(), "profile_data")
        os.makedirs(self.storage_path, exist_ok=True)

        self.profile = QWebEngineProfile(self.selected_profile, self)
        self._apply_profile_settings(self.profile)

        self.navbar = NavigationBar(self.settings.profiles_list, settings=self.settings)
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
        self._placeholders: Dict[int, QWidget] = {}
        self._snapshots: Dict[int, QPixmap] = {}
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

        # thread pool for background tasks like delayed deletion
        self._thread_pool = QThreadPool.globalInstance()

        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.navbar)
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
        except Exception:
            pass

        QTimer.singleShot(0, lambda: self.new_tab(self.settings.homepage))
        self._last_progress_ts = 0
        
        self.dock = QDockWidget("Proxy Window", self)
        self.dock.setMinimumWidth(300)
        self.dock.setMaximumWidth(400)
        self.dock.setWidget(self.proxy_panel)
        self.dock.setFloating(False)
        self.dock.setFeatures(QDockWidget.DockWidgetClosable)
        self.addDockWidget(Qt.RightDockWidgetArea, self.dock)

        # override close behavior dock
        self.dock.closeEvent = self._on_dock_close
        btn = QAction("Proxy", self.navbar)
        self.navbar.addAction(btn)
        btn.triggered.connect(self.show_proxy)
        

    def _on_dock_close(self, event):
        self.dock.hide()
        event.ignore()  

    def show_proxy(self):
        if not self.dock.isHidden():
            self.dock.hide()
            return
        self.dock.show()
        self.dock.raise_() 
        self.dock.activateWindow() 

    def _apply_profile_settings(self, profile: QWebEngineProfile):
        profile.setPersistentCookiesPolicy(QWebEngineProfile.ForcePersistentCookies)
        profile_dir = os.path.join(self.storage_path, self.selected_profile)
        os.makedirs(profile_dir, exist_ok=True)
        profile.setCachePath(os.path.join(profile_dir, "cache"))
        profile.setPersistentStoragePath(os.path.join(profile_dir, "storage"))
        profile.setDownloadPath(os.path.join(profile_dir, "downloads"))
        try:
            s = profile.settings()
            s.setAttribute(QWebEngineSettings.JavascriptEnabled, True)
            s.setAttribute(QWebEngineSettings.LocalStorageEnabled, True)
            s.setAttribute(QWebEngineSettings.FullScreenSupportEnabled, True)
        except Exception:
            pass

    def _capture_snapshot(self, index: int):
        if index < 0 or index >= len(self.views):
            return
        view = self.views[index]
        try:
            pix = view.grab()
            if pix and not pix.isNull():
                self._snapshots[index] = pix
        except Exception:
            pass

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
        """
        Fast-create tab with placeholder; real QWebEngineView loads offscreen and swaps in on loadFinished.
        """
        if not url:
            url = "about:blank"
        if isinstance(url, QUrl):
            url_q = url
        else:
            if " " in url or "." not in url:
                url_q = QUrl(f"{self.settings.default_search_engine}{url.replace(' ', '+')}")
            else:
                if not url.startswith(("http://", "https://")):
                    url = "https://" + url
                url_q = QUrl(url)

        # 1) Add tab button immediately (fast UI feedback)
        idx = self.tabbar.add_tab("New Tab")

        # 2) Create placeholder widget and insert into layout
        placeholder = self._make_placeholder(url_q.toString())
        self._placeholders[idx] = placeholder
        self.view_layout.addWidget(placeholder)

        # 3) Create the real QWebEngineView but keep it invisible until loaded
        view = QWebEngineView()
        view.setVisible(False)
        view.setAttribute(Qt.WA_TranslucentBackground, True)

        page = QWebEnginePage(self.profile, view)
        view.setPage(page)
        page.fullScreenRequested.connect(self.handle_fullscreen)
        

        # connect signals (use lambdas to capture view)
        view.titleChanged.connect(lambda t, v=view: self._on_title_changed(t, v))
        view.urlChanged.connect(lambda u, v=view: self._on_view_url_changed(u, v))
        view.loadStarted.connect(lambda v=view: self._on_load_started(v))
        view.loadProgress.connect(lambda p, v=view: self._on_load_progress(p, v))
        view.loadFinished.connect(lambda ok, v=view, pidx=idx: self._on_load_finished_with_swap(ok, v, pidx))

        # Append view to lists but keep it hidden until swapped in
        # We must insert the view after placeholder so indexes align (views list index == tab index)
        self.views.insert(idx, view)
        # Also insert placeholder mapping adjustments for indices > idx (shift keys)
        self._shift_placeholders_on_insert(idx)

        self.view_layout.addWidget(view)

        prev = self.current_index
        if make_active and prev != -1 and prev != idx:
            self._capture_snapshot(prev)

        if make_active:
            # Activate new tab immediately — placeholder visible
            self._activate(idx)

        # Start loading the URL (this runs asynchronously inside QWebEngine)
        view.setUrl(url_q)
        return idx

    def _shift_placeholders_on_insert(self, insert_idx: int):
        # keep dictionary keys consistent with views list indices
        new = {}
        for k, v in self._placeholders.items():
            if k >= insert_idx:
                new[k + 1] = v
            else:
                new[k] = v
        self._placeholders = new

    def _shift_placeholders_on_remove(self, removed_idx: int):
        # adjust placeholder indices after removal
        new = {}
        for k, v in self._placeholders.items():
            if k < removed_idx:
                new[k] = v
            elif k > removed_idx:
                new[k - 1] = v
        self._placeholders = new

    def request_close_tab(self, index: int):
        """
        Handles user request to close tab:
        - give instant UI feedback by removing tab UI and hiding placeholder/view.
        - schedule actual stop+deletion in background for responsiveness.
        """
        if index < 0 or index >= len(self.views):
            # Still remove tab button if possible to keep UI consistent
            try:
                self.tabbar.remove_tab(index)
            except Exception:
                pass
            return

        # Immediately remove tab button for fast UX
        try:
            self.tabbar.remove_tab(index)
        except Exception:
            pass

        # If placeholder exists for this index, remove it immediately
        placeholder = self._placeholders.get(index, None)
        if placeholder:
            try:
                self.view_layout.removeWidget(placeholder)
                placeholder.setParent(None)
                placeholder.deleteLater()
            except Exception:
                pass

        # Hide the view immediately so user sees it as closed
        view = self.views[index]
        try:
            view.hide()
        except Exception:
            pass

        # Remove view from the in-memory list so indices stay consistent
        try:
            self.views.pop(index)
        except Exception:
            pass

        # Shift placeholders mapping
        self._shift_placeholders_on_remove(index)

        # Schedule delayed cleanup to stop loading and delete the view safely (in background)
        cleanup = DelayedCleanupRunnable(view, wait_seconds=0.45)
        self._thread_pool.start(cleanup)

        # Adjust current index and activate a sensible tab
        if len(self.views) == 0:
            # last tab closed -> quit app
            self.close()
            return

        # pick a new index to activate
        new_index = max(0, min(self.tabbar.active_index, len(self.views) - 1))
        self._activate(new_index)

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
            self._capture_snapshot(prev_index)

        # Show the placeholder/view corresponding to index; hide others
        for i, v in enumerate(self.views):
            try:
                v.setVisible(i == index and (i not in self._placeholders))
            except Exception:
                pass

        # Also ensure only placeholder for active tab is visible if view hasn't been swapped in yet
        for k, ph in self._placeholders.items():
            try:
                ph.setVisible(k == index)
            except Exception:
                pass

        self.current_index = index

        try:
            cur_url = self.views[index].url()
            if hasattr(self.navbar, "url_bar"):
                self.navbar.url_bar.setText(cur_url.toString())
        except Exception:
            pass

        try:
            self.tabbar.set_active(index)
        except Exception:
            pass

    def _on_tab_changed(self, index: int):
        self._activate(index)

    def _on_title_changed(self, title: str, view: QWebEngineView):
        try:
            idx = self.views.index(view)
            self.tabbar.set_title(idx, title)
        except ValueError:
            pass

    def _on_view_url_changed(self, url: QUrl, view: QWebEngineView):
        if view is self.current_view():
            try:
                if hasattr(self.navbar, "url_bar"):
                    self.navbar.url_bar.setText(url.toString())
            except Exception:
                pass

    def _on_load_started(self, view: QWebEngineView):
        if view is not self.current_view():
            # still update placeholder/other states if needed
            pass
        else:
            self.progress_bar.setRange(0, 0)
            self.progress_bar.show()
        try:
            self.statusBar().showMessage("Loading...", 0)
        except Exception:
            pass


    def _on_load_progress(self, progress: int, view):
        if view is not self.current_view():
            return

        now = time.monotonic()
        if now - self._last_progress_ts < 0.05:  # 50ms
            return
        self._last_progress_ts = now

        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(progress)


    def _on_load_finished_with_swap(self, ok: bool, view: QWebEngineView, index_for_view: int):
        """
        When the real view finished loading, swap it in smoothly with the placeholder (if present).
        """
        try:
            # find current index of this view in self.views (it may have moved if other tabs closed)
            try:
                idx = self.views.index(view)
            except ValueError:
                # view no longer tracked (maybe closed) -> schedule immediate cleanup
                cleanup = DelayedCleanupRunnable(view, wait_seconds=0.15)
                self._thread_pool.start(cleanup)
                return

            # Update progress UI if this is current view
            if view is self.current_view():
                self.progress_bar.setRange(0, 100)
                self.progress_bar.setValue(100)
                QTimer.singleShot(300, self.progress_bar.hide)

            # Capture snapshot for preview
            QTimer.singleShot(100, lambda i=idx: self._capture_snapshot(i))

            # If there is a placeholder for this index, do a fade swap
            placeholder = self._placeholders.get(idx, None)
            if placeholder:
                # ensure view is invisible but ready
                view.setVisible(True)
                view_effect = QGraphicsOpacityEffect(view)
                view.setGraphicsEffect(view_effect)
                view_effect.setOpacity(0.0)

                ph_effect = QGraphicsOpacityEffect(placeholder)
                placeholder.setGraphicsEffect(ph_effect)
                ph_effect.setOpacity(1.0)

                # animate placeholder fade out
                anim_out = QPropertyAnimation(ph_effect, b"opacity", self)
                anim_out.setDuration(220)
                anim_out.setStartValue(1.0)
                anim_out.setEndValue(0.0)

                # animate view fade in
                anim_in = QPropertyAnimation(view_effect, b"opacity", self)
                anim_in.setDuration(260)
                anim_in.setStartValue(0.0)
                anim_in.setEndValue(1.0)

                def on_swap_finished():
                    # cleanup placeholder
                    try:
                        self.view_layout.removeWidget(placeholder)
                        placeholder.setParent(None)
                        placeholder.deleteLater()
                    except Exception:
                        pass
                    # remove placeholder entry
                    try:
                        del self._placeholders[idx]
                    except Exception:
                        pass
                    # remove effects
                    try:
                        view.setGraphicsEffect(None)
                    except Exception:
                        pass

                # chain animations: when anim_out finished, start anim_in and then call cleanup after both
                anim_out.finished.connect(anim_in.start)
                anim_in.finished.connect(on_swap_finished)
                anim_out.start()
            else:
                # no placeholder: just ensure view visible
                view.setVisible(True)
        except Exception:
            pass

        try:
            if view is self.current_view():
                self.statusBar().showMessage("Loaded" if ok else "Load failed", 1500 if ok else 3000)
        except Exception:
            pass

    def _show_tab_preview(self, index: int):
        if index < 0 or index >= len(self.views) or index == self.current_index:
            return

        pix = self._snapshots.get(index, None)
        if pix is None:
            try:
                pix = self.views[index].grab()
            except Exception:
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
        except Exception:
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
            except Exception:
                pass

    def current_view(self) -> Optional[QWebEngineView]:
        if 0 <= self.current_index < len(self.views):
            return self.views[self.current_index]
        return None

    def change_profile(self, profile_name: str):
        self.selected_profile = profile_name
        self.history = History(self.selected_profile)
        profile_dir = os.path.join(self.storage_path, profile_name)
        os.makedirs(profile_dir, exist_ok=True)
        self.profile = QWebEngineProfile(profile_name, self)
        self.proxy_panel.proxyWidget._stop_services()
        self.proxy_panel.profile = self.profile
        self._apply_profile_settings(self.profile)

        for v in self.views:
            try:
                new_page = QWebEnginePage(self.profile, v)
                v.setPage(new_page)
            except Exception:
                pass
        try:
            self.navbar.change_profile_orders(self.selected_profile)
            self.navbar.clear_url_bar()
        except Exception:
            pass

    def on_profile_selected(self, profile_name: str):
        try:
            self.settings.save(self.selected_profile)
        except Exception:
            pass
        self.selected_profile = profile_name
        self.settings.load(profile_name)
        self.change_profile(profile_name)
        self.apply_theme()
        self.new_tab(self.settings.homepage)

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
            try:
                if hasattr(self.navbar, "url_bar"):
                    self.navbar.url_bar.setText(url)
            except Exception:
                pass

    def update_url_bar(self, qurl: QUrl):
        try:
            if hasattr(self.navbar, "url_bar"):
                self.navbar.url_bar.setText(qurl.toString())
        except Exception:
            pass

    def open_settings(self):
        dialog = SettingsWindow(self.settings, self.selected_profile, self.history, self)
        if dialog.exec():
            self.settings.load(self.selected_profile)
            self.apply_theme()

    def apply_theme(self):
        try:
            theme = dark_theme if getattr(self.settings, "dark_mode", False) else light_theme
            self.setStyleSheet(theme)
            if hasattr(self.navbar, "apply_theme"):
                self.navbar.apply_theme()
        except Exception:
            pass
    
    def closeEvent(self, event):
        # dock widget hide instead of close
        if self.dock.isVisible():
            self.dock.hide()   
        self.proxy_panel.close()
        self.proxy_panel.proxyWidget._stop_services()
        self.proxy_panel.proxyWidget.stop_timer.emit()
        for i in self.tabbar.tabs:
            i._hover_timer.stop()
        self.proxy_panel.proxyWidget.proxy.stop()
        self.dock.close()
        event.accept() 

    def reload_engine(self):
        pass
    

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
            self.progress_bar.show()
        request.accept()
