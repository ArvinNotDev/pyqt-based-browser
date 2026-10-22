"""Compact, overflow-aware bookmarks strip for a browser window."""

import logging

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMenu,
    QSizePolicy,
    QToolButton,
    QWidget,
)

from ._manager_ui import normalize_bookmark


logger = logging.getLogger(__name__)


class BookmarksBar(QWidget):
    url_activated = Signal(str)
    manage_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("BookmarksBar")
        self.setFixedHeight(38)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._bookmarks = []
        self._buttons = []

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 2, 8, 2)
        layout.setSpacing(4)

        self.heading = QLabel("Bookmarks", self)
        self.heading.setObjectName("bookmarksHeading")
        self.heading.setFixedWidth(72)
        self.heading.setAccessibleName("Bookmarks")
        layout.addWidget(self.heading)

        self.empty_label = QLabel("No bookmarks yet", self)
        self.empty_label.setObjectName("bookmarksEmpty")
        self.empty_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout.addWidget(self.empty_label, 1)

        self._more_menu = QMenu(self)
        self.more_button = QToolButton(self)
        self.more_button.setObjectName("bookmarkMore")
        self.more_button.setText("More ▾")
        self.more_button.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.more_button.setToolTip("Show bookmarks that do not fit in the bar")
        self.more_button.setAccessibleName("More bookmarks")
        self.more_button.setPopupMode(QToolButton.InstantPopup)
        self.more_button.setFixedWidth(72)
        self.more_button.setMenu(self._more_menu)
        self.more_button.hide()
        layout.addWidget(self.more_button)

        self.manage_button = QToolButton(self)
        self.manage_button.setObjectName("bookmarkManage")
        self.manage_button.setText("Manage")
        self.manage_button.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.manage_button.setToolTip("Manage bookmarks")
        self.manage_button.setAccessibleName("Manage bookmarks")
        self.manage_button.setFixedWidth(68)
        self.manage_button.clicked.connect(self.manage_requested.emit)
        layout.addWidget(self.manage_button)
        self._layout = layout

    def set_bookmarks(self, items):
        """Replace the visible records; malformed entries are safely omitted."""
        for button in self._buttons:
            self._layout.removeWidget(button)
            button.deleteLater()
        self._buttons.clear()
        self._bookmarks = []
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
            self._bookmarks.append(normalized)
            title = normalized["title"]
            display = QFontMetrics(self.font()).elidedText(title, Qt.ElideRight, 150)
            button = QToolButton(self)
            button.setObjectName("bookmarkItem")
            button.setText(display)
            button.setToolButtonStyle(Qt.ToolButtonTextOnly)
            button.setToolTip(f"{title}\n{normalized['url']}")
            button.setAccessibleName(f"Open bookmark: {title}")
            button.setFocusPolicy(Qt.StrongFocus)
            button.setCursor(Qt.PointingHandCursor)
            width = max(64, min(172, QFontMetrics(button.font()).horizontalAdvance(display) + 22))
            button.setFixedWidth(width)
            button.clicked.connect(lambda checked=False, url=normalized["url"]: self.url_activated.emit(url))
            self._buttons.append(button)
            self._layout.insertWidget(self._layout.count() - 2, button)

        self.empty_label.setVisible(not self._bookmarks)
        if invalid_count and not self._bookmarks:
            self.empty_label.setText("No usable bookmarks")
        else:
            self.empty_label.setText("No bookmarks yet")
        if invalid_count:
            self.setToolTip(f"Skipped {invalid_count} invalid bookmark record(s).")
        else:
            self.setToolTip("")
        self._layout_visible_items()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._layout_visible_items()

    def _layout_visible_items(self):
        if not hasattr(self, "_buttons"):
            return
        self.heading.setVisible(self.width() >= 450)
        self.empty_label.setVisible(not self._bookmarks)
        if not self._buttons:
            self.more_button.hide()
            self._more_menu.clear()
            return

        heading_width = self.heading.width() if self.width() >= 450 else 0
        fixed_width = heading_width + self.manage_button.width() + 34
        available = max(0, self.contentsRect().width() - fixed_width)
        total_width = sum(button.width() for button in self._buttons)
        spacing = self._layout.spacing()
        overflow = total_width + spacing * max(0, len(self._buttons) - 1) > available
        if overflow:
            available = max(0, available - self.more_button.width() - spacing)

        visible = []
        used = 0
        for button in self._buttons:
            next_width = button.width() + (spacing if visible else 0)
            if used + next_width > available:
                break
            visible.append(button)
            used += next_width

        for button in self._buttons:
            button.setVisible(button in visible)

        overflow_items = self._bookmarks[len(visible):]
        self.more_button.setVisible(bool(overflow_items))
        self._more_menu.clear()
        for item in overflow_items:
            action = self._more_menu.addAction(item["title"])
            action.setToolTip(item["url"])
            action.triggered.connect(lambda checked=False, url=item["url"]: self.url_activated.emit(url))
