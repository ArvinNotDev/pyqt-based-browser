from PySide6.QtWidgets import (
    QApplication, QMainWindow, QMenu, QStackedWidget, QWidget,
    QVBoxLayout, QHBoxLayout, QPushButton, QButtonGroup, QSizePolicy,
    QSystemTrayIcon,
)
from PySide6.QtGui import QIcon, QAction
from PySide6.QtCore import Qt, Signal, QSize
import qtawesome as qta
from proxy.utils import resource_path
import keyboard
import threading
import time
import logging
from proxy.config import CONFIG, IS_WINDOWS
from proxy.ui_.worker.worker import Worker
from proxy.ui_.window.proxy_window import ProxyWindow
from proxy.ui_.window.custom_titlebar import CustomTitleBar
from proxy.ui_.window.setting_window import SettingWindow
from proxy.ui_.window.block_host_window import BlcokHostsWindow
from proxy.ui_.window.exclude_host_window import ExcludeHostsWindow
from proxy.ui_.window.updater_window import UpdaterWindow
from proxy.ui_.emojis import DARK, LIGHT, QUIT, HOME, EXCLUDE_HOST, BLOCK_HOST, SETTING, HELP
logger = logging.getLogger(__name__)
CONFIG.load()
class Window(QMainWindow):
    toggle_visibility_signal = Signal()
    def __init__(self, parent=None, profile=None):
        self._parent = parent
        self.profile = profile
        self._embedded = parent is not None
        self._display_mode = "dark"
        super().__init__(parent)
        if IS_WINDOWS and not self._embedded:
            self.setWindowFlag(Qt.FramelessWindowHint)
        self.main_widget = QWidget(self)
        self.main_widget.setObjectName("torProxyShell")
        self.setCentralWidget(self.main_widget)
        self.stack = QStackedWidget(self.main_widget)
        self.stack.setObjectName("torProxyPages")
        self.main_layout = QVBoxLayout(self.main_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        self.setWindowTitle("Tor proxy")
        if not self._embedded:
            self.resize(800, 600)
        else:
            self.setMinimumSize(0, 0)
            self.setMaximumSize(420, 16777215)
        
        
        self.proxyWidget = ProxyWindow(self)
        self.stack.addWidget(self.proxyWidget)
        
        self.settingWidget = SettingWindow(self)
        self.stack.addWidget(self.settingWidget)
        
        self.block_host_window = BlcokHostsWindow(self)
        self.stack.addWidget(self.block_host_window)
        
        self.exclude_host_window = ExcludeHostsWindow(self)
        self.stack.addWidget(self.exclude_host_window)
        
        self.updater_window = UpdaterWindow(self)
        self.stack.addWidget(self.updater_window)
        
        if IS_WINDOWS and not self._embedded:
            self.title_bar = CustomTitleBar(self)
            self.main_layout.addWidget(self.title_bar)
        self._createMenuBar()
        self.main_layout.addWidget(self.stack, 1)
        self.tray_icon = None
        self.listener_running = False
        self.listener_thread = None
        if not self._embedded:
            self.tray_icon = QSystemTrayIcon(self)
            self.tray_icon.setIcon(QIcon(resource_path("assets/icon.png")))
            tray_menu = QMenu(self)
            quit_action = QAction("Quit", self)
            quit_action.triggered.connect(lambda: (self.show(), self.close()))
            tray_menu.addAction(quit_action)
            self.tray_icon.setContextMenu(tray_menu)
            self.tray_icon.activated.connect(self.show_window)
            self.tray_icon.hide()
            self.listener_running = True
            self.listener_thread = threading.Thread(target=self._start_key_listener, daemon=True)
            if IS_WINDOWS:
                self.listener_thread.start()
        self.toggle_visibility_signal.connect(self._toggle_visibility)
        self.apply_theme(self._display_mode)

    def _toggle_visibility(self):
        self.setHidden(not self.isHidden())

    def _start_key_listener(self):
        keyboard.add_hotkey('ctrl+alt+p', lambda: self.toggle_visibility_signal.emit())
        while self.listener_running:
            time.sleep(0.5)
        keyboard.unhook_all_hotkeys()
        
        
    def show_tray(self):
        if self._embedded:
            return
        self.hide()
        if self.tray_icon is not None:
            self.tray_icon.show()

    def show_window(self, reason):
        if self._embedded or self.tray_icon is None:
            return
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.setVisible(self.isHidden())
   
    def _createMenuBar(self):
        """Responsive navigation without a duplicate Help/Exit section."""
        nav = QWidget(self.main_widget)
        nav.setObjectName("proxyEmbeddedNavigation")
        layout = QHBoxLayout(nav)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(5)
        self.menu_bar = nav
        self.main_layout.addWidget(nav)
        definitions = [
            ("Home", "fa6s.house", self._show_home),
            ("Settings", "fa6s.gear", self._show_setting),
            ("Bundles", "fa6s.boxes-stacked", self._show_updater),
        ]
        self._proxy_nav_buttons = []
        self._proxy_nav_group = QButtonGroup(self)
        self._proxy_nav_group.setExclusive(True)
        for label, icon_name, callback in definitions:
            button = QPushButton(label, nav)
            button.setObjectName("proxyEmbeddedNavButton")
            button.setIcon(qta.icon(icon_name))
            button.setIconSize(QSize(15, 15))
            button.setMinimumHeight(34)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            button.setCheckable(True)
            button.setToolTip(label)
            button.setAccessibleName(label)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.clicked.connect(callback)
            self._proxy_nav_group.addButton(button)
            self._proxy_nav_buttons.append(button)
            layout.addWidget(button, 1)
        self._proxy_nav_buttons[0].setChecked(True)

    def _show_page_index(self, index):
        if not 0 <= index < self.stack.count():
            return
        self.stack.setCurrentIndex(index)
        nav_title = "Home" if index == 0 else ("Bundles" if index == 4 else "Settings")
        for button in getattr(self, "_proxy_nav_buttons", []):
            button.setChecked(button.text() == nav_title)

    def _show_home(self):
        self._show_page_index(0)

    def _show_setting(self):
        self._show_page_index(1)

    def _show_block_host(self):
        self._show_page_index(2)

    def _show_exclude_host(self):
        self._show_page_index(3)

    def _show_updater(self):
        self._show_page_index(4)

    def apply_theme(self, mode=None):
        settings = getattr(self._parent, "settings", None)
        if mode not in {"dark", "light"}:
            mode = "dark" if bool(getattr(settings, "dark_mode", True)) else "light"
        self._display_mode = mode
        dark = mode == "dark"
        border = "#384454" if dark else "#d8e0eb"
        panel = "#202630" if dark else "#f7f9fc"
        text = "#e8edf3" if dark else "#253247"
        accent = "#65aaf6" if dark else "#176fc1"
        hover = "rgba(101,170,246,0.13)" if dark else "rgba(23,111,193,0.08)"
        self.setStyleSheet(f"""
            QWidget#torProxyShell {{ background: {panel}; color: {text}; }}
            QWidget#proxyEmbeddedNavigation {{ background: {"#1b2029" if dark else "#eef2f8"}; border-bottom: 1px solid {border}; }}
            QPushButton#proxyEmbeddedNavButton {{ min-height: 32px; padding: 0 6px; border: 1px solid transparent; border-radius: 8px; background: transparent; color: {text}; font-weight: 650; }}
            QPushButton#proxyEmbeddedNavButton:hover {{ background: {hover}; border-color: {border}; }}
            QPushButton#proxyEmbeddedNavButton:checked {{ background: {"#314c70" if dark else "#dce9fc"}; border-color: {"#5276a4" if dark else "#b8d0f3"}; color: {"#ffffff" if dark else "#174b8f"}; }}
            QScrollBar:vertical {{ background: transparent; width: 9px; margin: 2px; }}
            QScrollBar::handle:vertical {{ background: {"#4b5b70" if dark else "#bdc8d8"}; min-height: 24px; border-radius: 4px; }}
            QScrollBar::handle:vertical:hover {{ background: {"#6a809c" if dark else "#94a8c4"}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
            QLabel#proxyRulesTitle {{ font-size: 15px; font-weight: 800; padding: 6px 2px; }}
            QPushButton#proxySettingsBackButton {{ min-height: 32px; border: 1px solid {border}; border-radius: 8px; background: transparent; color: {text}; }}
            QPushButton#proxySettingsBackButton:hover {{ border-color: {accent}; background: {hover}; }}
        """)
        for widget in (getattr(self, "proxyWidget", None), getattr(self, "settingWidget", None)):
            callback = getattr(widget, "apply_theme", None)
            if callable(callback):
                callback(mode)
        if hasattr(self, "title_bar") and not self._embedded:
            self.title_bar.update_theme(text)

    def _notify(self, title, message):
        if self.tray_icon is not None and self.tray_icon.isVisible():
            self.tray_icon.showMessage(title, message, QSystemTrayIcon.Information, 2000)
        elif self._embedded and self._parent is not None:
            status_bar = getattr(self._parent, "statusBar", None)
            if callable(status_bar):
                status_bar().showMessage(f"{title}: {message}", 4500)

    def closeEvent(self, event):
        if self._embedded:
            event.ignore()
            return
        self.listener_running = False
        if IS_WINDOWS and self.listener_thread is not None:
            self.listener_thread.join(timeout=1)
        if self.tray_icon is not None:
            self.tray_icon.hide()
        self.proxyWidget._stop_services()
        self.proxyWidget.proxy.stop()
        logger.info("The window is closing by some other method.")
        event.accept()
