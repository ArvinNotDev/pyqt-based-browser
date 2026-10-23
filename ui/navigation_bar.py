"""Navigation and utility controls for the browser window."""

from __future__ import annotations

import json
import logging
import os

from PySide6.QtCore import QEvent, QPoint, QRect, QSize, Qt, QTimer, QObject, Signal
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QInputDialog,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QSizePolicy,
    QTabBar,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from .profile_dialog import CustomizeProfile
from .settings import Settings
from .themes import dark_theme, light_theme


logger = logging.getLogger(__name__)


class _SuggestionPopupFilter(QObject):
    """Keep address suggestions keyboard accessible without taking URL focus."""

    def __init__(self, navbar: "NavigationBar"):
        super().__init__(navbar)
        self.navbar = navbar

    def eventFilter(self, obj, event):
        navbar = self.navbar
        popup = navbar.suggestion_popup
        if popup is None or not popup.isVisible():
            return False

        if event.type() == QEvent.MouseButtonPress:
            pos = event.globalPosition().toPoint()
            url_rect = QRect(navbar.url_bar.mapToGlobal(navbar.url_bar.rect().topLeft()), navbar.url_bar.size())
            if not popup.frameGeometry().contains(pos) and not url_rect.contains(pos):
                navbar._close_suggestion_popup()
            return False

        app = QApplication.instance()
        if event.type() == QEvent.KeyPress and app and app.focusWidget() is navbar.url_bar:
            key = event.key()
            if key == Qt.Key_Escape:
                navbar._close_suggestion_popup()
                return True
            if key in (Qt.Key_Up, Qt.Key_Down):
                navbar._move_suggestion_selection(key)
                return True
            if key in (Qt.Key_Return, Qt.Key_Enter) and event.modifiers() & Qt.ShiftModifier:
                navbar._apply_suggestion(no_search=True)
                return True
        return False


class NavigationBar(QToolBar):
    url_submitted = Signal(str)
    home_clicked = Signal()
    profile_selected = Signal(str)
    new_tab_requested = Signal()
    switch_tab_requested = Signal(int)
    move_tab_requested = Signal(int)
    close_tab_requested = Signal(int)
    url_focus_changed = Signal(bool)
    bookmark_requested = Signal()
    show_bookmarks_requested = Signal()
    show_downloads_requested = Signal()
    show_history_requested = Signal()
    proxy_panel_requested = Signal()
    gaming_mode_toggled = Signal(bool)
    site_connection_toggled = Signal(bool)

    def __init__(self, profiles_list, settings: Settings | None = None, parent=None):
        super().__init__("Navigation", parent)
        self.setObjectName("NavigationBar")
        self.setLayoutDirection(Qt.LeftToRight)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumWidth(0)
        self.setFixedHeight(42)
        self.setMovable(False)
        self.setFloatable(False)
        self.setContentsMargins(8, 0, 8, 0)
        self.setIconSize(QSize(16, 16))
        self.setToolButtonStyle(Qt.ToolButtonIconOnly)

        # Kept for compatibility with older integrations. The authoritative, visible
        # tab strip belongs to BrowserWindow, so this bar is intentionally hidden.
        self.tabs_list = []
        self.current_tab_index = 0
        self.tab_bar = QTabBar(self)
        self.tab_bar.setObjectName("legacyTabBar")
        self.tab_bar.setTabsClosable(True)
        self.tab_bar.setMovable(True)
        self.tab_bar.hide()
        self.tab_bar.tabCloseRequested.connect(self.close_tab_requested)
        self.tab_bar.currentChanged.connect(self.switch_tab_requested)
        self.tab_bar.tabMoved.connect(lambda _old_index, new_index: self.move_tab_requested.emit(new_index))

        self.settings = settings if settings is not None else Settings()
        self.profiles = list(profiles_list) if profiles_list else ["Guest"]
        self.profile = self.profiles[0] if self.profiles else "Guest"
        self.history = {}

        self.suggestion_popup: QFrame | None = None
        self.suggestion_list: QListWidget | None = None
        self._popup_filter: _SuggestionPopupFilter | None = None

        icon_path = os.path.join("assets", "icons")
        self.back_btn = self._action("Back", os.path.join(icon_path, "back.png"))
        self.forward_btn = self._action("Forward", os.path.join(icon_path, "forward.png"))
        self.reload_btn = self._action("Reload", os.path.join(icon_path, "reload.png"))
        self.home_btn = self._action("Home", os.path.join(icon_path, "home.png"))
        self.settings_btn = self._action("Settings", os.path.join(icon_path, "settings.png"))
        self._navigation_icon_paths = {
            self.back_btn: os.path.join(icon_path, "back.png"),
            self.forward_btn: os.path.join(icon_path, "forward.png"),
            self.reload_btn: os.path.join(icon_path, "reload.png"),
            self.home_btn: os.path.join(icon_path, "home.png"),
            self.settings_btn: os.path.join(icon_path, "settings.png"),
        }

        for action in (self.back_btn, self.forward_btn, self.reload_btn, self.home_btn):
            self._add_styled_action(action)
            action.triggered.connect(self._close_suggestion_popup)
        self.home_btn.triggered.connect(self.home_clicked.emit)

        self.addSeparator()

        self.url_bar = QLineEdit(self)
        self.url_bar.setObjectName("urlBar")
        self.url_bar.setPlaceholderText("Search or enter address")
        self.url_bar.setFont(QFont("Segoe UI", 10))
        self.url_bar.setLayoutDirection(Qt.LeftToRight)
        self.url_bar.setMinimumWidth(0)
        self.url_bar.setMinimumHeight(25)
        self.url_bar.setMaximumHeight(32)
        self.url_bar.setClearButtonEnabled(True)
        self.url_bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.url_bar.setAccessibleName("Address and search bar")
        self.url_bar.setToolTip("Search or enter a website address (Ctrl+L)")
        self.url_bar.installEventFilter(self)
        self._add_widget(self.url_bar, expanding=True)
        self.url_bar.returnPressed.connect(self._on_url_entered)
        self.url_bar.textEdited.connect(self._on_url_typed)
        self.url_bar.editingFinished.connect(self._close_suggestion_popup)

        self.bookmark_btn = self._button("☆", "Bookmark this page", "utilityToolButton")
        self.bookmark_btn.setAccessibleName("Bookmark this page")
        self.bookmark_btn.clicked.connect(self.bookmark_requested.emit)
        self._add_widget(self.bookmark_btn)

        self.addSeparator()
        self.profile_btn = self._action("Profiles", os.path.join(icon_path, "profile.png"))
        self.profile_btn.setToolTip("Choose or customize a profile")
        self._add_styled_action(self.profile_btn)
        self.profile_menu = QMenu(self)
        self.profile_btn.triggered.connect(self._show_profile_menu)
        self.profile_selected.connect(self._on_profile_selected)
        self._populate_profile_menu()

        self.browser_menu = QMenu(self)
        self.new_tab_action = QAction("New tab", self)
        self.new_tab_action.triggered.connect(self.new_tab_requested.emit)
        self.browser_menu.addAction(self.new_tab_action)
        self.browser_menu.addSeparator()

        self.bookmark_action = QAction("Bookmark this page", self)
        self.bookmark_action.triggered.connect(self.bookmark_requested.emit)
        self.browser_menu.addAction(self.bookmark_action)
        self.show_bookmarks_action = QAction("Bookmarks", self)
        self.show_bookmarks_action.triggered.connect(self.show_bookmarks_requested.emit)
        self.browser_menu.addAction(self.show_bookmarks_action)
        self.show_history_action = QAction("History", self)
        self.show_history_action.triggered.connect(self.show_history_requested.emit)
        self.browser_menu.addAction(self.show_history_action)
        self.show_downloads_action = QAction("Downloads", self)
        self.show_downloads_action.triggered.connect(self.show_downloads_requested.emit)
        self.browser_menu.addAction(self.show_downloads_action)
        self.proxy_panel_action = QAction("Proxy panel", self)
        self.proxy_panel_action.triggered.connect(self.proxy_panel_requested.emit)
        self.browser_menu.addAction(self.proxy_panel_action)
        self.site_connection_action = QAction("Connect directly for this site", self)
        self.site_connection_action.setCheckable(True)
        self.site_connection_action.setToolTip(
            "Bypass Tor for the current site when Tor routing is enabled, then reload it"
        )
        self.site_connection_action.toggled.connect(self.site_connection_toggled.emit)
        self.browser_menu.addAction(self.site_connection_action)
        self.browser_menu.addSeparator()
        self.gaming_mode_action = QAction("Gaming mode", self)
        self.gaming_mode_action.setCheckable(True)
        self.gaming_mode_action.toggled.connect(self.gaming_mode_toggled.emit)
        self.browser_menu.addAction(self.gaming_mode_action)
        self.browser_menu.addSeparator()
        self.settings_btn.triggered.connect(self._close_suggestion_popup)
        self.browser_menu.addAction(self.settings_btn)

        self.menu_button = QToolButton(self)
        self.menu_button.setObjectName("menuButton")
        self.menu_button.setText("⋮")
        self.menu_button.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.menu_button.setToolTip("Browser menu")
        self.menu_button.setAccessibleName("Browser menu")
        self.menu_button.setProperty("menuOpen", False)
        self.menu_button.clicked.connect(self._show_browser_menu)
        self.browser_menu.aboutToShow.connect(lambda: self._set_menu_open(True))
        self.browser_menu.aboutToHide.connect(lambda: self._set_menu_open(False))
        self._add_widget(self.menu_button)

        self.get_history()
        self.apply_theme()
        self._install_popup_event_filter()

    def set_bookmark_state(self, bookmarked: bool) -> None:
        """Keep the star and menu label in sync with the current page."""
        self.bookmark_btn.setText("★" if bookmarked else "☆")
        label = "Remove bookmark" if bookmarked else "Bookmark this page"
        self.bookmark_btn.setToolTip(label)
        self.bookmark_btn.setAccessibleName(label)
        self.bookmark_action.setText(label)

    def set_site_connection_state(self, host: str, direct: bool) -> None:
        action = self.site_connection_action
        action.blockSignals(True)
        action.setVisible(bool(host))
        action.setText(f"Connect directly for {host}" if host else "Connect directly for this site")
        action.setChecked(bool(direct))
        action.blockSignals(False)

    def _action(self, label: str, icon_path: str) -> QAction:
        action = QAction(QIcon(icon_path), label, self)
        action.setToolTip(label)
        action.setStatusTip(label)
        return action

    def _add_styled_action(self, action: QAction) -> None:
        self.addAction(action)
        button = self.widgetForAction(action)
        if isinstance(button, QToolButton):
            button.setObjectName("navigationToolButton")
            button.setAccessibleName(action.text())
            button.setFocusPolicy(Qt.StrongFocus)

    def _button(self, text: str, tooltip: str, object_name: str) -> QToolButton:
        button = QToolButton(self)
        button.setObjectName(object_name)
        button.setText(text)
        button.setToolButtonStyle(Qt.ToolButtonTextOnly)
        button.setToolTip(tooltip)
        button.setAccessibleName(tooltip)
        button.setFocusPolicy(Qt.StrongFocus)
        return button

    def _add_widget(self, widget: QWidget, expanding: bool = False) -> None:
        action = QWidgetAction(self)
        action.setDefaultWidget(widget)
        if expanding:
            widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.addAction(action)

    # Address suggestions
    def _install_popup_event_filter(self):
        if self._popup_filter is None:
            app = QApplication.instance()
            if app:
                self._popup_filter = _SuggestionPopupFilter(self)
                app.installEventFilter(self._popup_filter)

    def _remove_popup_event_filter(self):
        if self._popup_filter is not None:
            app = QApplication.instance()
            if app:
                app.removeEventFilter(self._popup_filter)
            self._popup_filter.deleteLater()
            self._popup_filter = None

    def show_url_suggestions(self, suggestions: list[str]):
        """Backward-compatible entry point for externally supplied suggestions."""
        self._close_suggestion_popup()
        if suggestions:
            self._show_suggestion_popup(suggestions)

    def _on_url_typed(self, text: str):
        self._close_suggestion_popup()
        suggestions = self.search_history(text)
        if suggestions:
            self._show_suggestion_popup(suggestions)

    def _show_suggestion_popup(self, suggestions: list[str]):
        self._close_suggestion_popup()
        popup = QFrame(self)
        popup.setObjectName("suggestionPopup")
        popup.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint)
        popup.setAttribute(Qt.WA_ShowWithoutActivating)
        popup.setFocusPolicy(Qt.NoFocus)

        list_widget = QListWidget(popup)
        list_widget.setObjectName("suggestionList")
        list_widget.setFocusPolicy(Qt.NoFocus)
        for suggestion in suggestions:
            if isinstance(suggestion, str) and suggestion.strip():
                QListWidgetItem(suggestion, list_widget)
        if list_widget.count() == 0:
            popup.deleteLater()
            return
        list_widget.setCurrentRow(0)
        list_widget.itemClicked.connect(self._on_suggestion_clicked)

        layout = QVBoxLayout(popup)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(list_widget)
        popup.resize(self.url_bar.width(), min(240, list_widget.sizeHintForRow(0) * list_widget.count() + 16))
        popup.move(self.url_bar.mapToGlobal(self.url_bar.rect().bottomLeft()))
        self.suggestion_popup = popup
        self.suggestion_list = list_widget
        popup.show()
        popup.raise_()
        self.url_bar.setFocus(Qt.OtherFocusReason)

    def _on_suggestion_clicked(self, item: QListWidgetItem):
        value = item.text()
        self.url_bar.setText(value)
        self._close_suggestion_popup()
        self.url_submitted.emit(value)

    def _move_suggestion_selection(self, key: int):
        if self.suggestion_list is None or self.suggestion_list.count() == 0:
            return
        row = self.suggestion_list.currentRow() + (1 if key == Qt.Key_Down else -1)
        row = max(0, min(row, self.suggestion_list.count() - 1))
        self.suggestion_list.setCurrentRow(row)
        item = self.suggestion_list.currentItem()
        if item:
            self.url_bar.setText(item.text())

    def _apply_suggestion(self, no_search: bool = False):
        item = self.suggestion_list.currentItem() if self.suggestion_list else None
        if item is None:
            return
        value = item.text()
        self.url_bar.setText(value)
        self._close_suggestion_popup()
        if not no_search:
            self.url_submitted.emit(value)

    def _close_suggestion_popup(self, *_args):
        popup = self.suggestion_popup
        self.suggestion_popup = None
        self.suggestion_list = None
        if popup is not None:
            popup.close()
            popup.deleteLater()

    # Profiles and history
    def _on_profile_selected(self, profile_name: str):
        if profile_name not in self.profiles:
            logger.warning("Ignoring unknown profile selection: %r", profile_name)
            return
        self.profile = profile_name
        self._populate_profile_menu(profile_name)
        self.get_history()

    def get_history(self):
        if not self.profile:
            self.history = {}
            return {}
        path = os.path.join("profile_data", self.profile, "history.json")
        try:
            with open(path, "r", encoding="utf-8") as history_file:
                data = json.load(history_file)
            self.history = data if isinstance(data, dict) else {}
        except FileNotFoundError:
            self.history = {}
        except (OSError, json.JSONDecodeError, TypeError) as error:
            logger.warning("Could not read browser history from %s: %s", path, error)
            self.history = {}
        return self.history

    def search_history(self, text: str):
        if not isinstance(self.history, dict) or not self.history:
            return []
        needle = (text or "").casefold()
        return [value for value in self.history if isinstance(value, str) and needle in value.casefold()]

    def apply_theme(self):
        dark = bool(getattr(self.settings, "dark_mode", False))
        theme = dark_theme if dark else light_theme
        self.setStyleSheet(theme)
        if dark:
            for action, path in self._navigation_icon_paths.items():
                action.setIcon(self._tinted_icon(path, "#c7ced8"))
        else:
            for action, path in self._navigation_icon_paths.items():
                action.setIcon(QIcon(path))
        self._refresh_profile_icon()
        self._close_suggestion_popup()

    @staticmethod
    def _tinted_icon(path: str, color: str) -> QIcon:
        pixmap = QPixmap(path)
        if pixmap.isNull():
            return QIcon(path)
        painter = QPainter(pixmap)
        painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
        painter.fillRect(pixmap.rect(), QColor(color))
        painter.end()
        return QIcon(pixmap)

    def set_dark_mode(self, dark: bool):
        self.settings.dark_mode = bool(dark)
        self.apply_theme()

    def update_tabs(self, tabs: list, current_index: int = 0):
        """Update the hidden legacy tab model without adding a second tab strip."""
        self._close_suggestion_popup()
        self.tabs_list = list(tabs or [])
        self.current_tab_index = max(0, min(int(current_index), len(self.tabs_list) - 1)) if self.tabs_list else 0
        self.tab_bar.clear()
        for title in self.tabs_list:
            display = str(title)
            if len(display) > 40:
                display = display[:37] + "..."
            self.tab_bar.addTab(display)
        if self.tabs_list:
            self.tab_bar.setCurrentIndex(self.current_tab_index)

    def _show_profile_menu(self):
        rect = self.actionGeometry(self.profile_btn)
        pos = self.mapToGlobal(rect.bottomLeft() if rect.isValid() else QPoint(0, self.height()))
        self.profile_menu.popup(pos)

    def _show_browser_menu(self, _checked: bool = False) -> None:
        button = self.menu_button
        bottom = button.mapToGlobal(QPoint(0, button.height()))
        menu_width = self.browser_menu.sizeHint().width()
        self.browser_menu.popup(QPoint(bottom.x() + button.width() - menu_width, bottom.y()))

    def _set_menu_open(self, opened: bool) -> None:
        self.menu_button.setProperty("menuOpen", bool(opened))
        style = self.menu_button.style()
        style.unpolish(self.menu_button)
        style.polish(self.menu_button)
        self.menu_button.update()

    def _profile_image_path(self, profile_name: str) -> str:
        return os.path.join("profile_data", profile_name, "profile", "image.png")

    def _refresh_profile_icon(self):
        image_path = self._profile_image_path(self.profile)
        if os.path.isfile(image_path):
            icon = QIcon(image_path)
        elif getattr(self.settings, "dark_mode", False):
            icon = self._tinted_icon(os.path.join("assets", "icons", "profile.png"), "#c7ced8")
        else:
            icon = QIcon(os.path.join("assets", "icons", "profile.png"))
        if icon.isNull():
            default_path = os.path.join("assets", "icons", "profile.png")
            icon = (
                self._tinted_icon(default_path, "#c7ced8")
                if getattr(self.settings, "dark_mode", False)
                else QIcon(default_path)
            )
        self.profile_btn.setIcon(icon)

    def _populate_profile_menu(self, selected_profile: str | None = None):
        if selected_profile in self.profiles:
            self.profile = selected_profile
        elif self.profile not in self.profiles:
            self.profile = self.profiles[0] if self.profiles else "Guest"

        self.profile_menu.clear()
        self._refresh_profile_icon()
        for profile_name in self.profiles:
            action = QAction(profile_name, self.profile_menu)
            action.setCheckable(True)
            action.setChecked(profile_name == self.profile)
            action.triggered.connect(lambda checked=False, name=profile_name: self.profile_selected.emit(name))
            self.profile_menu.addAction(action)

        self.profile_menu.addSeparator()
        customize = QAction("Customize profile…", self.profile_menu)
        customize.triggered.connect(self._customize_profile)
        self.profile_menu.addAction(customize)
        add_profile = QAction("Add profile…", self.profile_menu)
        add_profile.triggered.connect(self._add_new_profile)
        self.profile_menu.addAction(add_profile)

    def _customize_profile(self):
        if not self.profile:
            return
        dialog = CustomizeProfile(self.profile, self)
        dialog.profile_saved.connect(lambda _path: self._refresh_profile_icon())
        dialog.exec()

    def _add_new_profile(self):
        name, accepted = QInputDialog.getText(self, "Add profile", "Profile name:")
        name = name.strip()
        if not accepted or not name:
            return
        if any(existing.casefold() == name.casefold() for existing in self.profiles):
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(self, "Profile already exists", f"A profile named “{name}” already exists.")
            return
        new_profiles = [*self.profiles, name]
        try:
            Settings.save_profiles(new_profiles)
        except Exception as error:
            logger.exception("Could not save the profile list")
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Could not add profile", f"The profile list could not be saved.\n\n{error}")
            return
        self.profiles = new_profiles
        self._populate_profile_menu()

    # URL entry and compatibility helpers
    def _on_url_entered(self):
        if self.suggestion_list is not None and self.suggestion_popup is not None:
            self._apply_suggestion(no_search=False)
            return
        value = self.url_bar.text().strip()
        self._close_suggestion_popup()
        if value:
            self.url_submitted.emit(value)

    def _focus_url_bar(self):
        self.url_bar.setFocus(Qt.ShortcutFocusReason)
        self.url_bar.selectAll()

    def clear_url_bar(self):
        self.url_bar.clear()

    def change_profile_orders(self, selected_profile: str):
        if selected_profile not in self.profiles:
            return
        self.profiles = [selected_profile, *(profile for profile in self.profiles if profile != selected_profile)]
        self._populate_profile_menu(selected_profile)

    def eventFilter(self, obj, event):
        if obj is self.url_bar:
            if event.type() == QEvent.FocusIn:
                self.url_focus_changed.emit(True)
                QTimer.singleShot(0, self.url_bar.selectAll)
            elif event.type() == QEvent.FocusOut:
                self.url_focus_changed.emit(False)
        return super().eventFilter(obj, event)
