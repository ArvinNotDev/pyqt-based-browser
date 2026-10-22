import importlib
from unittest.mock import Mock



def test_tor_runner_start_and_stop_manage_thread_and_process(tmp_path, monkeypatch):
    tor_module = importlib.import_module("proxy.tor")
    runner = tor_module.TorRunner.__new__(tor_module.TorRunner)
    runner.proc = None
    runner.thread = None
    runner._run = Mock()
    created_threads = []

    class FakeThread:
        def __init__(self, target, daemon):
            self.target = target
            self.daemon = daemon
            self.started = False

        def start(self):
            self.started = True

        def is_alive(self):
            return False

        def join(self):
            raise AssertionError("a stopped worker should not be joined")

    def make_thread(target, daemon):
        thread = FakeThread(target, daemon)
        created_threads.append(thread)
        return thread

    monkeypatch.setattr(tor_module.threading, "Thread", make_thread)
    runtime_file = tmp_path / "temp_torrc.txt"
    runtime_file.write_text("SocksPort 9050", encoding="utf-8")
    monkeypatch.setattr(tor_module, "resource_path", lambda _path: str(runtime_file))
    runner.start()

    assert len(created_threads) == 1
    assert created_threads[0].target == runner._run
    assert created_threads[0].daemon is True
    assert created_threads[0].started is True

    process = Mock()
    runner.proc = process
    runner.stop()

    process.terminate.assert_called_once_with()
    process.wait.assert_called_once_with()
    assert runner.proc is None
    assert runner.thread is None
    assert not runtime_file.exists()


def test_tor_runner_rejects_missing_local_bundle_without_starting_process(monkeypatch):
    tor_module = importlib.import_module("proxy.tor")
    monkeypatch.setattr(tor_module, "get_own_bundles", lambda: [])
    monkeypatch.setattr(tor_module, "list_downloaded_bundles", lambda: [])
    runner = tor_module.TorRunner.__new__(tor_module.TorRunner)

    assert runner.update_path() is False


def test_tor_configuration_includes_configured_ports_and_bridge_settings():
    tor_module = importlib.import_module("proxy.tor")
    runner = tor_module.TorRunner.__new__(tor_module.TorRunner)
    runner.socks_port = 9050
    runner.contorl_port = 9051
    runner.dns_port = 9053
    runner.geoip_path = "data/geoip"
    runner.geoip6_path = "data/geoip6"
    runner.Log = "notice stdout"
    runner.MaxCircuitDirtiness = 300
    runner.NewCircuitPeriod = 30
    runner.ExcludeNodes = []
    runner.ExitNodes = []
    runner.StrictNodes = 0
    runner.ClientUseIPv4 = 1
    runner.ClientUseIPv6 = 0
    runner.bridge = True
    runner.bridges = "obfs4 192.0.2.10:443 fingerprint cert=example"
    runner.bridge_types = ["obfs4"]
    runner.lyrebird_path = "tor/pluggable_transports/lyrebird"

    config = runner.generate_torcc()

    assert "SocksPort 9050" in config
    assert "ControlPort 9051" in config
    assert "DNSPort 9053" in config
    assert "UseBridges 1" in config
    assert "ClientTransportPlugin obfs4 exec tor/pluggable_transports/lyrebird" in config


def test_invalid_port_is_not_reported_as_available():
    proxy_module = importlib.import_module("proxy.proxy")
    assert proxy_module.is_port_free("127.0.0.1", 65536) is False
