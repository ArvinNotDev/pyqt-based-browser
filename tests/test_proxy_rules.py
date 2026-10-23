import json
import importlib
import io
from pathlib import Path
from email.message import Message
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


@pytest.fixture
def proxy_module(monkeypatch):
    module = importlib.import_module("proxy.proxy")
    monkeypatch.setattr(module, "blocked_hosts", [])
    monkeypatch.setattr(module, "exclude_hosts", [])
    monkeypatch.setattr(module, "PROXY_INTO_TOR", False)
    return module


def _connect_handler(proxy_module, path):
    handler = object.__new__(proxy_module.ProxyHandler)
    handler.path = path
    handler.server = SimpleNamespace(tor_socks_port=9050)
    handler.connection = object()
    handler.send_response = Mock()
    handler.end_headers = Mock()
    handler.send_error = Mock()
    handler._tunnel = Mock()
    return handler


def test_block_and_exclusion_lists_round_trip_in_isolation(tmp_path, monkeypatch, proxy_module):
    blocked_file = tmp_path / "blocked.json"
    exclude_file = tmp_path / "excluded.json"
    monkeypatch.setattr(proxy_module, "BLOCKED_FILE", str(blocked_file))
    monkeypatch.setattr(proxy_module, "EXCLUDE_FILE", str(exclude_file))
    assert proxy_module.add_to_blocked_hosts("ads.example") is True
    assert proxy_module.add_to_blocked_hosts("ads.example") is False
    assert proxy_module.add_to_exclude_hosts("private.example") is True
    proxy_module.save_blocked()
    proxy_module.save_exclude()

    proxy_module.blocked_hosts = []
    proxy_module.exclude_hosts = []
    proxy_module.load_blocked()
    proxy_module.load_exclude()

    assert proxy_module.get_blocked() == ["ads.example"]
    assert proxy_module.get_exclude() == ["private.example"]
    assert json.loads(blocked_file.read_text(encoding="utf-8")) == ["ads.example"]


@pytest.mark.parametrize("host", ["ads.example", "sub.ads.example", "tracker.ads.example"])
def test_blocked_connect_hosts_are_rejected_before_socket_creation(
    host, monkeypatch, proxy_module
):
    proxy_module.blocked_hosts = ["ads.example", "*.tracker.ads.example"]
    proxy_module.exclude_hosts = []
    socket_factory = Mock()
    monkeypatch.setattr(proxy_module.socks, "socksocket", socket_factory)
    handler = _connect_handler(proxy_module, f"{host}:443")

    handler.do_CONNECT()

    handler.send_error.assert_called_once_with(403, "Forbidden")
    socket_factory.assert_not_called()


def test_http_blocking_applies_to_wildcard_domain(proxy_module):
    proxy_module.blocked_hosts = ["*.ads.example"]
    handler = object.__new__(proxy_module.ProxyHandler)
    handler.path = "http://banner.ads.example/image.png"
    handler.command = "GET"
    handler.headers = Message()
    handler.rfile = io.BytesIO()
    handler.send_error = Mock()

    handler._handle_http()

    handler.send_error.assert_called_once_with(403, "Forbidden")


@pytest.mark.parametrize("host", ["example.test", "www.example.test"])
def test_excluded_hosts_bypass_tor_socks_proxy(host, monkeypatch, proxy_module):
    proxy_module.blocked_hosts = []
    proxy_module.exclude_hosts = ["example.test"]
    monkeypatch.setattr(proxy_module, "PROXY_INTO_TOR", True)
    remote = Mock()
    monkeypatch.setattr(proxy_module.socks, "socksocket", Mock(return_value=remote))
    handler = _connect_handler(proxy_module, f"{host}:443")

    handler.do_CONNECT()

    remote.connect.assert_called_once_with((host, 443))
    remote.set_proxy.assert_not_called()
    handler.send_response.assert_called_once_with(200, "Connection Established")
    handler._tunnel.assert_called_once()
    remote.close.assert_called_once_with()


def test_non_excluded_hosts_use_tor_socks_proxy(monkeypatch, proxy_module):
    proxy_module.blocked_hosts = []
    proxy_module.exclude_hosts = []
    monkeypatch.setattr(proxy_module, "PROXY_INTO_TOR", True)
    remote = Mock()
    monkeypatch.setattr(proxy_module.socks, "socksocket", Mock(return_value=remote))
    handler = _connect_handler(proxy_module, "example.test:443")

    handler.do_CONNECT()

    remote.set_proxy.assert_called_once_with(
        proxy_module.socks.SOCKS5, "127.0.0.1", 9050, rdns=True
    )
    handler.send_response.assert_called_once_with(200, "Connection Established")
    handler._tunnel.assert_called_once()
    remote.close.assert_called_once_with()


@pytest.mark.parametrize(
    "host",
    ["game-files.crazygames.com", "shellshockersio.game-files.crazygames.com"],
)
def test_crazygames_game_assets_use_direct_route(host, monkeypatch, proxy_module):
    rules_path = Path(__file__).resolve().parents[1] / "proxy" / "exclude_hosts.json"
    proxy_module.exclude_hosts = json.loads(rules_path.read_text(encoding="utf-8"))
    monkeypatch.setattr(proxy_module, "PROXY_INTO_TOR", True)

    assert proxy_module.route_uses_tor(host) is False


def test_optional_tor_proxy_is_applied_only_on_set_and_previous_route_restored(
    monkeypatch,
):
    from proxy import set_proxy as proxy_settings

    class FakeNetworkProxyFactory:
        @staticmethod
        def usesSystemConfiguration():
            return False

        @staticmethod
        def setUseSystemConfiguration(enabled):
            raise AssertionError("custom proxy configuration should be restored")

    class FakeNetworkProxy:
        HttpProxy = "http"
        NoProxy = "none"

        def __init__(self, proxy_type, host="", port=0):
            self.proxy_type = proxy_type
            self.host = host
            self.port = port

        @classmethod
        def applicationProxy(cls):
            return original_route

        @staticmethod
        def setApplicationProxy(value):
            applied_routes.append(value)

    original_route = FakeNetworkProxy("system", "system-proxy", 8080)
    applied_routes = []
    monkeypatch.setattr(proxy_settings, "QNetworkProxy", FakeNetworkProxy)
    monkeypatch.setattr(proxy_settings, "QNetworkProxyFactory", FakeNetworkProxyFactory)
    monkeypatch.setattr(proxy_settings, "_previous_proxy", None)
    monkeypatch.setattr(proxy_settings, "_application_proxy_active", False)
    monkeypatch.setattr(proxy_settings, "_uses_system_configuration", False)

    proxy_settings.manage_proxy(object(), "127.0.0.1", 43210, "set")
    proxy_settings.manage_proxy(object(), "127.0.0.1", 43211, "set")
    assert applied_routes[0].proxy_type == FakeNetworkProxy.HttpProxy
    assert (applied_routes[0].host, applied_routes[0].port) == ("127.0.0.1", 43210)
    assert applied_routes[1].port == 43211

    proxy_settings.manage_proxy(object(), "127.0.0.1", 43211, "clear")
    assert applied_routes[-1] is original_route
    applied_count = len(applied_routes)
    proxy_settings.manage_proxy(object(), "127.0.0.1", 43211, "clear")
    assert len(applied_routes) == applied_count


def test_optional_tor_proxy_restores_system_proxy_configuration(monkeypatch):
    from proxy import set_proxy as proxy_settings

    restored = []

    class FakeNetworkProxy:
        HttpProxy = "http"
        NoProxy = "none"

        def __init__(self, proxy_type, host="", port=0):
            self.proxy_type = proxy_type
            self.host = host
            self.port = port

        @staticmethod
        def applicationProxy():
            return FakeNetworkProxy("system", "system-proxy", 8080)

        @staticmethod
        def setApplicationProxy(_proxy):
            return None

    class FakeNetworkProxyFactory:
        @staticmethod
        def usesSystemConfiguration():
            return True

        @staticmethod
        def setUseSystemConfiguration(enabled):
            restored.append(enabled)

    monkeypatch.setattr(proxy_settings, "QNetworkProxy", FakeNetworkProxy)
    monkeypatch.setattr(proxy_settings, "QNetworkProxyFactory", FakeNetworkProxyFactory)
    monkeypatch.setattr(proxy_settings, "_previous_proxy", None)
    monkeypatch.setattr(proxy_settings, "_application_proxy_active", False)
    monkeypatch.setattr(proxy_settings, "_uses_system_configuration", False)

    proxy_settings.manage_proxy(object(), "127.0.0.1", 43210, "set")
    proxy_settings.manage_proxy(object(), "127.0.0.1", 43210, "clear")

    assert restored == [True]
