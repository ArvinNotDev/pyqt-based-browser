"""Navigation and utility controls for the browser window."""

from __future__ import annotations

import json
import logging
import os

import qtawesome as qta

from PySide6.QtCore import QEvent, QPoint, QRect, QSize, Qt, QTimer, QObject, Signal
from PySide6.QtGui import QAction, QFont, QIcon, QGuiApplication
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
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

from app_paths import user_data_path

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
    open_profiles_requested = Signal()
    create_profile_requested = Signal()
    new_tab_requested = Signal()
    switch_tab_requested = Signal(int)
    move_tab_requested = Signal(int)
    close_tab_requested = Signal(int)
    url_focus_changed = Signal(bool)
    bookmark_requested = Signal()
    show_bookmarks_requested = Signal()
    show_downloads_requested = Signal()
    downloads_panel_requested = Signal()
    show_history_requested = Signal()
    open_external_requested = Signal()
    reload_bypass_cache_requested = Signal()
    proxy_panel_requested = Signal()
    gaming_mode_toggled = Signal(bool)
    site_connection_toggled = Signal(bool)

    def __init__(self, profiles_list, settings: Settings | None = None, parent=None):
        super().__init__("Navigation", parent)
        self.setObjectName("NavigationBar")
        self.setLayoutDirection(Qt.LeftToRight)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumWidth(0)
        self.setFixedHeight(50)
        self.setMovable(False)
        self.setFloatable(False)
        # Keep every navigation control on the same vertical centre-line and let
        # the menu button sit close to the far-right edge of the browser shell.
        self.setContentsMargins(10, 0, 4, 0)
        self.setIconSize(QSize(18, 18))
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
        self._suggestion_popup_height: int | None = None
        self._url_load_progress: int | None = None

        self._navigation_icon_names = {}
        self.back_btn = self._action("Back", "fa5s.arrow-left")
        self.forward_btn = self._action("Forward", "fa5s.arrow-right")
        self.reload_btn = self._action("Reload", "fa5s.redo")
        self.home_btn = self._action("Home", "fa5s.home")
        self.settings_btn = self._action("Settings", "fa5s.cog")
        self._navigation_icon_names.update({
            self.back_btn: "fa5s.arrow-left",
            self.forward_btn: "fa5s.arrow-right",
            self.reload_btn: "fa5s.redo",
            self.home_btn: "fa5s.home",
            self.settings_btn: "fa5s.cog",
        })

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
        self.url_bar.setFixedHeight(30)
        self.url_bar.setClearButtonEnabled(True)
        self.url_bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.url_bar.setAccessibleName("Address and search bar")
        self.url_bar.setToolTip("Search or enter a website address (Ctrl+L)")
        self.url_bar.installEventFilter(self)
        self._add_widget(self.url_bar, expanding=True)
        self._apply_url_bar_progress_style()
        self.url_bar.returnPressed.connect(self._on_url_entered)
        self.url_bar.textEdited.connect(self._on_url_typed)
        self.url_bar.editingFinished.connect(self._close_suggestion_popup)

        self._bookmark_active = False
        self.bookmark_btn = self._button("", "Bookmark this page", "utilityToolButton")
        self.bookmark_btn.setToolButtonStyle(Qt.ToolButtonIconOnly)
        self.bookmark_btn.setIcon(self._awesome_icon("fa5.star"))
        self.bookmark_btn.setIconSize(QSize(18, 18))
        self.bookmark_btn.setAccessibleName("Bookmark this page")
        self.bookmark_btn.clicked.connect(self.bookmark_requested.emit)
        self._add_widget(self.bookmark_btn)

        self.downloads_btn = self._button("", "Show or hide downloads panel", "utilityToolButton")
        self.downloads_btn.setToolButtonStyle(Qt.ToolButtonIconOnly)
        self.downloads_btn.setIcon(self._awesome_icon("fa5s.download"))
        self.downloads_btn.setIconSize(QSize(17, 17))
        self.downloads_btn.setAccessibleName("Show or hide downloads panel")
        self.downloads_btn.setFixedSize(34, 30)
        self.downloads_btn.setCheckable(True)
        self.downloads_btn.setProperty("downloadsPanelOpen", False)
        self.downloads_btn.clicked.connect(self.downloads_panel_requested.emit)
        self._add_widget(self.downloads_btn)

        self.proxy_panel_btn = self._button("", "Show or hide Tor proxy", "utilityToolButton")
        self.proxy_panel_btn.setToolButtonStyle(Qt.ToolButtonIconOnly)
        self.proxy_panel_btn.setIcon(self._awesome_icon("fa5s.globe"))
        self.proxy_panel_btn.setIconSize(QSize(17, 17))
        self.proxy_panel_btn.setAccessibleName("Show or hide Tor proxy")
        self.proxy_panel_btn.setFixedSize(34, 30)
        self.proxy_panel_btn.setCheckable(True)
        self.proxy_panel_btn.setProperty("proxyPanelOpen", False)
        self.proxy_panel_btn.clicked.connect(self.proxy_panel_requested.emit)
        self._add_widget(self.proxy_panel_btn)

        self.addSeparator()
        self.profile_btn = self._action("Profiles", "fa5s.user-circle")
        self._navigation_icon_names[self.profile_btn] = "fa5s.user-circle"
        self.profile_btn.setToolTip("Choose or manage browser profiles")
        self._add_styled_action(self.profile_btn)
        self.profile_menu = QMenu(self)
        self.profile_btn.triggered.connect(self._show_profile_menu)
        self.profile_selected.connect(self._on_profile_selected)
        self._populate_profile_menu()

        self.browser_menu = QMenu(self)
        self.new_tab_action = QAction(self._awesome_icon("fa5s.plus"), "New tab", self)
        self.new_tab_action.triggered.connect(self.new_tab_requested.emit)
        self.browser_menu.addAction(self.new_tab_action)
        self.reload_bypass_cache_action = QAction(self._awesome_icon("fa5s.redo"), "Reload without cache", self)
        self.reload_bypass_cache_action.setToolTip(
            "Reload the current page while bypassing the local HTTP cache (Ctrl+Shift+R)"
        )
        self.reload_bypass_cache_action.triggered.connect(self.reload_bypass_cache_requested.emit)
        self.browser_menu.addAction(self.reload_bypass_cache_action)
        self.browser_menu.addSeparator()

        self.bookmark_action = QAction(self._awesome_icon("fa5s.bookmark"), "Bookmark this page", self)
        self.bookmark_action.triggered.connect(self.bookmark_requested.emit)
        self.browser_menu.addAction(self.bookmark_action)
        self.show_bookmarks_action = QAction(self._awesome_icon("fa5s.bookmark"), "Bookmarks", self)
        self.show_bookmarks_action.triggered.connect(self.show_bookmarks_requested.emit)
        self.browser_menu.addAction(self.show_bookmarks_action)
        self.show_history_action = QAction(self._awesome_icon("fa5s.history"), "History", self)
        self.show_history_action.triggered.connect(self.show_history_requested.emit)
        self.browser_menu.addAction(self.show_history_action)
        self.show_downloads_action = QAction(self._awesome_icon("fa5s.download"), "Downloads", self)
        self.show_downloads_action.triggered.connect(self.show_downloads_requested.emit)
        self.browser_menu.addAction(self.show_downloads_action)
        self.open_external_action = QAction(self._awesome_icon("fa5s.external-link-alt"), "Open in default browser", self)
        self.open_external_action.triggered.connect(self.open_external_requested.emit)
        self.browser_menu.addAction(self.open_external_action)
        self.proxy_panel_action = QAction(self._awesome_icon("fa5s.shield-alt"), "Proxy panel", self)
        self.proxy_panel_action.triggered.connect(self.proxy_panel_requested.emit)
        self.browser_menu.addAction(self.proxy_panel_action)
        self.site_connection_action = QAction(self._awesome_icon("fa5s.link"), "Connect directly for this site", self)
        self.site_connection_action.setCheckable(True)
        self.site_connection_action.setToolTip(
            "Bypass ARMA's Tor route for this host and reload without cache. "
            "This does not disable an external system VPN."
        )
        self.site_connection_action.toggled.connect(self.site_connection_toggled.emit)
        self.browser_menu.addAction(self.site_connection_action)
        self.browser_menu.addSeparator()
        self.gaming_mode_action = QAction(self._awesome_icon("fa5s.gamepad"), "Gaming mode", self)
        self.gaming_mode_action.setCheckable(True)
        self.gaming_mode_action.toggled.connect(self.gaming_mode_toggled.emit)
        self.browser_menu.addAction(self.gaming_mode_action)
        self.browser_menu.addSeparator()
        self.settings_btn.triggered.connect(self._close_suggestion_popup)
        self.browser_menu.addAction(self.settings_btn)
        self._browser_menu_icon_names = {
            self.new_tab_action: "fa5s.plus",
            self.reload_bypass_cache_action: "fa5s.redo",
            self.bookmark_action: "fa5s.bookmark",
            self.show_bookmarks_action: "fa5s.bookmark",
            self.show_history_action: "fa5s.history",
            self.show_downloads_action: "fa5s.download",
            self.open_external_action: "fa5s.external-link-alt",
            self.proxy_panel_action: "fa5s.shield-alt",
            self.site_connection_action: "fa5s.link",
            self.gaming_mode_action: "fa5s.gamepad",
            self.settings_btn: "fa5s.cog",
        }

        self.menu_button = QToolButton(self)
        self.menu_button.setObjectName("menuButton")
        # Retain the legacy text API for integrations/tests; IconOnly renders the
        # precisely centred vector icon instead of the glyph baseline.
        self.menu_button.setText("⋮")
        self.menu_button.setToolButtonStyle(Qt.ToolButtonIconOnly)
        self.menu_button.setIconSize(QSize(17, 17))
        self.menu_button.setFixedSize(QSize(34, 30))
        self.menu_button.setFocusPolicy(Qt.TabFocus)
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
        """Keep the vector star and menu label in sync with the current page."""
        self._bookmark_active = bool(bookmarked)
        self.bookmark_btn.setIcon(
            self._awesome_icon("fa5s.star" if self._bookmark_active else "fa5.star")
        )
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

    def _icon_color(self) -> str:
        return "#c7d4e6" if getattr(self.settings, "dark_mode", False) else "#465366"

    def _awesome_icon(self, name: str) -> QIcon:
        return qta.icon(name, color=self._icon_color())

    def _action(self, label: str, icon_name: str) -> QAction:
        action = QAction(self._awesome_icon(icon_name), label, self)
        action.setToolTip(label)
        action.setStatusTip(label)
        return action

    def _add_styled_action(self, action: QAction) -> None:
        self.addAction(action)
        button = self.widgetForAction(action)
        if isinstance(button, QToolButton):
            button.setObjectName("navigationToolButton")
            button.setAccessibleName(action.text())
            button.setFocusPolicy(Qt.TabFocus)
            button.setToolButtonStyle(Qt.ToolButtonIconOnly)
            button.setIconSize(QSize(17, 17))
            button.setFixedSize(34, 30)
            button.setAutoRaise(True)

    def _button(self, text: str, tooltip: str, object_name: str) -> QToolButton:
        button = QToolButton(self)
        button.setObjectName(object_name)
        button.setText(text)
        button.setToolButtonStyle(Qt.ToolButtonTextOnly)
        button.setToolTip(tooltip)
        button.setAccessibleName(tooltip)
        button.setFocusPolicy(Qt.TabFocus)
        button.setIconSize(QSize(17, 17))
        button.setFixedSize(34, 30)
        button.setAutoRaise(True)
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
        """Update the visible suggestions without tearing down the popup."""
        self._update_suggestion_popup(suggestions)

    def _on_url_typed(self, text: str):
        self._update_suggestion_popup(self.search_history(text))

    def _show_suggestion_popup(self, suggestions: list[str]):
        # Keep the older internal entry point available for callers and tests.
        self._update_suggestion_popup(suggestions)

    @staticmethod
    def _valid_suggestions(suggestions: list[str]) -> list[str]:
        valid: list[str] = []
        seen: set[str] = set()
        for suggestion in suggestions or []:
            if not isinstance(suggestion, str) or not suggestion.strip():
                continue
            value = suggestion.strip()
            key = value.casefold()
            if key not in seen:
                seen.add(key)
                valid.append(value)
        return valid

    def _position_suggestion_popup(self) -> None:
        popup = self.suggestion_popup
        if popup is None or self._suggestion_popup_height is None:
            return
        anchor = self.url_bar.mapToGlobal(self.url_bar.rect().bottomLeft())
        screen = QGuiApplication.screenAt(anchor) or QGuiApplication.primaryScreen()
        width = max(180, self.url_bar.width())
        height = self._suggestion_popup_height
        x, y = anchor.x(), anchor.y()
        if screen is not None:
            area = screen.availableGeometry()
            width = min(width, max(180, area.width() - 16))
            x = min(max(x, area.left() + 8), area.right() - width + 1)
            if y + height > area.bottom() + 1:
                above = self.url_bar.mapToGlobal(self.url_bar.rect().topLeft()).y() - height
                y = above if above >= area.top() else max(area.top(), area.bottom() - height + 1)
        popup.setGeometry(x, y, width, height)

    def _update_suggestion_popup(self, suggestions: list[str]) -> None:
        values = self._valid_suggestions(suggestions)
        if not values:
            self._close_suggestion_popup()
            return

        popup = self.suggestion_popup
        list_widget = self.suggestion_list
        if popup is not None and list_widget is not None:
            # Update the model in place: the native Tool window remains the same
            # widget at the same location, so typing does not flicker or jump.
            try:
                selected = list_widget.currentItem().text() if list_widget.currentItem() else None
                list_widget.setUpdatesEnabled(False)
                list_widget.clear()
                for value in values:
                    QListWidgetItem(value, list_widget)
                selected_row = next(
                    (row for row in range(list_widget.count())
                     if list_widget.item(row).text() == selected),
                    0,
                )
                list_widget.setCurrentRow(selected_row)
                list_widget.verticalScrollBar().setValue(0)
                list_widget.setUpdatesEnabled(True)
                self._position_suggestion_popup()
                if not popup.isVisible():
                    popup.show()
                popup.raise_()
                return
            except RuntimeError:
                # A popup can be destroyed by the window system while it is hidden.
                self.suggestion_popup = None
                self.suggestion_list = None
                self._suggestion_popup_height = None

        popup = QFrame(self)
        popup.setObjectName("suggestionPopup")
        popup.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint)
        popup.setAttribute(Qt.WA_ShowWithoutActivating)
        popup.setFocusPolicy(Qt.NoFocus)

        list_widget = QListWidget(popup)
        list_widget.setObjectName("suggestionList")
        list_widget.setFocusPolicy(Qt.NoFocus)
        list_widget.setUniformItemSizes(True)
        for value in values:
            QListWidgetItem(value, list_widget)
        list_widget.setCurrentRow(0)
        list_widget.itemClicked.connect(self._on_suggestion_clicked)

        layout = QVBoxLayout(popup)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(list_widget)
        row_height = max(30, list_widget.sizeHintForRow(0))
        visible_rows = min(6, max(3, len(values)))
        self._suggestion_popup_height = min(240, row_height * visible_rows + 8)
        self.suggestion_popup = popup
        self.suggestion_list = list_widget
        self._position_suggestion_popup()
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
        self._suggestion_popup_height = None
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
        path = user_data_path("profile_data", self.profile, "history.json")
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
        self.setStyleSheet(dark_theme if dark else light_theme)
        self.menu_button.setIcon(self._awesome_icon("fa5s.ellipsis-v"))
        self.menu_button.setIconSize(QSize(18, 18))
        for action, icon_name in self._navigation_icon_names.items():
            action.setIcon(self._awesome_icon(icon_name))
        for action, icon_name in self._browser_menu_icon_names.items():
            action.setIcon(self._awesome_icon(icon_name))
        self.bookmark_btn.setIcon(
            self._awesome_icon("fa5s.star" if self._bookmark_active else "fa5.star")
        )
        downloads_open = self.downloads_btn.isChecked()
        proxy_open = self.proxy_panel_btn.isChecked()
        self.downloads_btn.setIcon(qta.icon(
            "fa5s.download",
            color="#2f81f7" if downloads_open else self._icon_color(),
        ))
        self.proxy_panel_btn.setIcon(qta.icon(
            "fa5s.globe",
            color="#2f81f7" if proxy_open else self._icon_color(),
        ))
        self._refresh_profile_icon()
        self._apply_url_bar_progress_style()
        self._close_suggestion_popup()

    def set_load_progress(self, progress: int | None) -> None:
        """Tint the address field by load progress without a page-covering HUD."""
        if progress is None:
            normalized = None
        else:
            normalized = max(0, min(100, int(progress)))
        if normalized == self._url_load_progress:
            return
        self._url_load_progress = normalized
        self._apply_url_bar_progress_style()

    def _apply_url_bar_progress_style(self) -> None:
        if not hasattr(self, "url_bar"):
            return
        dark = bool(getattr(self.settings, "dark_mode", False))
        if dark:
            text, base = "#e4e8ee", "rgba(37,43,52,235)"
            border, hover, accent, placeholder = "#3a414b", "#536681", "#82aff4", "#9ba8bc"
            fill = "rgba(130,175,244,58)"
            selection = "#405e87"
        else:
            text, base = "#20242a", "rgba(255,255,255,235)"
            border, hover, accent, placeholder = "#d9dde4", "#b8c0cc", "#3979d6", "#78818d"
            fill = "rgba(57,121,214,54)"
            selection = "#cfe0fb"

        progress = self._url_load_progress
        if progress is None:
            background = base
        elif progress >= 100:
            background = fill
        else:
            # The address field itself paints the progress behind its editable text.
            # Keeping the transition point in a stylesheet avoids child overlays,
            # extra layout, or an extra widget covering the cursor and selection.
            stop = max(0.015, min(0.995, progress / 100.0))
            edge = min(0.999, stop + 0.003)
            background = (
                "qlineargradient(x1:0, y1:0, x2:1, y2:0, "
                f"stop:0 {fill}, stop:{stop:.4f} {fill}, "
                f"stop:{edge:.4f} {base}, stop:1 {base})"
            )

        self.url_bar.setStyleSheet(f"""
            QLineEdit#urlBar {{
                color: {text}; background: {background};
                border: 1px solid {border}; border-radius: 15px;
                padding: 3px 12px; min-height: 24px;
                selection-background-color: {selection};
            }}
            QLineEdit#urlBar:hover {{ border-color: {hover}; }}
            QLineEdit#urlBar:focus {{ border: 1px solid {accent}; }}
            QLineEdit#urlBar::placeholder {{ color: {placeholder}; }}
        """)

    def set_proxy_panel_state(self, opened: bool) -> None:
        button = getattr(self, "proxy_panel_btn", None)
        if button is None:
            return
        button.blockSignals(True)
        button.setChecked(bool(opened))
        button.setProperty("proxyPanelOpen", bool(opened))
        button.setToolTip("Hide Tor proxy panel" if opened else "Show Tor proxy panel")
        button.setAccessibleName(button.toolTip())
        color = "#2f81f7" if opened else self._icon_color()
        button.setIcon(qta.icon("fa5s.globe", color=color))
        button.style().unpolish(button)
        button.style().polish(button)
        button.blockSignals(False)
        button.update()

    def set_downloads_panel_state(self, opened: bool) -> None:
        button = getattr(self, "downloads_btn", None)
        if button is None:
            return
        button.blockSignals(True)
        button.setChecked(bool(opened))
        button.setProperty("downloadsPanelOpen", bool(opened))
        button.setToolTip("Hide downloads panel" if opened else "Show downloads panel")
        button.setAccessibleName(button.toolTip())
        color = "#2f81f7" if opened else self._icon_color()
        button.setIcon(qta.icon("fa5s.download", color=color))
        button.style().unpolish(button)
        button.style().polish(button)
        button.blockSignals(False)
        button.update()

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
        return user_data_path("profile_data", profile_name, "profile", "image.png")

    def _refresh_profile_icon(self):
        image_path = self._profile_image_path(self.profile)
        icon = QIcon(image_path) if os.path.isfile(image_path) else QIcon()
        if icon.isNull():
            icon = self._awesome_icon("fa5s.user-circle")
        self.profile_btn.setIcon(icon)
        label = f"Profile: {self.profile}"
        self.profile_btn.setToolTip(f"{label} · click to switch or manage")
        self.profile_btn.setStatusTip(label)
        self.profile_btn.setAccessibleName(label)

    def _populate_profile_menu(self, selected_profile: str | None = None) -> None:
        if selected_profile in self.profiles:
            self.profile = selected_profile
        elif self.profile not in self.profiles:
            self.profile = self.profiles[0] if self.profiles else "Guest"

        self.profile_menu.clear()
        current = QAction(self._awesome_icon("fa5s.user-circle"), f"Using {self.profile}", self.profile_menu)
        current.setEnabled(False)
        self.profile_menu.addAction(current)
        self.profile_menu.addSeparator()
        for profile_name in self.profiles:
            action = QAction(
                self._awesome_icon("fa5s.check-circle" if profile_name == self.profile else "fa5s.user"),
                profile_name,
                self.profile_menu,
            )
            action.setCheckable(True)
            action.setChecked(profile_name == self.profile)
            action.triggered.connect(
                lambda checked=False, name=profile_name: self.profile_selected.emit(name)
            )
            self.profile_menu.addAction(action)

        self.profile_menu.addSeparator()
        create_action = QAction(self._awesome_icon("fa5s.user-plus"), "Create profile…", self.profile_menu)
        create_action.triggered.connect(lambda _checked=False: self.create_profile_requested.emit())
        self.profile_menu.addAction(create_action)
        manage_action = QAction(self._awesome_icon("fa5s.users-cog"), "Manage profiles…", self.profile_menu)
        manage_action.triggered.connect(lambda _checked=False: self.open_profiles_requested.emit())
        self.profile_menu.addAction(manage_action)

    def _show_profile_menu(self, _checked: bool = False) -> None:
        rect = self.actionGeometry(self.profile_btn)
        pos = self.mapToGlobal(
            rect.bottomLeft() if rect.isValid() else QPoint(0, self.height())
        )
        self._populate_profile_menu()
        self.profile_menu.popup(pos)

    def set_profiles(self, profiles: list[str], selected_profile: str | None = None) -> None:
        """Refresh the header selector after profiles are created, switched or removed."""
        self.profiles = list(dict.fromkeys(
            name for name in (profiles or [])
            if isinstance(name, str) and name
        )) or ["Guest"]
        self._populate_profile_menu(selected_profile)

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
        self.set_profiles(self.profiles, selected_profile)

    def eventFilter(self, obj, event):
        if obj is self.url_bar:
            if event.type() == QEvent.FocusIn:
                self.url_focus_changed.emit(True)
                QTimer.singleShot(0, self.url_bar.selectAll)
            elif event.type() == QEvent.FocusOut:
                self.url_focus_changed.emit(False)
        return super().eventFilter(obj, event)
