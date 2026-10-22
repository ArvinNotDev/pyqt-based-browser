import os
import socket
import tempfile
import unittest
from unittest.mock import patch

from main import _configure_chromium_proxy, _load_startup_settings, _reserve_proxy_port
from managers.profile_manager import Profile
from ui.settings import Settings


class StartupConfigurationTests(unittest.TestCase):
    def test_proxy_port_is_available_on_loopback(self):
        port = _reserve_proxy_port()
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(("127.0.0.1", port))

    def test_chromium_flags_preserve_safe_options_and_enforce_sandbox(self):
        initial_flags = (
            "--disable-gpu --no-sandbox --disable-software-rasterizer "
            "--proxy-server old-proxy:1234 --enable-features=TestFeature"
        )
        with patch.dict(
            os.environ,
            {
                "QTWEBENGINE_CHROMIUM_FLAGS": initial_flags,
                "QTWEBENGINE_DISABLE_SANDBOX": "1",
            },
        ):
            _configure_chromium_proxy(43210)
            flags = os.environ["QTWEBENGINE_CHROMIUM_FLAGS"].split()
            self.assertIn("--disable-gpu", flags)
            self.assertIn("--enable-features=TestFeature", flags)
            self.assertIn("--proxy-server=http://127.0.0.1:43210", flags)
            self.assertNotIn("--no-sandbox", flags)
            self.assertNotIn("--disable-software-rasterizer", flags)
            self.assertNotIn("old-proxy:1234", flags)
            self.assertNotIn("QTWEBENGINE_DISABLE_SANDBOX", os.environ)

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


if __name__ == "__main__":
    unittest.main()
