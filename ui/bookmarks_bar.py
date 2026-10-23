"""Compact dropdown menu for saved bookmarks in the browser toolbar."""

import logging

from PySide6.QtCore import QPoint, QSize, Qt, Signal
from PySide6.QtWidgets import QMenu, QToolButton

import qtawesome as qta

from ._manager_ui import normalize_bookmark


logger = logging.getLogger(__name__)


class BookmarkOverflowMenu(QMenu):
    """Bookmark menu that forwards context actions to the browser window."""

    bookmark_context_requested = Signal(dict, QPoint)

    def contextMenuEvent(self, event):
        action = self.actionAt(event.pos())
        bookmark = action.data() if action is not None else None
        if isinstance(bookmark, dict):
            self.bookmark_context_requested.emit(bookmark, event.globalPos())
            event.accept()
            return
        super().contextMenuEvent(event)


class BookmarksBar(QToolButton):
    """Toolbar button that opens bookmarks in a clean, compact menu."""

    url_activated = Signal(str)
    manage_requested = Signal()
    bookmark_context_requested = Signal(dict, QPoint)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("bookmarkMenuButton")
        self.setText("Bookmarks")
        self.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.setIconSize(QSize(14, 14))
        self.setIcon(qta.icon("fa5s.bookmark", color="#53647c"))
        self.setFixedHeight(30)
        self.setMinimumWidth(86)
        self.setMaximumWidth(112)
        self.setToolTip("Open saved bookmarks")
        self.setAccessibleName("Saved bookmarks")
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.PointingHandCursor)
        self.setPopupMode(QToolButton.InstantPopup)

        self._bookmarks = []
        self._bookmark_actions = []
        self._more_menu = BookmarkOverflowMenu(self)
        self._more_menu.setObjectName("bookmarksPopupMenu")
        self._more_menu.bookmark_context_requested.connect(self.bookmark_context_requested)
        self.setMenu(self._more_menu)
        self.set_bookmarks([])

    def set_bookmarks(self, items):
        """Replace menu entries, safely omitting malformed bookmark records."""
        self._more_menu.clear()
        self._bookmarks = []
        self._bookmark_actions = []
        invalid_count = 0

        try:
            if isinstance(items, (str, bytes)):
                raise TypeError("Bookmarks must be a collection of records")
            records = list(items or [])
        except TypeError:
            records = []
            invalid_count = 1

        for item in records:
            try:
                normalized = normalize_bookmark(item)
            except Exception as error:
                logger.warning("Skipping an unreadable bookmark record: %s", error)
                invalid_count += 1
                continue
            if normalized is None:
                invalid_count += 1
                continue

            normalized = dict(normalized)
            self._bookmarks.append(normalized)
            action = self._more_menu.addAction(qta.icon("fa5s.bookmark", color="#53647c"), normalized["title"])
            action.setToolTip(normalized["url"])
            action.setStatusTip(normalized["url"])
            action.setData(normalized)
            action.triggered.connect(
                lambda checked=False, url=normalized["url"]: self.url_activated.emit(url)
            )
            self._bookmark_actions.append(action)

        if not self._bookmarks:
            empty_action = self._more_menu.addAction(
                qta.icon("fa5s.bookmark", color="#8c99ab"), "No bookmarks yet"
            )
            empty_action.setEnabled(False)

        self._more_menu.addSeparator()
        self._manage_action = self._more_menu.addAction(
            qta.icon("fa5s.list", color="#53647c"), "Manage bookmarks…"
        )
        self._manage_action.setToolTip("Open the bookmark manager")
        self._manage_action.triggered.connect(
            lambda checked=False: self.manage_requested.emit()
        )

        if invalid_count:
            self.setToolTip(f"Open saved bookmarks ({invalid_count} invalid record(s) skipped)")
        else:
            self.setToolTip("Open saved bookmarks")

    @property
    def bookmark_actions(self):
        """Return current bookmark actions for accessibility and UI tests."""
        return tuple(self._bookmark_actions)

    def apply_icon_theme(self, dark: bool) -> None:
        """Tint menu icons to maintain contrast in either browser theme."""
        color = "#c7d4e6" if dark else "#53647c"
        self.setIcon(qta.icon("fa5s.bookmark", color=color))
        for action in self._bookmark_actions:
            action.setIcon(qta.icon("fa5s.bookmark", color=color))
        if not self._bookmarks:
            for action in self._more_menu.actions():
                if action.text() == "No bookmarks yet":
                    action.setIcon(qta.icon("fa5s.bookmark", color="#8492a6"))
        self._manage_action.setIcon(qta.icon("fa5s.list", color=color))
