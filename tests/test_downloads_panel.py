from types import SimpleNamespace
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ui.browser_window import BrowserWindow
from ui.downloads_panel import DownloadsPanel


class _DownloadsModeHarness:
    _toggle_downloads_panel_mode = BrowserWindow._toggle_downloads_panel_mode
    _switch_downloads_panel_mode = BrowserWindow._switch_downloads_panel_mode
    _stop_downloads_panel_animation = BrowserWindow._stop_downloads_panel_animation
    _downloads_split_target_width = BrowserWindow._downloads_split_target_width
    _finish_mode_switch_to_split = BrowserWindow._finish_mode_switch_to_split
    _finish_mode_switch_to_overlay = BrowserWindow._finish_mode_switch_to_overlay
    _finish_mode_switch_overlay_animation = BrowserWindow._finish_mode_switch_overlay_animation
    _finish_downloads_mode_transition = BrowserWindow._finish_downloads_mode_transition
    _show_downloads_overlay_dismiss_area = BrowserWindow._show_downloads_overlay_dismiss_area
    _hide_downloads_overlay_dismiss_area = BrowserWindow._hide_downloads_overlay_dismiss_area


def _make_mode_harness(start_mode="overlay"):
    app = QApplication.instance() or QApplication([])
    row = QWidget()
    row.resize(1000, 620)
    splitter = QSplitter(Qt.Horizontal, row)
    splitter.setGeometry(row.rect())
    panel = DownloadsPanel()
    view_container = QWidget(splitter)
    view_layout = QVBoxLayout(view_container)
    view_layout.setContentsMargins(0, 0, 0, 0)
    page_surface = QWidget(view_container)
    page_surface.setObjectName("activeSitePage")
    view_layout.addWidget(page_surface)

    if start_mode == "split":
        panel.setParent(splitter)
        splitter.addWidget(panel)
        splitter.addWidget(view_container)
        splitter.setSizes([panel.PANEL_WIDTH, max(1, splitter.width() - panel.PANEL_WIDTH)])
    else:
        splitter.addWidget(view_container)
        panel.setParent(row)
        panel.setGeometry(0, 0, panel.PANEL_WIDTH, row.height())

    row.show()
    splitter.show()
    panel.open()
    app.processEvents()

    harness = _DownloadsModeHarness()
    harness.content_row = row
    harness.downloads_panel = panel
    harness.downloads_splitter = splitter
    harness._downloads_panel_mode = start_mode
    harness._downloads_mode_transitioning = False
    harness._downloads_panel_width = panel.PANEL_WIDTH
    harness._downloads_splitter_animating = False
    harness._downloads_splitter_animation = None
    harness.views = [page_surface]
    harness.statusBar = lambda: SimpleNamespace(showMessage=lambda *_args: None)

    def finish_split_animation(_start, end, callback):
        available = max(2, splitter.width() - splitter.handleWidth())
        width = max(0, min(int(end), available - 1))
        if splitter.count() == 2:
            splitter.setSizes([width, max(1, available - width)])
        callback()

    def finish_geometry_animation(_start_rect, end_rect, callback):
        panel.setGeometry(end_rect)
        callback()

    harness._animate_downloads_split_width = finish_split_animation
    harness._animate_downloads_panel_geometry = finish_geometry_animation
    return app, harness, page_surface, view_container


def test_failed_download_actions_button_opens_the_context_menu():
    app = QApplication.instance() or QApplication([])
    panel = DownloadsPanel()
    panel.resize(420, 600)
    panel.show()
    app.processEvents()

    download_url = "https://downloads.example.test/file.zip"
    card = panel._make_card({
        "id": "failed-download",
        "file_name": "file.zip",
        "path": "",
        "url": download_url,
        "received_bytes": 0,
        "total_bytes": -1,
        "state": "failed",
        "error": "Network error",
    })
    primary = card.findChild(QPushButton, "downloadsPrimaryButton")

    assert primary is not None
    assert primary.text() == "Actions"
    assert primary.isEnabled()

    def choose_copy_url(menu, *_args):
        return next(action for action in menu.actions() if action.text() == "Copy URL")

    with patch.object(panel, "_exec_item_menu", choose_copy_url):
        primary.click()

    assert QApplication.clipboard().text() == download_url
    panel.close()
    panel.deleteLater()
    app.processEvents()



def test_selecting_download_shows_speed_and_lifecycle_details():
    app = QApplication.instance() or QApplication([])
    panel = DownloadsPanel()
    panel.resize(420, 600)
    panel.show()
    app.processEvents()

    record = {
        "id": "selected-download",
        "file_name": "archive.zip",
        "path": "",
        "url": "https://downloads.example.test/archive.zip",
        "received_bytes": 2 * 1024 * 1024,
        "total_bytes": 4 * 1024 * 1024,
        "state": "downloading",
        "paused": False,
        "requested_at": "2026-10-24T02:00:00+03:30",
        "started_at": "2026-10-24T02:00:01+03:30",
        "finished_at": "",
        "speed_bytes_per_sec": 512 * 1024,
        "speed_samples": [
            {"elapsed_seconds": 0.0, "bytes_per_second": 0.0},
            {"elapsed_seconds": 1.0, "bytes_per_second": 512 * 1024},
        ],
    }
    card = panel._make_card(record)
    name = card.findChild(QPushButton, "downloadFileName")
    assert name is not None
    name.click()

    assert panel.details_title.text() == "archive.zip"
    assert "512.0 KB/s" in panel.details_summary.text()
    assert "Started" in panel.details_times.text()
    assert len(panel.speed_chart._samples) == 2

    panel.close()
    panel.deleteLater()
    app.processEvents()


def test_downloads_glass_softens_only_its_material_not_the_controls():
    app = QApplication.instance() or QApplication([])
    panel = DownloadsPanel()
    panel.resize(380, 620)
    app.processEvents()

    assert panel.manager_button is not None
    assert not panel.manager_button.icon().isNull()
    assert panel.glass_material.graphicsEffect() is None
    assert panel.glass_material.parentWidget() is panel
    assert panel.glass_material.isAncestorOf(panel.search) is False
    assert panel.search.parentWidget() is panel
    assert panel.search.isEnabled()
    assert panel.mode_button.isEnabled()

    panel.close()
    panel.deleteLater()
    app.processEvents()


def test_overlay_dock_switch_preserves_the_existing_page_and_view_container():
    app, browser, page_surface, view_container = _make_mode_harness("overlay")
    panel = browser.downloads_panel
    splitter = browser.downloads_splitter
    page_parent = page_surface.parent()

    browser._toggle_downloads_panel_mode()

    assert browser._downloads_panel_mode == "split"
    assert browser.views == [page_surface]
    assert page_surface.parent() is page_parent is view_container
    assert splitter.count() == 2
    assert splitter.widget(0) is panel
    assert splitter.widget(1) is view_container
    assert panel.is_open
    assert panel.mode_button.property("downloadsPinned") is True
    assert panel.mode_button.toolTip() == "Unpin downloads panel and return to overlay"

    browser._toggle_downloads_panel_mode()

    assert browser._downloads_panel_mode == "overlay"
    assert browser.views == [page_surface]
    assert page_surface.parent() is view_container
    assert splitter.count() == 1
    assert splitter.widget(0) is view_container
    assert panel.parentWidget() is browser.content_row
    assert panel.is_open
    assert panel.mode_button.property("downloadsPinned") is False
    assert panel.mode_button.toolTip() == "Pin downloads panel beside the page"

    browser.content_row.close()
    browser.content_row.deleteLater()
    app.processEvents()
