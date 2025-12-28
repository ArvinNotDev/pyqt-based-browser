from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QMenuBar,
    QMenu,
    QStackedWidget,
    QWidget,
    QVBoxLayout,
    QPushButton,
    QMessageBox,
    QSystemTrayIcon
)
from PySide6.QtGui import QIcon, QAction
from PySide6.QtCore import Qt, Signal
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
        super().__init__(parent)
        if IS_WINDOWS:
            self.setWindowFlag(Qt.FramelessWindowHint)
        self.main_widget = QWidget(self)
        self.setCentralWidget(self.main_widget)
        self.stack = QStackedWidget(self)
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0,0,0,0)
        self.main_widget.setLayout(self.main_layout)

        self.setWindowTitle("app")
        self.resize(800, 600)
        
        
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
        
        if IS_WINDOWS:
            self.title_bar = CustomTitleBar(self)
            self.main_layout.addWidget(self.title_bar)
        self._createMenuBar()
        self.main_layout.addWidget(self.stack)
        
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(QIcon(resource_path("assets/icon.png")))
        
        tray_menu = QMenu()
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

    def _toggle_visibility(self):
        self.setHidden(not self.isHidden())

    def _start_key_listener(self):
        keyboard.add_hotkey('ctrl+alt+p', lambda: self.toggle_visibility_signal.emit())
        while self.listener_running:
            time.sleep(0.5)
        keyboard.unhook_all_hotkeys()
        
        
    def show_tray(self):
        self.hide()
        # # shold use show becuase tray will delete after system locked in this case windows
        # self.tray_icon.show()
        
    
    def show_window(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            if self.isHidden():
                self.show()
            else:
                self.hide()
   
    def _createMenuBar(self):
        menuBar = QMenuBar(self)
        self.main_layout.addWidget(menuBar)

        # --- Home ---
        home_action = QAction(HOME, self)
        home_action.triggered.connect(self._show_home)
        menuBar.addAction(home_action)

        # --- Setting ---
        setting_action = QAction(SETTING, self)
        setting_action.triggered.connect(self._show_setting)
        menuBar.addAction(setting_action)

        # --- Block Host ---
        block_action = QAction(BLOCK_HOST, self)
        block_action.triggered.connect(self._show_block_host)
        menuBar.addAction(block_action)
        
        # --- Exclude Host ---
        exclude_action = QAction(EXCLUDE_HOST, self)
        exclude_action.triggered.connect(self._show_exclude_host)
        menuBar.addAction(exclude_action)
        
        # --- Updater ---
        updater_action = QAction("Updater", self)
        updater_action.triggered.connect(self._show_updater)
        menuBar.addAction(updater_action)

    
    def _show_home(self):
        self.stack.setCurrentIndex(0)

    def _show_setting(self):
        self.stack.setCurrentIndex(1)
    
    def _show_block_host(self):
        self.stack.setCurrentIndex(2)
    
    def _show_exclude_host(self):
        self.stack.setCurrentIndex(3)
        
    def _show_updater(self):
        self.stack.setCurrentIndex(4)
        
    def _notify(self, title, message):
        self.tray_icon.showMessage(title, message, QSystemTrayIcon.Information, 2000)

    def closeEvent(self, event):
        if IS_WINDOWS:
            self.listener_running = False
            self.listener_thread.join()
        
        self.listener_running = False 
        self.tray_icon.hide()  
        self.proxyWidget._stop_services()
        logger.info("The window is closing by some other method.")
        event.accept()