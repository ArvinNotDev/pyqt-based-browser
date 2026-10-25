import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from managers.bookmarks_manager import BookmarksManager
from managers.dashboard_manager import DashboardManager
from managers.download_manager import DownloadManager
from managers.history_manager import History
from managers.storage import validate_profile_name
from ui.settings import Settings


class FakeSignal:
    def __init__(self):
        self._slots = []

    def connect(self, slot):
        self._slots.append(slot)

    def disconnect(self, slot):
        self._slots.remove(slot)

    def emit(self, *args):
        for slot in list(self._slots):
            slot(*args)


class FakeProfile:
    def __init__(self, download_path=None):
        self.downloadRequested = FakeSignal()
        self.download_path = download_path

    def downloadPath(self):
        return self.download_path or ""


class FakeDownloadRequest:
    def __init__(self, url="https://example.test/file.txt", name="file.txt", total=100):
        self._url = url
        self._name = name
        self._total = total
        self._received = 0
        self._state = "DownloadRequested"
        self.downloadDirectory = None
        self.downloadFileName = None
        self.receivedBytesChanged = FakeSignal()
        self.totalBytesChanged = FakeSignal()
        self.stateChanged = FakeSignal()
        self.accepted = False
        self.cancelled = False
        self.fail_accept = False

    def url(self):
        return self._url

    def suggestedFileName(self):
        return self._name

    def downloadFileName(self):
        return self._name

    def receivedBytes(self):
        return self._received

    def totalBytes(self):
        return self._total

    def state(self):
        return self._state

    def setDownloadDirectory(self, value):
        self.downloadDirectory = value

    def setDownloadFileName(self, value):
        self.downloadFileName = value

    def accept(self):
        if self.fail_accept:
            raise RuntimeError("accept rejected")
        self.accepted = True
        self._state = "DownloadInProgress"
        self.stateChanged.emit(self._state)

    def cancel(self):
        self.cancelled = True
        self._state = "DownloadCancelled"
        self.stateChanged.emit(self._state)

    def interruptReasonString(self):
        return "Network error"

    def progress(self, received, total=None):
        self._received = received
        if total is not None:
            self._total = total
            self.totalBytesChanged.emit()
        self.receivedBytesChanged.emit()

    def finish(self):
        self._state = "DownloadCompleted"
        self.stateChanged.emit(self._state)


class DataManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_cwd = os.getcwd()
        os.chdir(self.temp_dir.name)

    def tearDown(self):
        os.chdir(self.old_cwd)
        self.temp_dir.cleanup()

    def test_profile_name_validation_and_path_isolation(self):
        self.assertEqual(validate_profile_name("Mina 2026 (work)"), "Mina 2026 (work)")
        for name in ("", "..", "../escape", "a/b", r"a\b", "NUL", "name."):
            with self.subTest(name=name), self.assertRaises(ValueError):
                validate_profile_name(name)
        with self.assertRaises(ValueError):
            History("../outside", base_dir="profile_data")

    def test_dashboard_widget_order_is_validated_and_persisted(self):
        base_dir = Path(self.temp_dir.name) / "profile_data"
        manager = DashboardManager("Guest", base_dir=base_dir)
        manager.update({"widget_order": ["notes", "bookmarks", "recent"]})
        expected = ["notes", "bookmarks", "recent", "closed", "focus"]
        self.assertEqual(manager.export()["widget_order"], expected)

        loaded = DashboardManager("Guest", base_dir=base_dir)
        self.assertEqual(loaded.export()["widget_order"], expected)
        with self.assertRaises(ValueError):
            manager.update({"widget_order": ["recent", "recent"]})
        with self.assertRaises(ValueError):
            manager.update({"widget_order": ["unknown-widget"]})

    def test_settings_defaults_round_trip_and_partial_values(self):
        path = str(Path(self.temp_dir.name) / "settings.json")
        settings = Settings(file_path=path)
        self.assertEqual(settings.homepage, "arma://dashboard/")
        self.assertTrue(settings.save_history)
        settings.homepage = "https://example.test"
        settings.private_mode = True
        settings.window_width = 1440
        settings.save("Guest")

        loaded = Settings(file_path=path)
        loaded.load("Guest")
        self.assertEqual(loaded.homepage, "https://example.test")
        self.assertTrue(loaded.private_mode)
        self.assertEqual(loaded.window_width, 1440)
        self.assertTrue(loaded.save_cookies)

        with open(path, "w", encoding="utf-8") as stream:
            json.dump({"Guest": {"save_history": "false", "window_height": -1}}, stream)
        partial = Settings(file_path=path)
        partial.load("Guest")
        self.assertTrue(partial.save_history)
        self.assertEqual(partial.window_height, 720)
        partial.homepage = "https://previous-profile.test"
        partial.load("Missing")
        self.assertEqual(partial.homepage, "arma://dashboard/")

    def test_settings_migrates_legacy_profile_list_without_deleting_it(self):
        path = str(Path(self.temp_dir.name) / "settings.json")
        legacy_key = "a" * 64
        with open(path, "w", encoding="utf-8") as stream:
            json.dump({"Guest": {"homepage": "https://old.test"}, legacy_key: {"profiles": ["Guest", "Work"]}}, stream)
        settings = Settings(file_path=path)
        settings.load_profile_settings()
        self.assertEqual(settings.profiles_list, ["Guest", "Work"])
        with open(path, "r", encoding="utf-8") as stream:
            persisted = json.load(stream)
        self.assertIn(legacy_key, persisted)
        self.assertIn("__pyqt_browser_meta_v1__", persisted)
        self.assertEqual(persisted[legacy_key]["profiles"], ["Guest", "Work"])

    def test_corrupt_settings_are_backed_up_before_save(self):
        path = Path(self.temp_dir.name) / "settings.json"
        original = "{not valid json"
        path.write_text(original, encoding="utf-8")
        settings = Settings(file_path=str(path))
        settings.load("Guest")
        self.assertEqual(settings.homepage, "arma://dashboard/")
        settings.save("Guest")
        backups = list(path.parent.glob("settings.json.corrupt-*.bak"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(encoding="utf-8"), original)

    def test_history_legacy_formats_delete_filters_and_disabled_recording(self):
        profile_data = Path(self.temp_dir.name) / "profile_data" / "Guest"
        profile_data.mkdir(parents=True)
        (profile_data / "history.json").write_text(json.dumps({
            "https://one.test": {"date": "2026/10/01", "time": "10:00"},
            "https://two.test": [
                {"date": "2026/10/01", "time": "11:00"},
                {"date": "2026/10/02", "time": "11:00"},
            ],
        }), encoding="utf-8")
        history = History("Guest", base_dir=str(Path(self.temp_dir.name) / "profile_data"))
        self.assertEqual(len(history.history["https://one.test"]), 1)
        history.delete(date="2026/10/01", time="11:00")
        self.assertEqual(len(history.history["https://two.test"]), 1)
        self.assertEqual(history.history["https://two.test"][0]["date"], "2026/10/02")
        history.save()
        reloaded = History("Guest", base_dir=str(Path(self.temp_dir.name) / "profile_data"))
        self.assertEqual(reloaded.history, history.history)

        disabled = History("NoRecord", enabled=False, base_dir=str(Path(self.temp_dir.name) / "profile_data"))
        self.assertFalse(disabled.add("https://example.test"))
        self.assertFalse(Path(disabled.file_path).exists())

    def test_corrupt_history_is_preserved_on_next_write(self):
        profile_data = Path(self.temp_dir.name) / "profile_data" / "Guest"
        profile_data.mkdir(parents=True)
        target = profile_data / "history.json"
        target.write_text("[broken", encoding="utf-8")
        history = History("Guest", base_dir=str(Path(self.temp_dir.name) / "profile_data"))
        self.assertEqual(history.history, {})
        history.add("https://example.test")
        self.assertTrue(list(profile_data.glob("history.json.corrupt-*.bak")))

    def test_history_legacy_row_list_loads(self):
        profile_data = Path(self.temp_dir.name) / "profile_data" / "Guest"
        profile_data.mkdir(parents=True)
        (profile_data / "history.json").write_text(json.dumps([
            {"url": "https://one.test", "date": "2025/01/02", "time": "09:30"},
            {"link": "https://one.test", "date": "2025/01/03", "time": "10:30"},
        ]), encoding="utf-8")
        history = History("Guest", base_dir=str(Path(self.temp_dir.name) / "profile_data"))
        self.assertEqual(len(history.history["https://one.test"]), 2)

    def test_bookmarks_create_lookup_delete_persistence_and_validation(self):
        manager = BookmarksManager("Guest")
        first = manager.add_bookmark("Example", "https://example.test")
        duplicate = manager.add_bookmark("Changed title", "HTTPS://EXAMPLE.TEST:443/")
        self.assertEqual(first["id"], duplicate["id"])
        self.assertEqual({"id", "title", "url", "created_at"} - first.keys(), set())
        self.assertTrue(manager.is_bookmarked("https://example.test/"))
        self.assertEqual(len(BookmarksManager("Guest").list_bookmarks()), 1)
        self.assertEqual(BookmarksManager("Other").list_bookmarks(), [])
        self.assertTrue(manager.remove_bookmark(first["id"]))
        self.assertFalse(manager.remove_bookmark(first["id"]))
        self.assertFalse(manager.is_bookmarked("javascript:alert(1)"))
        for url in ("javascript:alert(1)", "file:///secret", "https://user:pass@example.test"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                manager.add_bookmark("Bad", url)

    def test_bookmarks_accept_only_supported_internal_arma_pages(self):
        manager = BookmarksManager("Guest")
        for host in ("dashboard", "bookmarks", "history", "downloads", "settings"):
            with self.subTest(host=host):
                record = manager.add_bookmark(host.title(), f"arma://{host}/")
                self.assertEqual(record["url"], f"arma://{host}/")
                self.assertTrue(manager.is_bookmarked(f"arma://{host}"))

        for url in (
            "arma://unknown/",
            "arma://dashboard/private?secret=1",
            "arma://dashboard:443/",
            "arma://user@dashboard/",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                manager.add_bookmark("Unsafe internal", url)

    def test_bookmarks_preserve_legacy_valid_records(self):
        profile_dir = Path(self.temp_dir.name) / "profile_data" / "Guest"
        profile_dir.mkdir(parents=True)
        target = profile_dir / "bookmarks.json"
        legacy = [{"id": "stable-id", "title": "Old", "url": "https://old.test", "created_at": "2024-01-01T00:00:00+00:00"}]
        target.write_text(json.dumps(legacy), encoding="utf-8")
        manager = BookmarksManager("Guest")
        manager.add_bookmark("New", "https://new.test")
        self.assertEqual({item["id"] for item in manager.list_bookmarks()}, {"stable-id", manager.list_bookmarks()[1]["id"]})
        self.assertIsInstance(json.loads(target.read_text(encoding="utf-8")), list)

    def test_bookmark_records_are_detached_snapshots(self):
        profile_dir = Path(self.temp_dir.name) / "profile_data" / "Guest"
        profile_dir.mkdir(parents=True)
        (profile_dir / "bookmarks.json").write_text(json.dumps([{
            "id": "stable-id",
            "title": "Old",
            "url": "https://old.test",
            "created_at": "2024-01-01T00:00:00+00:00",
            "metadata": {"source": {"name": "legacy"}},
        }]), encoding="utf-8")
        manager = BookmarksManager("Guest")

        result = manager.list_bookmarks()
        result[0]["metadata"]["source"]["name"] = "changed"
        self.assertEqual(
            manager.list_bookmarks()[0]["metadata"]["source"]["name"],
            "legacy",
        )
        duplicate = manager.add_bookmark("Duplicate", "https://old.test/")
        duplicate["metadata"]["source"]["name"] = "also changed"
        self.assertEqual(
            manager.list_bookmarks()[0]["metadata"]["source"]["name"],
            "legacy",
        )

    def test_download_manager_tracks_safe_paths_progress_cancel_and_clear(self):
        manager = DownloadManager("Guest", str(Path(self.temp_dir.name) / "downloads"))
        profile = FakeProfile()
        manager.attach_profile(profile)
        request = FakeDownloadRequest(name=r"..\unsafe:name?.txt")
        profile.downloadRequested.emit(request)
        self.assertTrue(request.accepted)
        record = manager.get_downloads()[0]
        self.assertEqual(record["state"], "downloading")
        self.assertEqual(record["file_name"], "unsafe_name_.txt")
        self.assertEqual(os.path.dirname(record["path"]), os.path.realpath(manager.download_dir))
        request.progress(42)
        self.assertEqual(manager.get_downloads()[0]["received_bytes"], 42)

        second = FakeDownloadRequest(name=r"..\unsafe:name?.txt")
        profile.downloadRequested.emit(second)
        self.assertNotEqual(manager.get_downloads()[0]["path"], manager.get_downloads()[1]["path"])
        self.assertTrue(manager.cancel(manager.get_downloads()[0]["id"]))
        self.assertEqual(manager.get_downloads()[0]["state"], "cancelled")
        second.finish()
        self.assertEqual(manager.get_downloads()[1]["state"], "completed")
        manager.clear_finished()
        self.assertEqual(manager.get_downloads(), [])

    def test_download_open_file_only_opens_completed_items(self):
        directory = Path(self.temp_dir.name) / "downloads"
        manager = DownloadManager("Guest", str(directory))
        profile = FakeProfile()
        manager.attach_profile(profile)
        request = FakeDownloadRequest()
        profile.downloadRequested.emit(request)
        record = manager.get_downloads()[0]
        self.assertFalse(manager.open_file(record["id"]))
        Path(record["path"]).write_bytes(b"content")
        request.finish()
        with patch("managers.download_manager.QDesktopServices.openUrl", return_value=True) as open_url:
            self.assertTrue(manager.open_file(record["id"]))
            open_url.assert_called_once()

    def test_download_accept_failure_keeps_one_failed_record(self):
        manager = DownloadManager("Guest", str(Path(self.temp_dir.name) / "downloads"))
        profile = FakeProfile()
        manager.attach_profile(profile)
        request = FakeDownloadRequest()
        request.fail_accept = True
        profile.downloadRequested.emit(request)
        records = manager.get_downloads()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["state"], "failed")
        self.assertIn("accept rejected", records[0]["error"])

    def test_download_manager_shutdown_cancels_and_detaches_callbacks(self):
        manager = DownloadManager("Guest", str(Path(self.temp_dir.name) / "downloads"))
        profile = FakeProfile()
        manager.attach_profile(profile)
        request = FakeDownloadRequest()
        profile.downloadRequested.emit(request)
        download_id = manager.get_downloads()[0]["id"]

        manager.shutdown()

        self.assertTrue(request.cancelled)
        self.assertEqual(manager.get_downloads()[0]["state"], "cancelled")
        self.assertEqual(profile.downloadRequested._slots, [])
        self.assertEqual(request.receivedBytesChanged._slots, [])
        self.assertEqual(request.totalBytesChanged._slots, [])
        self.assertEqual(request.stateChanged._slots, [])
        request.progress(50)
        self.assertFalse(manager.cancel(download_id))

        late_request = FakeDownloadRequest(name="late.txt")
        profile.downloadRequested.emit(late_request)
        self.assertFalse(late_request.accepted)
        self.assertEqual(len(manager.get_downloads()), 1)

    def test_download_contract_emits_state_changes_and_returns_snapshots(self):
        manager = DownloadManager("Guest", str(Path(self.temp_dir.name) / "downloads"))
        observed_states = []
        manager.downloads_changed.connect(
            lambda: observed_states.append([item["state"] for item in manager.get_downloads()])
        )
        profile = FakeProfile()
        manager.attach_profile(profile)
        request = FakeDownloadRequest()
        profile.downloadRequested.emit(request)

        record = manager.get_downloads()[0]
        self.assertEqual(
            set(record),
            {
                "id", "file_name", "path", "url", "received_bytes",
                "total_bytes", "state", "paused", "error", "requested_at",
                "started_at", "finished_at", "speed_bytes_per_sec", "speed_samples",
            },
        )
        self.assertFalse(record["paused"])
        self.assertTrue(record["requested_at"])
        self.assertTrue(record["started_at"])
        self.assertEqual(record["finished_at"], "")
        self.assertIsInstance(record["speed_samples"], list)
        self.assertIn(["requested"], observed_states)
        self.assertIn(["downloading"], observed_states)

        exposed = manager.get_downloads()
        original_id = exposed[0]["id"]
        exposed[0]["state"] = "failed"
        exposed[0]["id"] = "external-mutation"
        self.assertEqual(manager.get_downloads()[0]["state"], "downloading")
        self.assertEqual(manager.get_downloads()[0]["id"], original_id)

        request.finish()
        self.assertIn(["completed"], observed_states)
        completed = manager.get_downloads()[0]
        self.assertEqual(completed["state"], "completed")
        self.assertTrue(completed["finished_at"])
        self.assertFalse(manager.cancel(original_id))

    def test_download_paths_are_reserved_across_profile_managers(self):
        directory = str(Path(self.temp_dir.name) / "shared-downloads")
        first = DownloadManager("Guest", directory)
        second = DownloadManager("Work", directory)
        first_profile = FakeProfile()
        second_profile = FakeProfile()
        first.attach_profile(first_profile)
        second.attach_profile(second_profile)

        first_profile.downloadRequested.emit(FakeDownloadRequest(name="same.txt"))
        second_profile.downloadRequested.emit(FakeDownloadRequest(name="same.txt"))

        first_record = first.get_downloads()[0]
        second_record = second.get_downloads()[0]
        self.assertNotEqual(first_record["path"], second_record["path"])
        self.assertEqual(first_record["file_name"], "same.txt")
        self.assertEqual(second_record["file_name"], "same (1).txt")
        self.assertEqual(len(first.get_downloads()), 1)
        self.assertEqual(len(second.get_downloads()), 1)

    def test_download_manager_tracks_profile_folder_updates(self):
        old_directory = Path(self.temp_dir.name) / "old-downloads"
        new_directory = Path(self.temp_dir.name) / "new-downloads"
        manager = DownloadManager("Guest", str(old_directory))
        profile = FakeProfile(str(old_directory))
        manager.attach_profile(profile)

        profile.download_path = str(new_directory)
        manager.attach_profile(profile)
        request = FakeDownloadRequest(name="after-change.txt")
        profile.downloadRequested.emit(request)

        self.assertTrue(os.path.samefile(manager.download_dir, new_directory))
        self.assertTrue(
            os.path.samefile(
                os.path.dirname(manager.get_downloads()[0]["path"]),
                new_directory,
            )
        )

        explicit_directory = Path(self.temp_dir.name) / "explicit-downloads"
        separate = DownloadManager("Other", str(explicit_directory))
        separate.attach_profile(FakeProfile(str(old_directory)))
        self.assertEqual(separate.download_dir, os.path.abspath(explicit_directory))

        separate.set_download_directory(new_directory)
        request = FakeDownloadRequest(name="new-destination.txt")
        separate._on_download_requested(request)
        self.assertTrue(
            os.path.samefile(
                os.path.dirname(separate.get_downloads()[0]["path"]),
                new_directory,
            )
        )


if __name__ == "__main__":
    unittest.main()
