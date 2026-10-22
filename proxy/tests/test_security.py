import io
import json
import os
import queue
import socket as socket_lib
import tarfile
import tempfile
import threading
import unittest
from email.message import Message
from types import SimpleNamespace
from unittest import mock

import socks

from proxy import proxy as proxy_module
from proxy import updater, utils
from proxy.config import Config


class ProxyPolicyTests(unittest.TestCase):
    def setUp(self):
        with proxy_module._state_lock:
            proxy_module.blocked_hosts[:] = []
            proxy_module.exclude_hosts[:] = []
        proxy_module.set_tor_routing(False)

    def tearDown(self):
        proxy_module.set_tor_routing(False)
        with proxy_module._state_lock:
            proxy_module.blocked_hosts[:] = []
            proxy_module.exclude_hosts[:] = []

    def test_domain_rules_respect_label_boundaries(self):
        proxy_module.blocked_hosts[:] = ["example.com"]
        with self.assertRaises(proxy_module.BlockedHost):
            proxy_module.route_uses_tor("sub.example.com")
        self.assertFalse(proxy_module.route_uses_tor("notexample.com"))

    def test_blocked_host_wins_over_exclusion(self):
        proxy_module.blocked_hosts[:] = ["example.com"]
        proxy_module.exclude_hosts[:] = ["example.com"]
        proxy_module.set_tor_routing(True)
        with self.assertRaises(proxy_module.BlockedHost):
            proxy_module.route_uses_tor("example.com")

    def test_exclusion_is_direct_only_while_tor_routing_is_enabled(self):
        proxy_module.exclude_hosts[:] = ["*.example.com"]
        self.assertFalse(proxy_module.route_uses_tor("www.example.com"))
        proxy_module.set_tor_routing(True)
        self.assertFalse(proxy_module.route_uses_tor("www.example.com"))
        self.assertTrue(proxy_module.route_uses_tor("example.net"))

    def test_authority_parser_accepts_ipv4_and_bracketed_ipv6(self):
        self.assertEqual(proxy_module._parse_authority("192.0.2.5:443", require_port=True), ("192.0.2.5", 443))
        self.assertEqual(proxy_module._parse_authority("[2001:db8::1]:443", require_port=True), ("2001:db8::1", 443))

    def test_authority_parser_rejects_malformed_hosts_and_ports(self):
        for target in ("", "example.com", "example.com:0", "example.com:65536", "example.com:nope",
                       "2001:db8::1:443", "user@example.com:443", "example.com:443/path"):
            with self.subTest(target=target), self.assertRaises(proxy_module.InvalidHost):
                proxy_module._parse_authority(target, require_port=True)

    def test_numeric_ipv4_aliases_cannot_bypass_host_rules(self):
        for host in ("127.1", "2130706433", "0177.0.0.1"):
            with self.subTest(host=host), self.assertRaises(proxy_module.InvalidHost):
                proxy_module.normalize_host(host)
        self.assertEqual(proxy_module.normalize_host("[::ffff:127.0.0.1]"), "127.0.0.1")

    def test_duplicate_host_headers_are_rejected(self):
        handler = object.__new__(proxy_module.ProxyHandler)
        handler.path = "/"
        handler.headers = Message()
        handler.headers.add_header("Host", "example.com")
        handler.headers.add_header("Host", "127.0.0.1")
        with self.assertRaises(proxy_module.InvalidHost):
            handler._request_target()

    def test_tor_failure_does_not_retry_directly(self):
        remote = mock.Mock()
        remote.connect.side_effect = OSError("SOCKS endpoint unavailable")
        handler = object.__new__(proxy_module.ProxyHandler)
        handler.server = SimpleNamespace(tor_socks_port=9050)
        with mock.patch.object(proxy_module.socks, "socksocket", return_value=remote), \
             mock.patch.object(proxy_module.socket, "create_connection") as direct_connect:
            with self.assertRaises(OSError):
                handler._connect_upstream("example.com", 443, use_tor=True)
        remote.set_proxy.assert_called_once_with(socks.SOCKS5, "127.0.0.1", 9050, rdns=True)
        direct_connect.assert_not_called()

    def test_server_rejects_non_loopback_binding(self):
        with self.assertRaises(ValueError):
            proxy_module.ThreadedHTTPServer(("0.0.0.0", 0), proxy_module.ProxyHandler, 9050)

    def test_port_availability_rejects_invalid_ports_before_resolution(self):
        invalid_ports = (0, -1, 65536, 1.5, "80", None, True, False)
        with mock.patch.object(proxy_module.socket, "getaddrinfo") as resolve, \
             mock.patch.object(proxy_module.socket, "socket") as socket_factory:
            for port in invalid_ports:
                with self.subTest(port=port):
                    self.assertFalse(proxy_module.is_port_free("127.0.0.1", port))
            resolve.assert_not_called()
            socket_factory.assert_not_called()

    def test_port_availability_checks_valid_boundary_ports(self):
        address = (socket_lib.AF_INET, socket_lib.SOCK_STREAM, socket_lib.IPPROTO_TCP,
                   "", ("127.0.0.1", 1))
        for port in (1, 65535):
            with self.subTest(port=port), \
                 mock.patch.object(proxy_module.socket, "getaddrinfo", return_value=[address]) as resolve, \
                 mock.patch.object(proxy_module.socket, "socket") as socket_factory:
                socket_factory.return_value.__enter__.return_value.bind.return_value = None
                self.assertTrue(proxy_module.is_port_free("127.0.0.1", port))
                resolve.assert_called_once_with(
                    "127.0.0.1", port, socket_lib.AF_UNSPEC, socket_lib.SOCK_STREAM
                )
                socket_factory.assert_called_once_with(
                    socket_lib.AF_INET, socket_lib.SOCK_STREAM, socket_lib.IPPROTO_TCP
                )

    def test_port_availability_rejects_invalid_hosts_and_socket_errors(self):
        invalid_hosts = (None, b"127.0.0.1", "", "  ", "bad host", "127.0.0.1\x00")
        with mock.patch.object(proxy_module.socket, "getaddrinfo") as resolve, \
             mock.patch.object(proxy_module.socket, "socket") as socket_factory:
            for host in invalid_hosts:
                with self.subTest(host=host):
                    self.assertFalse(proxy_module.is_port_free(host, 8080))
            resolve.assert_not_called()
            socket_factory.assert_not_called()

        with mock.patch.object(proxy_module.socket, "getaddrinfo", side_effect=OSError):
            self.assertFalse(proxy_module.is_port_free("127.0.0.1", 8080))
        with mock.patch.object(proxy_module.socket, "getaddrinfo", return_value=[
            (socket_lib.AF_INET, socket_lib.SOCK_STREAM, socket_lib.IPPROTO_TCP,
             "", ("127.0.0.1", 8080))
        ]), mock.patch.object(proxy_module.socket, "socket", side_effect=OSError):
            self.assertFalse(proxy_module.is_port_free("127.0.0.1", 8080))

    def test_port_availability_matches_local_free_and_occupied_sockets(self):
        self.assertTrue(proxy_module.is_port_free("127.0.0.1", proxy_module.get_free_port()))
        with socket_lib.socket(socket_lib.AF_INET, socket_lib.SOCK_STREAM) as occupied:
            occupied.bind(("127.0.0.1", 0))
            port = occupied.getsockname()[1]
            self.assertFalse(proxy_module.is_port_free("127.0.0.1", port))

    def test_traffic_updates_are_aggregated_on_shutdown(self):
        while True:
            try:
                proxy_module.queue_bytes.get_nowait()
            except queue.Empty:
                break
        proxy_module.queue_bytes.put(4)
        proxy_module.queue_bytes.put(6)
        stop_event = threading.Event()
        stop_event.set()
        with mock.patch.object(proxy_module.CONFIG, "add_data_usage") as persist:
            proxy_module.worker_data_usage_tracker(stop_event)
        persist.assert_called_once_with(10)


class ProxyLifecycleTests(unittest.TestCase):
    def test_start_and_stop_are_idempotent(self):
        runner = __import__("proxy.tor", fromlist=["Runner"]).Runner(
            proxy_module.get_free_port(), 9050, app_window=None
        )
        self.assertTrue(runner.start())
        server = runner.server
        tracker = runner.data_usage_tracker
        self.assertFalse(runner.start())
        self.assertIs(runner.server, server)
        self.assertIs(runner.data_usage_tracker, tracker)
        self.assertTrue(runner.stop())
        self.assertFalse(runner.stop())
        self.assertTrue(runner.start())
        self.assertTrue(runner.stop())

    def test_tor_process_launch_failure_is_reported_without_ui_calls(self):
        from proxy.tor import TorRunner

        bridge = SimpleNamespace(
            tor_exit_signal=mock.Mock(),
            tor_log_signal=mock.Mock(),
            tor_status_signal=mock.Mock(),
        )
        runner = TorRunner(19050, 19051, 19053)
        runner.path_set = True
        runner.tor_path = "missing-tor-binary"
        runner.geoip_path = "geoip"
        runner.geoip6_path = "geoip6"
        runner.app_window = bridge
        with mock.patch("proxy.tor.subprocess.Popen", side_effect=FileNotFoundError):
            self.assertTrue(runner.start())
            runner.thread.join(timeout=2)
        self.assertFalse(runner.thread.is_alive())
        bridge.tor_exit_signal.emit.assert_called_once()
        runner.stop()


class ConfigurationTests(unittest.TestCase):
    def test_corrupt_and_partially_typed_config_recovers(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "config.json")
            with open(path, "w", encoding="utf-8") as stream:
                stream.write('{"data_usage": "bad", "proxy_port": 70000, "bridge": "yes"}')
            with mock.patch("proxy.config.resource_path", side_effect=lambda name: os.path.join(directory, name)):
                config = Config()
                loaded = config.load()
                self.assertEqual(loaded["data_usage"], 0)
                self.assertIsNone(loaded["proxy_port"])
                self.assertFalse(loaded["bridge"])
                config["data_usage"] = 123
                with open(path, encoding="utf-8") as stream:
                    self.assertEqual(json.load(stream)["data_usage"], 123)
                self.assertFalse(any(name.endswith(".tmp") for name in os.listdir(directory)))


class BundleSafetyTests(unittest.TestCase):
    def test_bundle_paths_cannot_escape_bundle_directory(self):
        with self.assertRaises(ValueError):
            updater.bundle_path("../outside.tar.gz")
        with self.assertRaises(ValueError):
            updater.bundle_path("C:\\outside.tar.gz")

    def test_official_base_rejects_credentials_and_untrusted_host(self):
        for base in (
            "https://user:pass@dist.torproject.org/torbrowser/",
            "https://dist.torproject.org.attacker.invalid/",
            "http://dist.torproject.org/",
        ):
            with self.subTest(base=base), self.assertRaises(ValueError):
                updater._official_base(base)

    def test_checksum_redirect_must_remain_on_official_host(self):
        response = SimpleNamespace(
            url="https://attacker.invalid/archive.tar.gz",
            close=mock.Mock(),
            raise_for_status=mock.Mock(),
        )
        with mock.patch.object(updater.requests, "get", return_value=response):
            with self.assertRaisesRegex(ValueError, "redirected"):
                updater._get_response("https://dist.torproject.org/torbrowser/archive")
        response.close.assert_called_once()

    def test_missing_checksum_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = os.path.join(directory, "bundles")
            os.makedirs(root)
            name = "tor-expert-bundle-windows-x86_64-13.5.23.tar.gz"
            with open(os.path.join(root, name), "wb") as stream:
                stream.write(b"archive")
            with mock.patch.object(updater, "resource_path", side_effect=lambda path: os.path.join(directory, path)):
                self.assertFalse(updater.check_hash(name, go_online=False))

    def test_cached_checksum_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = os.path.join(directory, "bundles")
            os.makedirs(root)
            name = "tor-expert-bundle-windows-x86_64-13.5.23.tar.gz"
            with open(os.path.join(root, name), "wb") as stream:
                stream.write(b"archive contents")
            with open(os.path.join(root, "13.5.23-sha256sums.txt"), "w", encoding="utf-8") as stream:
                stream.write("0" * 64 + "  " + name + "\n")
            with mock.patch.object(updater, "resource_path", side_effect=lambda path: os.path.join(directory, path)):
                self.assertFalse(updater.check_hash(name, go_online=False))

    def test_online_checksum_failures_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = os.path.join(directory, "bundles")
            os.makedirs(root)
            name = "tor-expert-bundle-windows-x86_64-13.5.23.tar.gz"
            with open(os.path.join(root, name), "wb") as stream:
                stream.write(b"archive contents")
            with mock.patch.object(updater, "resource_path", side_effect=lambda path: os.path.join(directory, path)), \
                 mock.patch.object(updater, "_fetch_checksum", side_effect=updater.requests.ConnectionError):
                self.assertFalse(updater.check_hash(name, go_online=True))
            response = SimpleNamespace(
                url="https://attacker.invalid/13.5.23/sha256sums.txt",
                close=mock.Mock(),
                raise_for_status=mock.Mock(),
            )
            with mock.patch.object(updater, "resource_path", side_effect=lambda path: os.path.join(directory, path)), \
                 mock.patch.object(updater.requests, "get", return_value=response):
                self.assertFalse(updater.check_hash(name, go_online=True))
            response.close.assert_called_once()

    def test_bad_checksum_does_not_replace_existing_archive(self):
        name = "tor-expert-bundle-windows-x86_64-13.5.23.tar.gz"
        original = b"existing bundle archive"
        bad_checksums = "0" * 64 + "  " + name + "\n"
        with tempfile.TemporaryDirectory() as directory:
            root = os.path.join(directory, "bundles")
            os.makedirs(root)
            path = os.path.join(root, name)
            with open(path, "wb") as stream:
                stream.write(original)
            with mock.patch.object(updater, "resource_path", side_effect=lambda item: os.path.join(directory, item)), \
                 mock.patch.object(updater, "_fetch_checksum", return_value=bad_checksums):
                with self.assertRaisesRegex(ValueError, "left untouched"):
                    updater.download_file(name, "13.5.23")
            with open(path, "rb") as stream:
                self.assertEqual(stream.read(), original)

    def test_supported_bundle_discovery_and_safe_extraction(self):
        os_name = {"Windows": "windows", "Linux": "linux"}.get(updater.OS_NAME)
        arch = "x86_64" if updater.ARCHITECTURE == 64 else "i686"
        if os_name is None:
            self.skipTest("Current OS is not a supported Tor bundle platform")
        name = f"tor-expert-bundle-{os_name}-{arch}-13.5.23"
        if not updater.check_bundle_compatibility(name + ".tar.gz"):
            self.skipTest("Current architecture is not supported by the Tor bundle selector")
        with tempfile.TemporaryDirectory() as directory:
            root = os.path.join(directory, "bundles")
            bundle_dir = os.path.join(root, name)
            os.makedirs(bundle_dir)
            self.assertTrue(updater.check_bundle_compatibility(bundle_dir))
            with mock.patch.object(updater, "resource_path", side_effect=lambda item: os.path.join(directory, item)):
                self.assertEqual(updater.get_own_bundles(), [bundle_dir])

            archive = os.path.join(directory, "safe.tar.gz")
            with tarfile.open(archive, "w:gz") as tar:
                payload = b"verified layout"
                member = tarfile.TarInfo("tor/tor")
                member.size = len(payload)
                tar.addfile(member, io.BytesIO(payload))
            destination = os.path.join(directory, "extracted")
            utils.extract_tar_gz_file(archive, destination)
            with open(os.path.join(destination, "tor", "tor"), "rb") as stream:
                self.assertEqual(stream.read(), b"verified layout")

    def test_download_checksum_mismatch_leaves_no_archive(self):
        name = "tor-expert-bundle-windows-x86_64-13.5.23.tar.gz"
        bad_checksums = "0" * 64 + "  " + name + "\n"

        class Response:
            headers = {}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def iter_content(self, chunk_size):
                yield b"untrusted archive data"

        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.object(updater, "resource_path", side_effect=lambda path: os.path.join(directory, path)), \
                 mock.patch.object(updater, "_fetch_checksum", return_value=bad_checksums), \
                 mock.patch.object(updater, "_get_response", return_value=Response()):
                with self.assertRaisesRegex(ValueError, "checksum"):
                    updater.download_file(name, "13.5.23")
                self.assertFalse(os.path.exists(os.path.join(directory, "bundles", name)))

    def test_tar_extraction_rejects_traversal(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = os.path.join(directory, "bad.tar.gz")
            with tarfile.open(archive, "w:gz") as tar:
                member = tarfile.TarInfo("../outside.txt")
                payload = b"unsafe"
                member.size = len(payload)
                tar.addfile(member, io.BytesIO(payload))
            destination = os.path.join(directory, "extracted")
            with self.assertRaises(ValueError):
                utils.extract_tar_gz_file(archive, destination)
            self.assertFalse(os.path.exists(destination))
            self.assertFalse(os.path.exists(os.path.join(directory, "outside.txt")))


if __name__ == "__main__":
    unittest.main()
