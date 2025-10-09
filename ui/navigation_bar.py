from PySide6.QtGui import QAction, QIcon, QFont
from PySide6.QtCore import QSize, Signal, Qt
from PySide6.QtWidgets import QToolBar, QLineEdit, QSizePolicy, QMenu, QInputDialog, QWidgetAction
from .settings import Settings

class NavigationBar(QToolBar):
    url_submitted = Signal(str)
    home_clicked = Signal()
    profile_selected = Signal(str)

    def __init__(self, profiles_list, parent=None):
        super().__init__("Navigation", parent)
        self.setMovable(False)

        self.setIconSize(QSize(24, 24))
        self.setFixedHeight(60)

        icon_path = "assets/icons/"

        self.back_btn = QAction(QIcon(f"{icon_path}back.png"), "Back", self)
        self.forward_btn = QAction(QIcon(f"{icon_path}forward.png"), "Forward", self)
        self.reload_btn = QAction(QIcon(f"{icon_path}reload.png"), "Reload", self)
        self.home_btn = QAction(QIcon(f"{icon_path}home.png"), "Home", self)
        self.settings_btn = QAction(QIcon(f"{icon_path}settings.png"), "Settings", self)

        for btn in [self.back_btn, self.forward_btn, self.reload_btn, self.home_btn, self.settings_btn]:
            self.addAction(btn)

        self.addSeparator()

        self.url_bar = QLineEdit()
        self.url_bar.setPlaceholderText("Enter URL or search...")
        self.url_bar.setFont(QFont("Segoe UI", 12))
        self.url_bar.setMinimumHeight(38)
        self.url_bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.addWidget(self.url_bar)
        self.url_bar.returnPressed.connect(self._on_url_entered)

        self.home_btn.triggered.connect(self.home_clicked.emit)

        self.profile_btn = QAction(QIcon(f"{icon_path}profile.png"), "Profiles", self)
        self.addAction(self.profile_btn)

        self.profiles = profiles_list
        self.profile_menu = QMenu()
        self._populate_profile_menu()
        self.profile_btn.triggered.connect(self._show_profile_menu)

    def _show_profile_menu(self):
        action_widget = self.widgetForAction(self.profile_btn)
        if action_widget:
            self.profile_menu.exec(action_widget.mapToGlobal(action_widget.rect().bottomLeft()))

    def _populate_profile_menu(self):
        self.profile_menu.clear()
        for profile in self.profiles:
            act = QAction(profile, self)
            act.triggered.connect(lambda checked, p=profile: self.profile_selected.emit(p))
            self.profile_menu.addAction(act)

        self.profile_menu.addSeparator()
        add_profile = QAction("➕ Add New Profile", self)
        add_profile.triggered.connect(self._add_new_profile)
        self.profile_menu.addAction(add_profile)

    def _add_new_profile(self):
        name, ok = QInputDialog.getText(self, "New Profile", "Enter profile name:")
        if ok and name.strip():
            self.profiles.append(name.strip())
            Settings.save_profiles(self.profiles)
            self._populate_profile_menu()

    def _on_url_entered(self):
        url = self.url_bar.text().strip()
        if url:
            self.url_submitted.emit(url)
    
    def clear_url_bar(self):
        self.url_bar.clear()