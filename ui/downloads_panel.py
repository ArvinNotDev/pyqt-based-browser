"""Animated, in-window download center with per-item actions."""

from __future__ import annotations

import os

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


_ACTIVE = {"requested", "downloading"}
_TERMINAL = {"completed", "cancelled", "failed"}


class DownloadsPanel(QFrame):
    """A left-side download drawer that keeps its actions beside each item."""

    close_requested = Signal()
    mode_toggle_requested = Signal()
    PANEL_WIDTH = 368

    def __init__(self, manager=None, parent=None):
        super().__init__(parent)
        self.setObjectName("downloadsPanel")
        self.setMinimumWidth(245)
        self.setMaximumWidth(600)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        self._manager = None
        self._is_open = False

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 14)
        root.setSpacing(10)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(1)
        title = QLabel("Downloads", self)
        title.setObjectName("downloadsTitle")
        title_box.addWidget(title)
        self.count_label = QLabel("Your recent files", self)
        self.count_label.setObjectName("downloadsSubtitle")
        title_box.addWidget(self.count_label)
        header.addLayout(title_box, 1)
        self.close_button = QToolButton(self)
        self.close_button.setObjectName("downloadsCloseButton")
        self.close_button.setText("×")
        self.close_button.setToolTip("Close downloads panel")
        self.close_button.setAccessibleName("Close downloads panel")
        self.mode_button = QToolButton(self)
        self.mode_button.setObjectName("downloadsModeButton")
        self.mode_button.setText("Dock")
        self.mode_button.setToolTip("Keep downloads pinned beside the page")
        self.mode_button.setAccessibleName("Change downloads panel layout")
        self.mode_button.clicked.connect(self.mode_toggle_requested.emit)
        header.addWidget(self.mode_button)
        self.close_button.clicked.connect(self.close_requested.emit)
        header.addWidget(self.close_button)
        root.addLayout(header)

        self.search = QLineEdit(self)
        self.search.setObjectName("downloadsSearch")
        self.search.setPlaceholderText("Search downloads")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.refresh)
        root.addWidget(self.search)

        tools = QHBoxLayout()
        tools.setSpacing(7)
        self.folder_button = QPushButton("Open folder", self)
        self.folder_button.setObjectName("downloadsSecondaryButton")
        self.folder_button.clicked.connect(self.open_download_folder)
        tools.addWidget(self.folder_button)
        self.clear_button = QPushButton("Clear finished", self)
        self.clear_button.setObjectName("downloadsSecondaryButton")
        self.clear_button.clicked.connect(self.clear_finished)
        tools.addWidget(self.clear_button)
        root.addLayout(tools)

        self.scroll = QScrollArea(self)
        self.scroll.setObjectName("downloadsScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list_host = QWidget(self.scroll)
        self.list_layout = QVBoxLayout(self.list_host)
        self.list_layout.setContentsMargins(0, 2, 0, 2)
        self.list_layout.setSpacing(9)
        self.empty_label = QLabel("Downloads you start will appear here.", self.list_host)
        self.empty_label.setObjectName("downloadsEmpty")
        self.empty_label.setWordWrap(True)
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.list_layout.addWidget(self.empty_label)
        self.list_layout.addStretch(1)
        self.scroll.setWidget(self.list_host)
        root.addWidget(self.scroll, 1)

        self.set_manager(manager)

    @property
    def is_open(self) -> bool:
        return self._is_open

    def set_manager(self, manager) -> None:
        if self._manager is manager:
            self.refresh()
            return
        if self._manager is not None:
            try:
                self._manager.downloads_changed.disconnect(self.refresh)
            except (AttributeError, RuntimeError, TypeError):
                pass
        self._manager = manager
        if manager is not None:
            manager.downloads_changed.connect(self.refresh)
        self.refresh()

    def open(self) -> None:
        self._is_open = True
        self.show()

    def close_panel(self) -> None:
        self._is_open = False

    def set_docked(self, docked: bool) -> None:
        """Label the one-click action that switches between overlay and split layouts."""
        self.mode_button.setText("Overlay" if docked else "Dock")
        self.mode_button.setToolTip(
            "Show downloads over the page without resizing it"
            if docked else "Keep downloads pinned beside the page and reserve its width"
        )

    def refresh(self, *_args) -> None:
        while self.list_layout.count() > 0:
            item = self.list_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        all_records = []
        if self._manager is not None:
            try:
                all_records = self._manager.get_downloads()
            except Exception:
                all_records = []
        records = all_records
        query = self.search.text().strip().casefold()
        if query:
            records = [
                item for item in records
                if query in str(item.get("file_name", "")).casefold()
                or query in str(item.get("url", "")).casefold()
            ]

        self.empty_label = QLabel(
            (
                "Download management is unavailable in this session."
                if self._manager is None
                else "Downloads you start will appear here."
                if not all_records
                else "No downloads match your search."
            ),
            self.list_host,
        )
        self.empty_label.setObjectName("downloadsEmpty")
        self.empty_label.setWordWrap(True)
        self.empty_label.setAlignment(Qt.AlignCenter)
        if records:
            for download in reversed(records):
                card = self._make_card(download)
                self.list_layout.addWidget(card)
        else:
            self.list_layout.addWidget(self.empty_label, 1)
        self.list_layout.addStretch(1)
        total_count = len(all_records)
        self.count_label.setText(f"{total_count} item" if total_count == 1 else f"{total_count} items")
        self.clear_button.setEnabled(any(item.get("state") in _TERMINAL for item in all_records))

    def _make_card(self, download: dict) -> QFrame:
        card = QFrame(self.list_host)
        card.setObjectName("downloadCard")
        card.setProperty("downloadState", str(download.get("state", "unknown")))
        layout = QVBoxLayout(card)
        layout.setContentsMargins(11, 10, 11, 10)
        layout.setSpacing(7)

        top = QHBoxLayout()
        top.setSpacing(7)
        name = QLabel(str(download.get("file_name") or "Download"), card)
        name.setObjectName("downloadFileName")
        name.setWordWrap(True)
        name.setToolTip(str(download.get("path", "")))
        top.addWidget(name, 1)
        menu_button = QToolButton(card)
        menu_button.setObjectName("downloadMoreButton")
        menu_button.setText("⋮")
        menu_button.setToolTip("Download actions")
        menu_button.clicked.connect(lambda _checked=False, b=menu_button, d=download: self._show_item_menu(d, b))
        top.addWidget(menu_button)
        layout.addLayout(top)

        source = QLabel(str(download.get("url", "")), card)
        source.setObjectName("downloadSource")
        source.setWordWrap(True)
        source.setTextInteractionFlags(Qt.TextSelectableByMouse)
        source.setToolTip(str(download.get("url", "")))
        layout.addWidget(source)

        state = str(download.get("state", "unknown"))
        received = max(0, int(download.get("received_bytes", 0) or 0))
        total = int(download.get("total_bytes", -1) or -1)
        status_text = self._status_text(download, received, total)
        status = QLabel(status_text, card)
        status.setObjectName("downloadStatus")
        status.setWordWrap(True)
        layout.addWidget(status)
        if state in _ACTIVE:
            progress = QProgressBar(card)
            progress.setObjectName("downloadProgress")
            progress.setTextVisible(False)
            progress.setFixedHeight(5)
            if total > 0:
                progress.setRange(0, 100)
                progress.setValue(min(100, int(received * 100 / total)))
            else:
                progress.setRange(0, 0)
            layout.addWidget(progress)

        actions = QHBoxLayout()
        actions.addStretch(1)
        primary = QPushButton("Open file" if state == "completed" else "Cancel" if state in _ACTIVE else "Actions", card)
        primary.setObjectName("downloadsPrimaryButton")
        # Terminal records still need the Actions menu (copy URL, show folder,
        # remove from list, and delete a completed file where applicable).
        primary.setEnabled(True)
        download_id = download.get("id")
        if state == "completed":
            primary.clicked.connect(lambda _checked=False, current_id=download_id: self._open_file(current_id))
        elif state in _ACTIVE:
            primary.clicked.connect(lambda _checked=False, current_id=download_id: self._cancel(current_id))
        else:
            primary.clicked.connect(lambda _checked=False, b=primary, d=download: self._show_item_menu(d, b))
        actions.addWidget(primary)
        layout.addLayout(actions)
        return card

    @staticmethod
    def _status_text(download: dict, received: int, total: int) -> str:
        state = str(download.get("state", "unknown"))
        labels = {
            "requested": "Starting…",
            "downloading": "Downloading",
            "completed": "Completed",
            "cancelled": "Cancelled",
            "failed": "Failed",
        }
        if download.get("paused") and state in _ACTIVE:
            state_text = "Paused"
        else:
            state_text = labels.get(state, "Status unavailable")
        if state in _ACTIVE and total > 0:
            return f"{state_text} · {received / 1_048_576:.1f} / {total / 1_048_576:.1f} MB"
        if state in _ACTIVE:
            return f"{state_text} · {received / 1_048_576:.1f} MB"
        error = str(download.get("error", ""))
        return f"{state_text} · {error}" if error else state_text

    def _show_item_menu(self, download: dict, button: QWidget) -> None:
        menu = QMenu(self)
        copy_url = menu.addAction("Copy URL")
        open_file = menu.addAction("Open file")
        show_folder = menu.addAction("Show in folder")
        menu.addSeparator()
        state = str(download.get("state", "unknown"))
        if state in _ACTIVE:
            pause_text = "Resume" if download.get("paused") else "Pause"
            pause_resume = menu.addAction(pause_text)
            pause_resume.setEnabled(state == "downloading")
            cancel = menu.addAction("Cancel download")
        else:
            pause_resume = cancel = None
        if state in _TERMINAL:
            remove = menu.addAction("Remove from list")
        else:
            remove = None
        if state == "completed":
            delete_file = menu.addAction("Delete downloaded file…")
        else:
            delete_file = None
        open_file.setEnabled(state == "completed")
        show_folder.setEnabled(bool(download.get("path")))
        selected = self._exec_item_menu(menu, button)
        download_id = download.get("id")
        if selected is copy_url:
            QApplication.clipboard().setText(str(download.get("url", "")))
            self._message("Download URL copied to clipboard.")
        elif selected is open_file:
            self._open_file(download_id)
        elif selected is show_folder:
            self._run_manager_action("open_folder", download_id, "Could not open the download folder.")
        elif selected is pause_resume:
            method = "resume" if download.get("paused") else "pause"
            self._run_manager_action(method, download_id, "Could not update this download.")
        elif selected is cancel:
            self._cancel(download_id)
        elif selected is remove:
            self._run_manager_action("remove_download", download_id, "Could not remove this item.")
        elif selected is delete_file:
            self._delete_file(download)

    @staticmethod
    def _exec_item_menu(menu: QMenu, button: QWidget):
        """Show a download action menu; isolated for deterministic UI tests."""
        return menu.exec(button.mapToGlobal(button.rect().bottomLeft()))

    def _delete_file(self, download: dict) -> None:
        answer = QMessageBox.question(
            self,
            "Delete downloaded file?",
            f"Permanently delete “{download.get('file_name', 'this file')}”?",
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        if answer != QMessageBox.Yes:
            return
        if not self._run_manager_action("delete_download_file", download.get("id"), "Could not delete this file."):
            return
        self._message("Downloaded file deleted.")

    def _open_file(self, download_id: str) -> None:
        self._run_manager_action("open_file", download_id, "Could not open this file.")

    def _cancel(self, download_id: str) -> None:
        self._run_manager_action("cancel", download_id, "Could not cancel this download.")

    def _run_manager_action(self, method: str, download_id: str, failure_message: str) -> bool:
        if self._manager is None:
            self._message("Downloads are unavailable in this session.")
            return False
        try:
            result = bool(getattr(self._manager, method)(download_id))
        except Exception:
            result = False
        if not result:
            self._message(failure_message)
        return result

    def clear_finished(self) -> None:
        if self._manager is not None:
            self._manager.clear_finished()

    def open_download_folder(self) -> None:
        folder = getattr(self._manager, "download_dir", "") if self._manager is not None else ""
        if folder and os.path.isdir(folder):
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.abspath(folder)))
        else:
            self._message("The download folder is unavailable.")

    def _message(self, message: str) -> None:
        parent = self.window()
        status_bar = getattr(parent, "statusBar", lambda: None)()
        if status_bar is not None:
            status_bar.showMessage(message, 3000)
