"""Non-blocking download list backed by an injected DownloadManager."""

import os

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QFontMetrics
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ._manager_ui import call_manager, manager_records, normalize_download


_ACTIVE = {"created", "queued", "pending", "running", "downloading", "in_progress", "started"}
_COMPLETED = {"complete", "completed", "finished", "succeeded", "success"}
_CANCELLED = {"cancelled", "canceled", "aborted"}
_FAILED = {"failed", "error", "interrupted"}


class DownloadsDialog(QDialog):
    operation_failed = Signal(str)

    def __init__(self, manager, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.manager = manager
        self.setWindowTitle("Downloads")
        self.setMinimumSize(700, 420)
        self.resize(900, 560)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 16)
        root.setSpacing(12)

        title = QLabel("Downloads", self)
        title.setObjectName("dialogTitle")
        root.addWidget(title)

        self.table = QTableWidget(0, 4, self)
        self.table.setHorizontalHeaderLabels(["File", "Progress and size", "Status", "Actions"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().hide()
        self.table.setShowGrid(False)
        header = self.table.horizontalHeader()
        header.setMinimumSectionSize(90)
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        header.setSectionResizeMode(3, QHeaderView.Fixed)
        self.table.setColumnWidth(0, 270)
        self.table.setColumnWidth(2, 120)
        self.table.setColumnWidth(3, 190)
        root.addWidget(self.table, 1)

        self.empty_label = QLabel("No downloads yet.", self)
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
        self.clear_button = QPushButton("Clear finished", self)
        self.clear_button.clicked.connect(self.clear_finished)
        buttons.addWidget(self.clear_button)
        close_button = QPushButton("Close", self)
        close_button.clicked.connect(self.reject)
        buttons.addWidget(close_button)
        root.addLayout(buttons)

        self._connect_manager_signal()
        self.refresh()

    def _connect_manager_signal(self):
        signal = getattr(self.manager, "downloads_changed", None)
        if signal is not None and callable(getattr(signal, "connect", None)):
            signal.connect(self.refresh)

    def refresh(self):
        try:
            records = manager_records(
                self.manager,
                methods=("get_downloads", "list_downloads"),
                attributes=("downloads", "items"),
            )
        except Exception as error:
            self._set_status(f"Could not load downloads: {error}")
            self.table.setRowCount(0)
            self.table.hide()
            self.empty_label.setText("Downloads are unavailable.")
            self.empty_label.show()
            self.clear_button.setEnabled(False)
            return

        downloads = []
        invalid_count = 0
        for record in records:
            try:
                downloads.append(normalize_download(record))
            except Exception as error:
                invalid_count += 1
                self._report_error(f"Skipped an unreadable download record: {error}")
        self.table.setRowCount(len(downloads))
        finished_count = 0
        for row, download in enumerate(downloads):
            state = download["status"]
            complete = state in _COMPLETED
            if complete or state in _CANCELLED or state in _FAILED:
                finished_count += 1

            self._set_file_cell(row, download)
            self._set_progress_cell(row, download, state)
            self._set_status_cell(row, download, state)
            self._set_actions_cell(row, download, state)
            self.table.setRowHeight(row, 76)

        self.table.setVisible(bool(downloads))
        self.empty_label.setVisible(not downloads)
        self.empty_label.setText("No downloads yet.")
        self.clear_button.setEnabled(finished_count > 0)
        self._set_status(
            f"Skipped {invalid_count} unreadable download record(s)." if invalid_count else ""
        )

    def _set_file_cell(self, row, download):
        cell = QWidget(self.table)
        cell.setObjectName("downloadCell")
        layout = QVBoxLayout(cell)
        layout.setContentsMargins(8, 5, 8, 5)
        layout.setSpacing(3)
        metrics = QFontMetrics(self.font())
        filename = QLabel(metrics.elidedText(download["filename"], Qt.ElideRight, 245), cell)
        filename.setToolTip(download["path"] or download["filename"])
        filename.setTextInteractionFlags(Qt.TextSelectableByMouse)
        origin_text = download["url"] or "Origin unavailable"
        origin = QLabel(metrics.elidedText(origin_text, Qt.ElideMiddle, 245), cell)
        origin.setObjectName("dialogStatus")
        origin.setToolTip(download["url"])
        origin.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(filename)
        layout.addWidget(origin)
        self.table.setCellWidget(row, 0, cell)

    def _set_progress_cell(self, row, download, state):
        cell = QWidget(self.table)
        cell.setObjectName("downloadCell")
        layout = QVBoxLayout(cell)
        layout.setContentsMargins(8, 9, 8, 9)
        layout.setSpacing(6)
        progress = QProgressBar(cell)
        progress.setTextVisible(False)
        total = _positive_int(download["total"])
        received = _positive_int(download["received"])
        percent = _progress_percent(download["progress"])
        if total:
            value = min(100, int(received * 100 / total))
            progress.setRange(0, 100)
            progress.setValue(100 if state in _COMPLETED else value)
            size_text = f"{_format_size(received)} of {_format_size(total)}"
        elif state in _COMPLETED:
            progress.setRange(0, 100)
            progress.setValue(100)
            size_text = _size_for_download(download)
        elif state in _ACTIVE:
            progress.setRange(0, 0)
            size_text = f"{_format_size(received)} downloaded · total unknown"
        else:
            progress.setRange(0, 100)
            progress.setValue(min(100, percent))
            size_text = _size_for_download(download)
        size_label = QLabel(size_text, cell)
        size_label.setObjectName("dialogStatus")
        layout.addWidget(progress)
        layout.addWidget(size_label)
        self.table.setCellWidget(row, 1, cell)

    def _set_status_cell(self, row, download, state):
        if state in _COMPLETED:
            text = "Completed"
        elif state in _CANCELLED:
            text = "Cancelled"
        elif state in _FAILED:
            text = "Failed"
        elif state in _ACTIVE:
            text = "In progress"
        else:
            text = "Status unknown"
        if download["error"]:
            text = f"{text}\n{download['error']}"
        status_item = QTableWidgetItem(text)
        status_item.setToolTip(download["error"] or text)
        self.table.setItem(row, 2, status_item)

    def _set_actions_cell(self, row, download, state):
        cell = QWidget(self.table)
        cell.setObjectName("downloadCell")
        layout = QHBoxLayout(cell)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        path = download["path"]
        usable_file = state in _COMPLETED and bool(path) and os.path.isfile(path)
        usable_folder = usable_file and os.path.isdir(os.path.dirname(os.path.abspath(path)))

        identifier = download["id"] if download["id"] is not None else path
        if state in _ACTIVE:
            cancel_button = QPushButton("Cancel", cell)
            cancel_button.setEnabled(identifier is not None)
            cancel_button.setToolTip("Cancel this download")
            cancel_button.clicked.connect(
                lambda checked=False, download_id=identifier: self.cancel_download(download_id)
            )
            layout.addWidget(cancel_button)
        elif state in _COMPLETED and usable_file:
            open_button = QPushButton("Open", cell)
            open_button.setToolTip("Open the completed file")
            open_button.clicked.connect(lambda checked=False, p=path: self._open_path(p))
            layout.addWidget(open_button)

            if usable_folder:
                folder_button = QPushButton("Show folder", cell)
                folder_button.setToolTip("Open the folder containing the completed file")
                folder_button.clicked.connect(lambda checked=False, p=path: self._open_folder(p))
                layout.addWidget(folder_button)
        layout.addStretch(1)
        self.table.setCellWidget(row, 3, cell)

    def _open_path(self, path):
        if not path or not os.path.isfile(path):
            self._report_error("The completed file is no longer available.")
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.abspath(path))):
            self._report_error(f"Could not open the file: {path}")

    def _open_folder(self, path):
        folder = os.path.dirname(os.path.abspath(path)) if path else ""
        if not folder or not os.path.isdir(folder):
            self._report_error("The download folder is no longer available.")
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(folder)):
            self._report_error(f"Could not open the folder: {folder}")

    def cancel_download(self, download_id):
        if download_id is None:
            self._report_error("This download has no identifier to cancel.")
            return
        try:
            call_manager(self.manager, ("cancel_download", "cancel"), download_id)
        except Exception as error:
            self._report_error(f"Could not cancel download: {error}")
            return
        self._set_status("")
        self.refresh()

    def clear_finished(self):
        try:
            call_manager(
                self.manager,
                ("clear_finished_downloads", "clear_finished", "clear_completed_downloads"),
            )
        except Exception as error:
            self._report_error(f"Could not clear finished downloads: {error}")
            return
        self._set_status("")
        self.refresh()

    def _report_error(self, message):
        self._set_status(message)
        self.operation_failed.emit(message)

    def _set_status(self, text):
        self.status_label.setText(text)
        self.status_label.setVisible(bool(text))


def _positive_int(value):
    try:
        return max(0, int(value)) if value is not None else 0
    except (TypeError, ValueError, OverflowError):
        return 0


def _progress_percent(value):
    try:
        value = float(value)
    except (TypeError, ValueError, OverflowError):
        return 0
    if 0 <= value <= 1:
        value *= 100
    return max(0, min(100, int(value)))


def _format_size(value):
    number = _positive_int(value)
    units = ("B", "KB", "MB", "GB", "TB")
    amount = float(number)
    unit = units[0]
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            break
        amount /= 1024
    return f"{int(amount)} {unit}" if unit == "B" else f"{amount:.1f} {unit}"


def _size_for_download(download):
    total = _positive_int(download["total"])
    if total:
        return _format_size(total)
    path = download["path"]
    if download["status"] in _COMPLETED and path and os.path.isfile(path):
        try:
            return _format_size(os.path.getsize(path))
        except OSError:
            return "Size unavailable"
    return "Size unknown"
