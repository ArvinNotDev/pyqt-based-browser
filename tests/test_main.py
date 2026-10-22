import os
import socket
import unittest
from unittest.mock import patch

from main import _configure_chromium_proxy, _reserve_proxy_port


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


if __name__ == "__main__":
    unittest.main()
