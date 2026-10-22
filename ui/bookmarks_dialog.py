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

from ._manager_ui import call_manager, manager_records, normalize_bookmark


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
        self.open_button.setDefault(True)
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
        self._connect_manager_signal()
        self.refresh()

    def _connect_manager_signal(self):
        signal = getattr(self.manager, "bookmarks_changed", None)
        if signal is not None and callable(getattr(signal, "connect", None)):
            signal.connect(self.refresh)

    def refresh(self):
        try:
            records = manager_records(
                self.manager,
                methods=("get_bookmarks", "list_bookmarks"),
                attributes=("bookmarks", "items"),
            )
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
            try:
                bookmark = normalize_bookmark(record)
            except Exception as error:
                self._set_status(f"Skipped an unreadable bookmark record: {error}")
                invalid_count += 1
                continue
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
            call_manager(
                self.manager,
                ("remove_bookmark", "delete_bookmark", "remove"),
                bookmark["id"],
            )
        except Exception as error:
            self._set_status(f"Could not remove bookmark: {error}")
            return
        self._set_status("")
        self.refresh()

    def _set_status(self, text: str):
        self.status_label.setText(text)
        self.status_label.setVisible(bool(text))
