from PySide6.QtGui import QAction, QIcon, QFont
from PySide6.QtCore import QSize, Signal, Qt, QPoint
from PySide6.QtWidgets import (
    QToolBar, QLineEdit, QSizePolicy, QListWidget, QListWidgetItem, QFrame,
    QInputDialog, QWidgetAction, QPushButton, QWidget, QHBoxLayout, QTabBar, QMenu, QVBoxLayout
)
from .settings import Settings
from .themes import light_theme, dark_theme
from .profile_dialog import CustomizeProfile
import os, json


class NavigationBar(QToolBar):
    url_submitted = Signal(str)
    home_clicked = Signal()
    profile_selected = Signal(str)
    new_tab_requested = Signal()
    switch_tab_requested = Signal(int)
    move_tab_requested = Signal(int)
    close_tab_requested = Signal(int)
    url_focus_changed = Signal(bool)

    def __init__(self, profiles_list, settings: Settings | None = None, parent=None):
        super().__init__("Navigation", parent)
        self.setMovable(False)
        self.setIconSize(QSize(20, 20))
        self.setFixedHeight(40)
        self.tabs_list = []
        self.current_tab_index = 0
        self.settings = settings if settings is not None else Settings()
        self.profiles = list(profiles_list) if profiles_list else ["Guest"]
        self.profile = self.profiles[0] if self.profiles else "Guest"
        self.history = {}
        self.suggestion_popup = None

        # === Buttons ===
        icon_path = "assets/icons/"
        self.back_btn = QAction(QIcon(f"{icon_path}back.png"), "Back", self)
        self.forward_btn = QAction(QIcon(f"{icon_path}forward.png"), "Forward", self)
        self.reload_btn = QAction(QIcon(f"{icon_path}reload.png"), "Reload", self)
        self.home_btn = QAction(QIcon(f"{icon_path}home.png"), "Home", self)
        self.settings_btn = QAction(QIcon(f"{icon_path}settings.png"), "Settings", self)
        for btn in (self.back_btn, self.forward_btn, self.reload_btn, self.home_btn, self.settings_btn):
            self.addAction(btn)

        # === Connect buttons ===
        self.home_btn.triggered.connect(lambda: self.home_clicked.emit())
        self.addSeparator()

        # === Tabs section ===
        tab_widget = QWidget()
        tab_layout = QHBoxLayout(tab_widget)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.setSpacing(0)

        self.tab_bar = QTabBar()
        self.tab_bar.setTabsClosable(True)
        self.tab_bar.setMovable(True)
        self.tab_bar.setExpanding(False)
        self.tab_bar.setElideMode(Qt.ElideRight)
        self.tab_bar.tabCloseRequested.connect(self.close_tab_requested)
        self.tab_bar.currentChanged.connect(self.switch_tab_requested)
        self.tab_bar.setStyleSheet("""
            QTabBar::tab {
                background: #2b2b2b;
                color: #ddd;
                border: 1px solid #444;
                border-bottom: none;
                padding: 8px 20px;
                margin-right: 2px;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
            }
            QTabBar::tab:selected {
                background: #444;
                color: white;
            }
            QTabBar::close-button {
                image: url(assets/icons/close.png);
                width: 12px;
                height: 12px;
                margin-left: 8px;
            }
            QTabBar::close-button:hover {
                image: url(assets/icons/close_hover.png);
            }
        """)
        tab_layout.addWidget(self.tab_bar)

        # New Tab Button
        self.new_tab_btn = QPushButton()
        self.new_tab_btn.setIcon(QIcon(f"{icon_path}new_tab.png"))
        self.new_tab_btn.setFixedSize(30, 30)
        self.new_tab_btn.setObjectName("newTabButton")
        self.new_tab_btn.setStyleSheet("""
            QPushButton#newTabButton {
                background: transparent;
                color: #aaa;
                border: none;
            }
            QPushButton#newTabButton:hover {
                background: #444;
                color: white;
                border-radius: 5px;
            }
        """)
        self.new_tab_btn.clicked.connect(lambda: self.new_tab_requested.emit())
        tab_layout.addWidget(self.new_tab_btn)

        tab_action = QWidgetAction(self)
        tab_action.setDefaultWidget(tab_widget)
        self.addAction(tab_action)

        # === URL bar ===
        self.url_bar = QLineEdit()
        self.url_bar.setPlaceholderText("Search or enter address")
        self.url_bar.setFont(QFont("Segoe UI", 11))
        self.url_bar.setMinimumHeight(36)
        self.url_bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.addWidget(self.url_bar)

        self.url_bar.returnPressed.connect(self._on_url_entered)
        self.url_bar.textEdited.connect(lambda text: self._on_url_typed(text))

        # === Spacer ===
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        spacer_action = QWidgetAction(self)
        spacer_action.setDefaultWidget(spacer)
        self.addAction(spacer_action)

        # === Profile Button ===
        self.profile_btn = QAction(QIcon(f"{icon_path}profile.png"), "Profiles", self)
        self.addAction(self.profile_btn)

        # === Menus ===
        self.profile_menu = QMenu(self)
        self.profile_btn.triggered.connect(self._show_profile_menu)
        self.profile_selected.connect(self._on_profile_selected)
        self._populate_profile_menu()

        # === Load History & Theme ===
        self.get_history()
        self.apply_theme()

    # ==================================================
    # === Suggestion Popup ===
    # ==================================================
    def show_url_suggestions(self, suggestions: list[str]):
        if self.suggestion_popup:
            self.suggestion_popup.deleteLater()
            self.suggestion_popup = None

        if not suggestions:
            return

        popup = QFrame(self)
        popup.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint)
        popup.setAttribute(Qt.WA_ShowWithoutActivating)
        popup.setFocusPolicy(Qt.NoFocus)
        popup.setStyleSheet("""
            QFrame {
                background-color: #2b2b2b;
                border: 1px solid #555;
                border-radius: 6px;
            }
            QListWidget {
                background: transparent;
                color: white;
                border: none;
            }
            QListWidget::item {
                padding: 6px 10px;
            }
            QListWidget::item:hover {
                background-color: #444;
            }
        """)

        list_widget = QListWidget(popup)
        list_widget.setFocusPolicy(Qt.NoFocus)
        for s in suggestions:
            QListWidgetItem(s, list_widget)

        def on_item_clicked(item):
            self.url_bar.setText(item.text())
            self.url_submitted.emit(item.text())
            popup.close()

        list_widget.itemClicked.connect(on_item_clicked)

        layout = QVBoxLayout(popup)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(list_widget)

        popup.resize(self.url_bar.width(), min(200, list_widget.sizeHintForRow(0) * len(suggestions) + 8))
        pos = self.url_bar.mapToGlobal(self.url_bar.rect().bottomLeft())
        popup.move(pos)
        popup.show()
        popup.raise_()

        self.suggestion_popup = popup
        self.url_bar.setFocus(Qt.OtherFocusReason)

    def _on_url_typed(self, text):
        if self.suggestion_popup:
            self.suggestion_popup.close()
            self.suggestion_popup = None

        suggestions = self.search_history(text)
        self.show_url_suggestions(suggestions)

    # ==================================================
    # === Profiles, History, Tabs, and Themes ===
    # ==================================================
    def _on_profile_selected(self, profile_name):
        self.profile = profile_name
        self._populate_profile_menu(profile_name)
        self.get_history()

    def get_history(self):
        if not self.profile:
            self.history = {}
            return {}
        path = f"profile_data/{self.profile}/history.json"
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    self.history = json.load(f)
            except Exception:
                self.history = {}
        else:
            self.history = {}
        return self.history

    def search_history(self, text: str):
        if not hasattr(self, "history") or not self.history:
            return []
        return [h for h in self.history.keys() if text.lower() in h.lower()]

    def apply_theme(self):
        theme = dark_theme if getattr(self.settings, "dark_mode", False) else light_theme
        self.setStyleSheet(theme)
        self.url_bar.setStyleSheet("")
        self.new_tab_btn.setStyleSheet(self.new_tab_btn.styleSheet())
        self.tab_bar.setStyleSheet(self.tab_bar.styleSheet())

    def set_dark_mode(self, dark: bool):
        try:
            self.settings.dark_mode = dark
        except Exception:
            pass
        self.apply_theme()

    def update_tabs(self, tabs: list, current_index: int = 0):
        self.tab_bar.clear()
        self.tabs_list = list(tabs)
        self.current_tab_index = int(current_index) if tabs else 0
        for t in self.tabs_list:
            display = t if len(t) <= 40 else t[:37] + "..."
            self.tab_bar.addTab(display)
        self.tab_bar.setCurrentIndex(self.current_tab_index)

    # ==================================================
    # === Profile Menu ===
    # ==================================================
    def _show_profile_menu(self):
        rect = self.actionGeometry(self.profile_btn)
        pos = self.mapToGlobal(rect.bottomLeft() if rect.isValid() else QPoint(0, self.height()))
        self.profile_menu.popup(pos)

    def _populate_profile_menu(self, selected_profile=None):
        self.profile_menu.clear()
        self.profile = selected_profile or self.profile or (self.profiles[0] if self.profiles else "Guest")
        path = f"profile_data/{self.profile}/profile/image.png"
        if os.path.exists(path):
            self.profile_btn.setIcon(QIcon(path))
        else:
            self.profile_btn.setIcon(QIcon("assets/icons/profile.png"))

        for profile in self.profiles:
            display_name = f"*{profile}" if profile == self.profile else profile
            act = QAction(display_name, self)
            act.triggered.connect(lambda checked=False, p=profile: self.profile_selected.emit(p))
            self.profile_menu.addAction(act)

        self.profile_menu.addSeparator()
        customize_profile = QAction("✏️ Customize Profile", self)
        customize_profile.triggered.connect(self._customize_profile)
        self.profile_menu.addAction(customize_profile)
        self.profile_menu.addSeparator()
        add_profile = QAction("➕ Add New Profile", self)
        add_profile.triggered.connect(self._add_new_profile)
        self.profile_menu.addAction(add_profile)

    def _customize_profile(self):
        if self.profile is not None:
            CustomizeProfile(self.profile, self).show()

    def _add_new_profile(self):
        name, ok = QInputDialog.getText(self, "New Profile", "Enter profile name:")
        if ok and name.strip():
            self.profiles.append(name.strip())
            try:
                Settings.save_profiles(self.profiles)
            except Exception:
                try:
                    Settings.save_profile_settings(self.profiles)
                except Exception:
                    pass
            self._populate_profile_menu()

    # ==================================================
    # === URL Bar ===
    # ==================================================
    def _on_url_entered(self):
        url = self.url_bar.text().strip()
        if url:
            self.url_submitted.emit(url)

    def clear_url_bar(self):
        self.url_bar.clear()

    def change_profile_orders(self, selected_profile: str):
        if selected_profile not in self.profiles:
            return
        new_profiles_order = [selected_profile] + [p for p in self.profiles if p != selected_profile]
        self.profiles = new_profiles_order
        self._populate_profile_menu(selected_profile)
