import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
import shiboken6
from PySide6.QtCore import QCoreApplication, QEvent, QObject, QPoint, QSize, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QProgressBar, QPushButton

from ui.bookmarks_bar import BookmarksBar
from ui.bookmarks_dialog import BookmarksDialog
from ui.downloads_dialog import DownloadsDialog
from ui.navigation_bar import NavigationBar
from ui.settings import Settings
from ui.settings_window import ThemeSwitch
from ui.themes import dark_theme, light_theme


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def test_theme_switch_keeps_checkbox_state_and_changes_with_click(qapp):
    switch = ThemeSwitch()
    switch.setChecked(False)
    switch.show()
    qapp.processEvents()

    assert switch.isChecked() is False
    assert switch.accessibleName() == "Dark theme"
    assert switch.toolTip()

    QTest.mouseClick(switch, Qt.LeftButton, pos=QPoint(18, 18))
    qapp.processEvents()
    assert switch.isChecked() is True

    QTest.mouseClick(switch, Qt.LeftButton, pos=QPoint(50, 18))
    qapp.processEvents()
    assert switch.isChecked() is False

    switch.setChecked(True)
    assert switch.isChecked() is True
    switch.close()


def test_navigation_bar_stays_fixed_when_entering_long_or_rtl_search(qapp):
    navbar = NavigationBar(["Guest"], Settings())
    navbar.resize(1100, 42)
    navbar.show()
    qapp.processEvents()
    starting_geometry = navbar.url_bar.geometry()

    navbar.url_bar.setText("https://search.example/?q=" + "long-query-" * 100)
    qapp.processEvents()
    assert navbar.url_bar.geometry() == starting_geometry
    assert navbar.width() == 1100

    navbar.url_bar.setText("جستجوی آزمایشی")
    qapp.processEvents()
    assert navbar.layoutDirection() == Qt.LeftToRight
    assert navbar.url_bar.layoutDirection() == Qt.LeftToRight
    assert navbar.url_bar.geometry() == starting_geometry
    assert navbar.menu_button.text() == "⋮"
    assert navbar.menu_button.toolButtonStyle() == Qt.ToolButtonIconOnly
    assert not navbar.menu_button.icon().isNull()
    assert navbar.menu_button.size() == QSize(36, 32)
    assert navbar.menu_button.menu() is None
    assert navbar.menu_button.geometry().right() < navbar.width()
    navbar.close()


class FakeBookmarksManager:
    def __init__(self, records=()):
        self.records = [dict(record) for record in records]
        self.removed_ids = []
        self.remove_result = True

    def list_bookmarks(self):
        return [dict(record) for record in self.records]

    def add_bookmark(self, title, url):
        record = {"id": f"id-{len(self.records)}", "title": title, "url": url}
        self.records.append(record)
        return dict(record)

    def remove_bookmark(self, bookmark_id):
        self.removed_ids.append(bookmark_id)
        if not self.remove_result:
            return False
        before = len(self.records)
        self.records = [record for record in self.records if record.get("id") != bookmark_id]
        return len(self.records) != before


class FakeDownloadsManager(QObject):
    downloads_changed = Signal()

    def __init__(self, records=()):
        super().__init__()
        self.records = [dict(record) for record in records]
        self.cancelled_ids = []
        self.opened_ids = []
        self.cancel_result = True
        self.open_result = True
        self.clear_calls = 0

    def get_downloads(self):
        return [dict(record) for record in self.records]

    def cancel(self, download_id):
        self.cancelled_ids.append(download_id)
        if not self.cancel_result:
            return False
        for record in self.records:
            if record["id"] == download_id:
                record["state"] = "cancelled"
        self.downloads_changed.emit()
        return True

    def open_file(self, download_id):
        self.opened_ids.append(download_id)
        return self.open_result

    def clear_finished(self):
        self.clear_calls += 1
        self.records = [
            record for record in self.records
            if record["state"] not in {"completed", "cancelled", "failed"}
        ]
        self.downloads_changed.emit()


def bookmark(bookmark_id="bookmark-1", title="Example", url="https://example.com"):
    return {"id": bookmark_id, "title": title, "url": url}


def download(download_id, state, **changes):
    record = {
        "id": download_id,
        "file_name": f"{download_id}.bin",
        "path": "",
        "url": f"https://example.com/{download_id}",
        "received_bytes": 0,
        "total_bytes": -1,
        "state": state,
        "error": "",
    }
    record.update(changes)
    return record


def _buttons_in(dialog, row):
    cell = dialog.table.cellWidget(row, 3)
    return {button.text(): button for button in cell.findChildren(QPushButton)}


def _cell_labels(widget):
    return [label.text() for label in widget.findChildren(QLabel)]


def test_bookmarks_dialog_empty_populated_stale_and_stable_removal(qapp):
    empty_manager = FakeBookmarksManager()
    empty_dialog = BookmarksDialog(empty_manager)
    empty_dialog.show()
    qapp.processEvents()
    assert empty_dialog.empty_label.isVisible()
    assert empty_dialog.table.rowCount() == 0

    records = [
        bookmark("stable-id", "A title that is long enough to be elided in the table", "https://example.com/" + "path/" * 30),
        {"id": "stale", "title": None, "url": ""},
        {"title": "No stable id", "url": "https://example.net"},
    ]
    manager = FakeBookmarksManager(records)
    dialog = BookmarksDialog(manager)
    dialog.show()
    qapp.processEvents()
    assert dialog.table.rowCount() == 1
    assert dialog.status_label.text() == "Skipped 2 invalid bookmark record(s)."
    title_item = dialog.table.item(0, 0)
    address_item = dialog.table.item(0, 1)
    assert title_item.text().startswith("A title")
    assert address_item.toolTip() == records[0]["url"]

    dialog.table.selectRow(0)
    dialog.remove_selected()
    assert manager.removed_ids == ["stable-id"]
    assert dialog.table.rowCount() == 0
    assert dialog.empty_label.isVisible()

    manager.records = [bookmark("externally-removed")]
    dialog.refresh()
    dialog.table.selectRow(0)
    manager.records.clear()  # Simulate another owner removing it while the dialog is open.
    dialog.remove_selected()
    assert dialog.table.rowCount() == 0
    assert dialog.status_label.text() == "This bookmark no longer exists."


def test_bookmark_activation_is_explicit_and_emits_once_for_keyboard_and_button(qapp):
    dialog = BookmarksDialog(FakeBookmarksManager([bookmark()]))
    emitted = []
    dialog.url_activated.connect(emitted.append)
    assert emitted == []  # Constructing/showing the manager never navigates.

    dialog.table.setCurrentCell(0, 0)
    dialog.table.setFocus()
    QTest.keyClick(dialog.table, Qt.Key_Return)
    qapp.processEvents()
    assert emitted == ["https://example.com"]

    dialog = BookmarksDialog(FakeBookmarksManager([bookmark()]))
    emitted = []
    dialog.url_activated.connect(emitted.append)
    dialog.table.selectRow(0)
    QTest.mouseClick(dialog.open_button, Qt.LeftButton)
    assert emitted == ["https://example.com"]


def test_bookmark_bar_uses_compact_dropdown_and_activates_saved_bookmarks(qapp):
    bar = BookmarksBar()
    bar.show()
    records = [
        bookmark(f"id-{i}", f"Bookmark {i}", f"https://example.com/{i}")
        for i in range(8)
    ]
    bar.set_bookmarks(records)
    qapp.processEvents()

    assert bar.objectName() == "bookmarkMenuButton"
    assert bar.menu() is bar._more_menu
    assert len(bar.bookmark_actions) == len(records)
    assert bar._more_menu.actions()[-1].text() == "Manage bookmarks…"

    emitted = []
    bar.url_activated.connect(emitted.append)
    first_action = bar.bookmark_actions[0]
    first_action.trigger()
    assert emitted == ["https://example.com/0"]

    manage_requests = []
    bar.manage_requested.connect(lambda: manage_requests.append(True))
    bar._manage_action.trigger()
    assert manage_requests == [True]

    bar.set_bookmarks([bookmark("new", "Updated", "https://updated.example")])
    assert len(bar.bookmark_actions) == 1
    bar.bookmark_actions[0].trigger()
    assert emitted == ["https://example.com/0", "https://updated.example"]

    bar.set_bookmarks([])
    assert any(
        action.text() == "No bookmarks yet" and not action.isEnabled()
        for action in bar._more_menu.actions()
    )


def test_download_dialog_maps_all_manager_states_and_actions(qapp, tmp_path):
    completed_path = tmp_path / "empty.bin"
    completed_path.write_bytes(b"")
    manager = FakeDownloadsManager([
        download("requested-id", "requested"),
        download("active-id", "downloading", received_bytes=25),
        download("done-id", "completed", path=str(completed_path), total_bytes=0),
        download("cancelled-id", "cancelled", error="Cancelled by user"),
        download("failed-id", "failed", error="Connection interrupted"),
    ])
    dialog = DownloadsDialog(manager)
    assert [dialog.table.item(row, 2).text().splitlines()[0] for row in range(5)] == [
        "Requested", "Downloading", "Completed", "Cancelled", "Failed"
    ]
    assert set(_buttons_in(dialog, 0)) == {"Cancel"}
    assert set(_buttons_in(dialog, 1)) == {"Cancel"}
    assert set(_buttons_in(dialog, 2)) == {"Open", "Show folder"}
    assert _buttons_in(dialog, 3) == {}
    assert _buttons_in(dialog, 4) == {}
    assert "Cancelled by user" in dialog.table.item(3, 2).text()
    assert "Connection interrupted" in dialog.table.item(4, 2).text()
    progress = dialog.table.cellWidget(2, 1).findChild(QProgressBar)
    assert progress.value() == 100  # A completed zero-byte file avoids 0/0.
    assert "0 B of 0 B" in _cell_labels(dialog.table.cellWidget(2, 1))
    assert dialog.clear_button.isEnabled()
    dialog.clear_finished()
    assert manager.clear_calls == 1
    assert [record["id"] for record in manager.records] == ["requested-id", "active-id"]
    assert dialog.table.rowCount() == 2


def test_download_unknown_and_zero_totals_and_unknown_state_are_safe(qapp):
    manager = FakeDownloadsManager([
        download("unknown-total", "downloading", received_bytes=2048, total_bytes=-1),
        download("zero-total", "requested", total_bytes=0),
        download("unknown-state", "future-state"),
    ])
    dialog = DownloadsDialog(manager)

    unknown_progress = dialog.table.cellWidget(0, 1).findChild(QProgressBar)
    assert (unknown_progress.minimum(), unknown_progress.maximum()) == (0, 0)
    assert "2.0 KB downloaded · total unknown" in _cell_labels(dialog.table.cellWidget(0, 1))
    zero_progress = dialog.table.cellWidget(1, 1).findChild(QProgressBar)
    assert (zero_progress.minimum(), zero_progress.maximum()) == (0, 0)
    assert "0 B of 0 B" in _cell_labels(dialog.table.cellWidget(1, 1))
    assert dialog.table.item(2, 2).text() == "Status unavailable"
    assert _buttons_in(dialog, 2) == {}


def test_download_cancel_open_and_stale_operations_report_useful_results(qapp, tmp_path):
    completed_path = tmp_path / "available.bin"
    completed_path.write_bytes(b"content")
    manager = FakeDownloadsManager([
        download("active", "downloading"),
        download("terminal", "failed", error="Network error"),
        download("done", "completed", path=str(completed_path), total_bytes=7, received_bytes=7),
    ])
    dialog = DownloadsDialog(manager)
    emitted_errors = []
    dialog.operation_failed.connect(emitted_errors.append)

    dialog.cancel_download("active")
    assert manager.cancelled_ids == ["active"]
    assert next(row for row in manager.records if row["id"] == "active")["state"] == "cancelled"

    dialog.cancel_download("terminal")
    assert manager.cancelled_ids == ["active"]
    assert "already failed" in dialog.status_label.text()
    dialog.cancel_download("stale")
    assert "no longer available" in dialog.status_label.text()
    assert len(emitted_errors) == 2

    dialog.open_download("terminal")
    assert manager.opened_ids == []
    assert "Only completed downloads" in dialog.status_label.text()
    dialog.open_download("done")
    assert manager.opened_ids == ["done"]
    completed_path.unlink()
    dialog.open_download("done")
    assert manager.opened_ids == ["done"]
    assert "no longer available" in dialog.status_label.text()

    failed_manager = FakeDownloadsManager([download("still-active", "requested")])
    failed_manager.cancel_result = False
    failed_dialog = DownloadsDialog(failed_manager)
    failed_dialog.cancel_download("still-active")
    assert "could not be cancelled" in failed_dialog.status_label.text()


def test_downloads_changed_refreshes_once_and_deleted_dialog_disconnects(qapp):
    class CountedDialog(DownloadsDialog):
        def __init__(self, manager):
            self.refresh_count = 0
            super().__init__(manager)

        def refresh(self, *args):
            self.refresh_count += 1
            super().refresh(*args)

    manager = FakeDownloadsManager([download("one", "requested")])
    first = CountedDialog(manager)
    assert first.refresh_count == 1
    first.close()
    QCoreApplication.sendPostedEvents(first, QEvent.Type.DeferredDelete)
    qapp.processEvents()
    assert not shiboken6.isValid(first)

    second = CountedDialog(manager)
    assert second.refresh_count == 1
    manager.records[0]["state"] = "downloading"
    manager.downloads_changed.emit()
    assert second.refresh_count == 2
    assert second.table.item(0, 2).text() == "Downloading"


def _contrast(foreground, background):
    def luminance(color):
        rgb = [int(color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
        linear = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4 for value in rgb]
        return sum(channel * weight for channel, weight in zip(linear, (0.2126, 0.7152, 0.0722)))

    values = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (values[0] + 0.05) / (values[1] + 0.05)


@pytest.mark.parametrize(
    ("stylesheet", "foreground", "background"),
    [
        (light_theme, "#3f4752", "#f7f8fa"),
        (dark_theme, "#c7ced8", "#1b1e23"),
    ],
)
def test_theme_styles_dialogs_and_toolbar_glyph_contrast(qapp, stylesheet, foreground, background):
    qapp.setStyleSheet(stylesheet)
    assert "QToolBar#NavigationBar" in stylesheet
    assert "QLineEdit#urlBar:focus" in stylesheet
    assert 'QFrame#browserTab[active="true"]' in stylesheet
    assert "QMenu::item:selected" in stylesheet
    assert "QToolButton#windowCloseButton:hover" in stylesheet
    if "porcelain glass — light chrome" in stylesheet:
        assert _contrast("#26364c", "#ffffff") >= 4.5
    else:
        assert "obsidian glass — dark chrome" in stylesheet
        assert _contrast("#e7edf6", "#0f141c") >= 4.5
    dialog = BookmarksDialog(FakeBookmarksManager([bookmark()]))
    bar = BookmarksBar()
    bar.set_bookmarks([bookmark()])
    assert "QToolButton#navigationToolButton" in qapp.styleSheet()
    assert QColor(foreground).isValid() and QColor(background).isValid()
    assert _contrast(foreground, background) >= 4.5
    assert dialog.table.rowCount() == 1
    assert bar.bookmark_actions[0].text() == "Example"
    dialog.close()
    qapp.setStyleSheet("")



def test_theme_toggle_is_not_a_navigation_header_control(qapp):
    navbar = NavigationBar(["Guest"], settings=Settings())

    assert not hasattr(navbar, "theme_btn")
    assert not hasattr(navbar, "theme_toggle_requested")
    assert navbar.settings_btn in navbar.browser_menu.actions()

    navbar.close()
    navbar.deleteLater()
    qapp.processEvents()
