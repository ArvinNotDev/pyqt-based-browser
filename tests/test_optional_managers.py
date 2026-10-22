"""Tests for manager implementations being integrated from sibling branches.

The files are optional on this branch. Once present, import or dependency errors
are allowed to fail the suite instead of being converted into skips.
"""

import importlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _optional_module(module_name: str, source_path: Path):
    if not source_path.is_file():
        pytest.skip(f"{source_path.name} has not been integrated on this branch")
    return importlib.import_module(module_name)


def test_bookmark_add_deduplicate_remove_and_profile_isolation(tmp_path, monkeypatch):
    module = _optional_module(
        "managers.bookmarks_manager", ROOT / "managers" / "bookmarks_manager.py"
    )
    monkeypatch.chdir(tmp_path)
    personal = module.BookmarksManager("Personal")
    work = module.BookmarksManager("Work")

    first = personal.add_bookmark("Example", "https://example.test")
    duplicate = personal.add_bookmark("Another title", "https://example.test:443/")
    work.add_bookmark("Work", "https://work.example.test/")

    assert duplicate["id"] == first["id"]
    assert personal.is_bookmarked("https://example.test/")
    assert [item["title"] for item in personal.list_bookmarks()] == ["Example"]
    assert [item["title"] for item in module.BookmarksManager("Work").list_bookmarks()] == [
        "Work"
    ]
    assert personal.remove_bookmark(first["id"]) is True
    assert personal.remove_bookmark(first["id"]) is False
    assert personal.list_bookmarks() == []


def test_bookmark_invalid_url_is_rejected(tmp_path, monkeypatch):
    module = _optional_module(
        "managers.bookmarks_manager", ROOT / "managers" / "bookmarks_manager.py"
    )
    monkeypatch.chdir(tmp_path)
    manager = module.BookmarksManager("Guest")

    with pytest.raises(ValueError):
        manager.add_bookmark("Script", "javascript:alert(1)")


def test_bookmark_corrupt_file_is_preserved_before_replacement(tmp_path, monkeypatch):
    module = _optional_module(
        "managers.bookmarks_manager", ROOT / "managers" / "bookmarks_manager.py"
    )
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "profile_data" / "Guest" / "bookmarks.json"
    path.parent.mkdir(parents=True)
    path.write_text("{broken", encoding="utf-8")
    manager = module.BookmarksManager("Guest")

    assert manager.list_bookmarks() == []
    manager.add_bookmark("Example", "https://example.test/")

    backups = list(path.parent.glob("bookmarks.json.corrupt-*.bak"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == "{broken"


class FakeSignal:
    def __init__(self):
        self.slots = []

    def connect(self, slot):
        self.slots.append(slot)


def _fake_download_request(name="report.txt", url="https://download.example/report.txt"):
    return SimpleNamespace(
        url=lambda: url,
        suggestedFileName=lambda: name,
        receivedBytes=lambda: 0,
        totalBytes=lambda: 10,
        state=lambda: "DownloadRequested",
        receivedBytesChanged=FakeSignal(),
        totalBytesChanged=FakeSignal(),
        stateChanged=FakeSignal(),
        setDownloadDirectory=Mock(),
        setDownloadFileName=Mock(),
        accept=Mock(),
        cancel=Mock(),
    )


def test_download_manager_tracks_state_and_clears_finished_records(tmp_path):
    module = _optional_module(
        "managers.download_manager", ROOT / "managers" / "download_manager.py"
    )
    manager = module.DownloadManager("Guest", tmp_path / "downloads")
    request = _fake_download_request()

    manager._on_download_requested(request)
    record = manager.get_downloads()[0]
    assert record["state"] == "requested"
    assert record["file_name"] == "report.txt"
    assert Path(record["path"]).parent == (tmp_path / "downloads").resolve()
    request.accept.assert_called_once_with()
    request.setDownloadDirectory.assert_called_once_with(manager.download_dir)

    request.state = lambda: "DownloadInProgress"
    request.receivedBytes = lambda: 5
    manager._refresh(record["id"])
    assert manager.get_downloads()[0]["state"] == "downloading"
    assert manager.get_downloads()[0]["received_bytes"] == 5

    request.state = lambda: "DownloadCompleted"
    manager._refresh(record["id"])
    assert manager.get_downloads()[0]["state"] == "completed"
    manager.clear_finished()
    assert manager.get_downloads() == []


def test_download_manager_sanitizes_names_and_avoids_collisions(tmp_path):
    module = _optional_module(
        "managers.download_manager", ROOT / "managers" / "download_manager.py"
    )
    manager = module.DownloadManager("Guest", tmp_path / "downloads")
    first = _fake_download_request("..\\..\\report.txt")
    second = _fake_download_request("report.txt")

    manager._on_download_requested(first)
    manager._on_download_requested(second)

    records = manager.get_downloads()
    assert records[0]["file_name"] == "report.txt"
    assert records[1]["file_name"] == "report (1).txt"
    assert all(Path(record["path"]).parent == (tmp_path / "downloads").resolve() for record in records)


def test_download_manager_cancel_and_failed_destination_are_safe(tmp_path):
    module = _optional_module(
        "managers.download_manager", ROOT / "managers" / "download_manager.py"
    )
    manager = module.DownloadManager("Guest", tmp_path / "downloads")
    request = _fake_download_request()
    manager._on_download_requested(request)
    download_id = manager.get_downloads()[0]["id"]

    assert manager.cancel(download_id) is True
    request.cancel.assert_called_once_with()
    assert manager.get_downloads()[0]["state"] == "cancelled"
    assert manager.cancel(download_id) is False

    invalid_root = tmp_path / "not-a-directory"
    invalid_root.write_text("file", encoding="utf-8")
    failing_manager = module.DownloadManager("Guest", invalid_root)
    failing_request = _fake_download_request()
    failing_manager._on_download_requested(failing_request)

    failing_request.cancel.assert_called_once_with()
    assert failing_manager.get_downloads()[0]["state"] == "failed"
