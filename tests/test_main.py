import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from main import (
    _consume_session,
    _load_startup_settings,
    _normalize_application_font,
    _runtime_arguments,
    _wait_for_parent_exit,
)
from managers.profile_manager import Profile
from ui.settings import Settings


class StartupConfigurationTests(unittest.TestCase):
    def test_startup_settings_do_not_add_or_replace_chromium_proxy(self):
        original_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                os.chdir(temp_dir)
                with patch.object(Profile, "get_machine_id", return_value="test-machine"):
                    with patch.dict(
                        os.environ,
                        {"QTWEBENGINE_CHROMIUM_FLAGS": "--enable-features=TestFeature"},
                    ):
                        _load_startup_settings()
                        flags = os.environ["QTWEBENGINE_CHROMIUM_FLAGS"].split()
                        # Startup also appends Chromium's focused WebGPU opt-out
                        # because the persisted profile default is conservative;
                        # caller-provided switches must remain untouched.
                        self.assertIn("--enable-features=TestFeature", flags)
                        self.assertIn("--disable-features=WebGPU", flags)
                        self.assertEqual(flags.count("--enable-features=TestFeature"), 1)
            finally:
                os.chdir(original_cwd)

    def test_network_mode_handoff_arguments_are_removed_before_qt(self):
        qt_args, tor_mode, session_path, parent_pid = _runtime_arguments([
            "--enable-features=TestFeature",
            "--tor-mode",
            "--resume-session=C:/Temp/arma-network-switch-test.json",
            "--wait-for-parent=1234",
        ])
        self.assertEqual(qt_args, ["--enable-features=TestFeature"])
        self.assertTrue(tor_mode)
        self.assertEqual(session_path, "C:/Temp/arma-network-switch-test.json")
        self.assertEqual(parent_pid, 1234)

    def test_session_handoff_is_consumed_only_from_its_owned_temp_path(self):
        descriptor, safe_path = tempfile.mkstemp(
            prefix="arma-network-switch-", suffix=".json"
        )
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write('{"tabs": ["https://example.test/"]}')
        self.assertEqual(_consume_session(safe_path), {"tabs": ["https://example.test/"]})
        self.assertFalse(os.path.exists(safe_path))

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as stream:
            unrelated_path = stream.name
            stream.write(b'{"leave":"untouched"}')
        self.assertIsNone(_consume_session(unrelated_path))
        self.assertTrue(os.path.exists(unrelated_path))
        os.remove(unrelated_path)

    def test_invalid_parent_pid_is_rejected_for_handoff_wait(self):
        self.assertFalse(_wait_for_parent_exit(0))

    def test_startup_applies_selected_profile_hardware_setting_before_qt(self):
        original_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                os.chdir(temp_dir)
                with patch.object(Profile, "get_machine_id", return_value="test-machine"):
                    settings = Settings()
                    settings.hardware_acceleration = False
                    settings.save("Research")
                    Settings.save_profiles(["Research"])

                    with patch.dict(
                        os.environ,
                        {"QTWEBENGINE_CHROMIUM_FLAGS": "--enable-features=TestFeature"},
                    ):
                        loaded = _load_startup_settings()

                        self.assertFalse(loaded.hardware_acceleration)
                        flags = os.environ["QTWEBENGINE_CHROMIUM_FLAGS"].split()
                        self.assertIn("--disable-gpu", flags)
                        self.assertIn("--enable-features=TestFeature", flags)
                        self.assertEqual(os.environ["QT_OPENGL"], "software")
            finally:
                os.chdir(original_cwd)

    def test_bookmark_dialog_routes_opened_url_to_browser_navigation(self):
        from ui import browser_window

        class FakeSignal:
            def connect(self, slot):
                self.slot = slot

            def emit(self, value):
                self.slot(value)

        class FakeDialog:
            def __init__(self, manager, parent):
                self.manager = manager
                self.parent = parent
                self.url_activated = FakeSignal()
                self.executed = False

            def exec(self):
                self.executed = True

        manager = object()
        navigation = []
        refreshes = []
        browser = SimpleNamespace(
            bookmarks_manager=manager,
            navigate=navigation.append,
            _refresh_bookmarks=lambda: refreshes.append(True),
        )
        dialogs = []

        def create_dialog(*args):
            dialog = FakeDialog(*args)
            dialogs.append(dialog)
            return dialog

        with patch.object(browser_window, "BookmarksDialog", create_dialog):
            browser_window.BrowserWindow.show_bookmarks(browser)

        dialogs[0].url_activated.emit("https://saved.example/")
        self.assertTrue(dialogs[0].executed)
        self.assertEqual(navigation, ["https://saved.example/"])
        self.assertEqual(refreshes, [True])


    def test_application_font_normalizer_preserves_valid_point_size(self):
        from PySide6.QtGui import QFont

        class FakeApplication:
            def __init__(self):
                self.current_font = QFont("Segoe UI", 11)

            def font(self):
                return self.current_font

            def setFont(self, font):
                self.current_font = font

        app = FakeApplication()
        normalized = _normalize_application_font(app)

        self.assertEqual(normalized.pointSize(), 11)
        self.assertEqual(app.font().pointSize(), 11)


    def test_application_font_normalizer_repairs_unspecified_point_size(self):
        from PySide6.QtGui import QFont

        class FakeApplication:
            def __init__(self):
                self.current_font = QFont()
                self.current_font.setPixelSize(13)

            def font(self):
                return self.current_font

            def setFont(self, font):
                self.current_font = font

        app = FakeApplication()
        self.assertLessEqual(app.font().pointSize(), 0)

        normalized = _normalize_application_font(app)

        self.assertEqual(normalized.pointSize(), 10)
        self.assertEqual(app.font().pointSize(), 10)


if __name__ == "__main__":
    unittest.main()
