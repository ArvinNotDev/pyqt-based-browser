from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QMenu, QPushButton

from ui.downloads_panel import DownloadsPanel


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

    with patch.object(QMenu, "exec", choose_copy_url):
        primary.click()

    assert QApplication.clipboard().text() == download_url
    panel.close()
    panel.deleteLater()
    app.processEvents()
