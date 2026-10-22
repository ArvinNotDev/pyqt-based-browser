import json
import importlib
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


@pytest.fixture
def proxy_module():
    return importlib.import_module("proxy.proxy")


def test_block_and_exclusion_lists_round_trip_in_isolation(tmp_path, monkeypatch, proxy_module):
    blocked_file = tmp_path / "blocked.json"
    exclude_file = tmp_path / "excluded.json"
    monkeypatch.setattr(proxy_module, "BLOCKED_FILE", str(blocked_file))
    monkeypatch.setattr(proxy_module, "EXCLUDE_FILE", str(exclude_file))
    proxy_module.blocked_hosts = []
    proxy_module.exclude_hosts = []

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
    handler = SimpleNamespace(
        path=f"{host}:443",
        send_error=Mock(),
        server=SimpleNamespace(tor_socks_port=9050),
    )

    proxy_module.ProxyHandler.do_CONNECT(handler)

    handler.send_error.assert_called_once_with(403, "Forbidden: Blocked")
    socket_factory.assert_not_called()


def test_http_blocking_applies_to_wildcard_domain(proxy_module):
    proxy_module.blocked_hosts = ["*.ads.example"]
    handler = SimpleNamespace(
        path="http://banner.ads.example/image.png",
        command="GET",
        send_error=Mock(),
    )

    proxy_module.ProxyHandler._handle_http(handler)

    handler.send_error.assert_called_once_with(403, "Forbidden: Blocked")


@pytest.mark.parametrize("host", ["example.test", "www.example.test"])
def test_excluded_hosts_bypass_tor_socks_proxy(host, monkeypatch, proxy_module):
    proxy_module.blocked_hosts = []
    proxy_module.exclude_hosts = ["example.test"]
    monkeypatch.setattr(proxy_module, "PROXY_INTO_TOR", True)
    remote = Mock()
    monkeypatch.setattr(proxy_module.socks, "socksocket", Mock(return_value=remote))
    handler = SimpleNamespace(
        path=f"{host}:443",
        server=SimpleNamespace(tor_socks_port=9050),
        connection=object(),
        send_response=Mock(),
        end_headers=Mock(),
        _tunnel=Mock(),
    )

    proxy_module.ProxyHandler.do_CONNECT(handler)

    remote.connect.assert_called_once_with((host, 443))
    remote.set_proxy.assert_not_called()
    handler.send_response.assert_called_once_with(200, "Connection Established")
    handler._tunnel.assert_called_once()


def test_non_excluded_hosts_use_tor_socks_proxy(monkeypatch, proxy_module):
    proxy_module.blocked_hosts = []
    proxy_module.exclude_hosts = []
    monkeypatch.setattr(proxy_module, "PROXY_INTO_TOR", True)
    remote = Mock()
    monkeypatch.setattr(proxy_module.socks, "socksocket", Mock(return_value=remote))
    handler = SimpleNamespace(
        path="example.test:443",
        server=SimpleNamespace(tor_socks_port=9050),
        connection=object(),
        send_response=Mock(),
        end_headers=Mock(),
        _tunnel=Mock(),
    )

    proxy_module.ProxyHandler.do_CONNECT(handler)

    remote.set_proxy.assert_called_once_with(
        proxy_module.socks.SOCKS5, "127.0.0.1", 9050, rdns=True
    )
