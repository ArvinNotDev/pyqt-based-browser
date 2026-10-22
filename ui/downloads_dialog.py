"""Download list backed by the browser profile's DownloadManager."""

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

from ._manager_ui import normalize_download


_ACTIVE = {"requested", "downloading"}
_TERMINAL = {"completed", "cancelled", "failed"}
_STATE_LABELS = {
    "requested": "Requested",
    "downloading": "Downloading",
    "completed": "Completed",
    "cancelled": "Cancelled",
    "failed": "Failed",
    "unknown": "Status unavailable",
}


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
        self.table.setFocusPolicy(Qt.StrongFocus)
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

        # The manager emits from its in-memory state transitions; the dialog
        # does not poll or perform work on a download's network path.
        self.manager.downloads_changed.connect(self.refresh)
        self.refresh()

    def refresh(self, *_signal_args):
        try:
            records = self.manager.get_downloads()
            if not isinstance(records, (list, tuple)):
                raise TypeError("get_downloads() must return a list of download records")
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
            download = normalize_download(record)
            if download is None:
                invalid_count += 1
            else:
                downloads.append(download)

        self.table.setRowCount(len(downloads))
        finished_count = 0
        for row, download in enumerate(downloads):
            state = download["status"]
            if state in _TERMINAL:
                finished_count += 1

            self._set_file_cell(row, download)
            self._set_progress_cell(row, download)
            self._set_status_cell(row, download)
            self._set_actions_cell(row, download)
            self.table.setRowHeight(row, 76)

        self.table.setVisible(bool(downloads))
        self.empty_label.setVisible(not downloads)
        self.empty_label.setText(
            "No downloads yet." if not records else "No usable downloads found."
        )
        self.clear_button.setEnabled(finished_count > 0)
        self._set_status(
            f"Skipped {invalid_count} invalid download record(s)." if invalid_count else ""
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

    def _set_progress_cell(self, row, download):
        cell = QWidget(self.table)
        cell.setObjectName("downloadCell")
        layout = QVBoxLayout(cell)
        layout.setContentsMargins(8, 9, 8, 9)
        layout.setSpacing(6)
        progress = QProgressBar(cell)
        progress.setTextVisible(False)

        state = download["status"]
        total = download["total"]
        received = download["received"]
        if total is not None:
            if total > 0:
                progress.setRange(0, 100)
                progress.setValue(100 if state == "completed" else min(100, received * 100 // total))
            elif state == "completed":
                progress.setRange(0, 100)
                progress.setValue(100)
            elif state in _ACTIVE:
                # A known zero-byte total cannot produce a meaningful ratio.
                progress.setRange(0, 0)
            else:
                progress.setRange(0, 100)
                progress.setValue(0)
            size_text = f"{_format_size(received)} of {_format_size(total)}"
        elif state in _ACTIVE:
            progress.setRange(0, 0)
            size_text = f"{_format_size(received)} downloaded · total unknown"
        else:
            progress.setRange(0, 100)
            progress.setValue(100 if state == "completed" else 0)
            size_text = _size_for_download(download)

        size_label = QLabel(size_text, cell)
        size_label.setObjectName("dialogStatus")
        layout.addWidget(progress)
        layout.addWidget(size_label)
        self.table.setCellWidget(row, 1, cell)

    def _set_status_cell(self, row, download):
        state = download["status"]
        text = _STATE_LABELS[state]
        if download["error"]:
            text = f"{text}\n{download['error']}"
        status_item = QTableWidgetItem(text)
        status_item.setToolTip(download["error"] or text)
        self.table.setItem(row, 2, status_item)

    def _set_actions_cell(self, row, download):
        cell = QWidget(self.table)
        cell.setObjectName("downloadCell")
        layout = QHBoxLayout(cell)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        path = download["path"]
        download_id = download["id"]
        state = download["status"]
        valid_file = state == "completed" and _is_file(path)
        valid_folder = state == "completed" and _is_folder_for(path)

        if state in _ACTIVE and download_id:
            cancel_button = QPushButton("Cancel", cell)
            cancel_button.setToolTip("Cancel this download")
            cancel_button.setAccessibleName(f"Cancel {download['filename']}")
            cancel_button.clicked.connect(
                lambda checked=False, current_id=download_id: self.cancel_download(current_id)
            )
            layout.addWidget(cancel_button)
        elif state == "completed" and valid_file and download_id:
            open_button = QPushButton("Open", cell)
            open_button.setToolTip("Open the completed file")
            open_button.setAccessibleName(f"Open {download['filename']}")
            open_button.clicked.connect(
                lambda checked=False, current_id=download_id: self.open_download(current_id)
            )
            layout.addWidget(open_button)

        if state == "completed" and valid_folder and download_id:
            folder_button = QPushButton("Show folder", cell)
            folder_button.setToolTip("Open the folder containing the completed file")
            folder_button.setAccessibleName(f"Show folder for {download['filename']}")
            folder_button.clicked.connect(
                lambda checked=False, current_id=download_id: self.open_download_folder(current_id)
            )
            layout.addWidget(folder_button)

        layout.addStretch(1)
        self.table.setCellWidget(row, 3, cell)

    def _find_download(self, download_id):
        records = self.manager.get_downloads()
        if not isinstance(records, (list, tuple)):
            raise TypeError("get_downloads() must return a list of download records")
        for record in records:
            download = normalize_download(record)
            if download is not None and download["id"] == download_id:
                return download
        return None

    def cancel_download(self, download_id):
        if not download_id:
            self._report_error("This download has no identifier to cancel.")
            return
        try:
            download = self._find_download(download_id)
            if download is None:
                self.refresh()
                self._report_error("This download is no longer available.")
                return
            if download["status"] not in _ACTIVE:
                label = _STATE_LABELS[download["status"]].lower()
                self.refresh()
                if download["status"] in _TERMINAL:
                    self._report_error(f"This download is already {label}.")
                else:
                    self._report_error("This download cannot be cancelled because its status is unavailable.")
                return
            cancelled = self.manager.cancel(download_id)
        except Exception as error:
            self._report_error(f"Could not cancel download: {error}")
            return

        self.refresh()
        if not cancelled:
            self._report_error("The download could not be cancelled; it may have finished already.")
        else:
            self._set_status("")

    def open_download(self, download_id):
        try:
            download = self._find_download(download_id)
            if download is None:
                self.refresh()
                self._report_error("This download is no longer available.")
                return
            if download["status"] != "completed":
                self.refresh()
                self._report_error("Only completed downloads can be opened.")
                return
            if not _is_file(download["path"]):
                self.refresh()
                self._report_error("The completed file is no longer available.")
                return
            opened = self.manager.open_file(download_id)
        except Exception as error:
            self._report_error(f"Could not open download: {error}")
            return

        if not opened:
            self._report_error("The download manager could not open this file.")
        else:
            self._set_status("")

    def open_download_folder(self, download_id):
        try:
            download = self._find_download(download_id)
        except Exception as error:
            self._report_error(f"Could not locate download folder: {error}")
            return
        if download is None or download["status"] != "completed":
            self._report_error("This completed download is no longer available.")
            return
        folder = os.path.dirname(os.path.abspath(download["path"])) if download["path"] else ""
        if not folder or not os.path.isdir(folder):
            self._report_error("The download folder is no longer available.")
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(folder)):
            self._report_error(f"Could not open the folder: {folder}")
        else:
            self._set_status("")

    def clear_finished(self):
        try:
            self.manager.clear_finished()
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


def _format_size(value):
    number = max(0, int(value))
    units = ("B", "KB", "MB", "GB", "TB")
    amount = float(number)
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            break
        amount /= 1024
    return f"{int(amount)} {unit}" if unit == "B" else f"{amount:.1f} {unit}"


def _size_for_download(download):
    if download["status"] == "completed" and _is_file(download["path"]):
        try:
            return _format_size(os.path.getsize(download["path"]))
        except OSError:
            pass
    if download["received"] or download["status"] in _ACTIVE:
        return f"{_format_size(download['received'])} downloaded · total unknown"
    return "Size unknown"


def _is_file(path):
    try:
        return bool(path) and os.path.isfile(path)
    except (OSError, TypeError, ValueError):
        return False


def _is_folder_for(path):
    try:
        return bool(path) and os.path.isdir(os.path.dirname(os.path.abspath(path)))
    except (OSError, TypeError, ValueError):
        return False
