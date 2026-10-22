"""Bookmark management dialog backed by an injected BookmarksManager."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ._manager_ui import normalize_bookmark


class BookmarksDialog(QDialog):
    url_activated = Signal(str)

    def __init__(self, manager, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.manager = manager
        self.setWindowTitle("Bookmarks")
        self.setMinimumSize(600, 400)
        self.resize(760, 500)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 16)
        root.setSpacing(12)

        title = QLabel("Bookmarks", self)
        title.setObjectName("dialogTitle")
        root.addWidget(title)

        self.table = QTableWidget(0, 2, self)
        self.table.setHorizontalHeaderLabels(["Title", "Address"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setFocusPolicy(Qt.StrongFocus)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setMinimumSectionSize(100)
        self.table.setColumnWidth(0, 190)
        self.table.setShowGrid(False)
        self.table.itemActivated.connect(lambda _item: self.open_selected())
        root.addWidget(self.table, 1)

        self.empty_label = QLabel("No bookmarks saved yet.", self)
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.hide()
        root.addWidget(self.empty_label)

        self.status_label = QLabel(self)
        self.status_label.setObjectName("dialogStatus")
        self.status_label.setWordWrap(True)
        self.status_label.hide()
        root.addWidget(self.status_label)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.open_button = QPushButton("Open", self)
        self.open_button.setObjectName("primaryButton")
        self.open_button.setAutoDefault(False)
        self.open_button.clicked.connect(self.open_selected)
        buttons.addWidget(self.open_button)

        self.remove_button = QPushButton("Remove", self)
        self.remove_button.setObjectName("dangerButton")
        self.remove_button.clicked.connect(self.remove_selected)
        buttons.addWidget(self.remove_button)

        close_button = QPushButton("Close", self)
        close_button.clicked.connect(self.reject)
        buttons.addWidget(close_button)
        root.addLayout(buttons)

        self.table.itemSelectionChanged.connect(self._update_buttons)
        self.refresh()

    def refresh(self):
        try:
            records = self.manager.list_bookmarks()
            if not isinstance(records, (list, tuple)):
                raise TypeError("list_bookmarks() must return a list of bookmark records")
        except Exception as error:
            self._set_status(f"Could not load bookmarks: {error}")
            self.table.setRowCount(0)
            self.empty_label.setText("Bookmarks are unavailable.")
            self.empty_label.show()
            self.table.hide()
            self._update_buttons()
            return

        normalized = []
        invalid_count = 0
        for record in records:
            bookmark = normalize_bookmark(record)
            if bookmark is None:
                invalid_count += 1
            else:
                normalized.append(bookmark)
        self.table.setRowCount(len(normalized))
        for row, bookmark in enumerate(normalized):
            title_item = QTableWidgetItem(bookmark["title"])
            title_item.setData(Qt.UserRole, bookmark)
            title_item.setToolTip(bookmark["url"])
            url_item = QTableWidgetItem(bookmark["url"])
            url_item.setToolTip(bookmark["url"])
            self.table.setItem(row, 0, title_item)
            self.table.setItem(row, 1, url_item)
            self.table.setRowHeight(row, 34)

        invalid_count = max(invalid_count, len(records) - len(normalized))
        self.table.setVisible(bool(normalized))
        self.empty_label.setVisible(not normalized)
        self.empty_label.setText("No bookmarks saved yet." if not records else "No usable bookmarks found.")
        if invalid_count:
            self._set_status(f"Skipped {invalid_count} invalid bookmark record(s).")
        else:
            self._set_status("")
        self._update_buttons()

    def _selected_bookmark(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        return item.data(Qt.UserRole) if item else None

    def _update_buttons(self):
        selected = self._selected_bookmark() is not None
        self.open_button.setEnabled(selected)
        self.remove_button.setEnabled(selected)

    def open_selected(self):
        bookmark = self._selected_bookmark()
        if bookmark is None:
            return
        self.url_activated.emit(bookmark["url"])
        self.accept()

    def remove_selected(self):
        bookmark = self._selected_bookmark()
        if bookmark is None:
            return
        try:
            removed = self.manager.remove_bookmark(bookmark["id"])
        except Exception as error:
            self._set_status(f"Could not remove bookmark: {error}")
            return
        if not removed:
            self.refresh()
            self._set_status("This bookmark no longer exists.")
            return
        self._set_status("")
        self.refresh()

    def _set_status(self, text: str):
        self.status_label.setText(text)
        self.status_label.setVisible(bool(text))
