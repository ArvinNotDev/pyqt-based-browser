import importlib
from unittest.mock import Mock

import pytest



def test_tor_runner_start_and_stop_manage_thread_and_process(monkeypatch):
    tor_module = importlib.import_module("proxy.tor")
    runner = tor_module.TorRunner(19050, 19051, 19053)
    runner.path_set = True
    runner.tor_path = "tor.exe"
    runner._run = Mock()
    created_threads = []

    class FakeThread:
        def __init__(self, target, args, daemon):
            self.target = target
            self.args = args
            self.daemon = daemon
            self.started = False

        def start(self):
            self.started = True

        def is_alive(self):
            return False

        def join(self, timeout):
            self.join_timeout = timeout

    def make_thread(target, args, daemon):
        thread = FakeThread(target, args, daemon)
        created_threads.append(thread)
        return thread

    monkeypatch.setattr(tor_module.threading, "Thread", make_thread)
    assert runner.start() is True

    assert len(created_threads) == 1
    assert created_threads[0].target == runner._run
    assert created_threads[0].args == (runner._lifecycle_generation,)
    assert created_threads[0].daemon is True
    assert created_threads[0].started is True

    process = Mock()
    process.poll.side_effect = [None, 0]
    runner.proc = process
    runner.stop()

    process.terminate.assert_called_once_with()
    process.wait.assert_called_once_with(timeout=tor_module.PROCESS_STOP_TIMEOUT)
    assert runner.proc is None
    assert runner.thread is None
    assert created_threads[0].join_timeout == tor_module.THREAD_STOP_TIMEOUT


def test_tor_runner_rejects_missing_local_bundle_without_starting_process(monkeypatch):
    tor_module = importlib.import_module("proxy.tor")
    monkeypatch.setattr(tor_module, "get_own_bundles", lambda: [])
    monkeypatch.setattr(tor_module, "list_downloaded_bundles", lambda: [])
    runner = tor_module.TorRunner(19050, 19051, 19053)

    assert runner.update_path() is False
    assert runner.path_set is False
    with monkeypatch.context() as patcher:
        popen = Mock()
        patcher.setattr(tor_module.subprocess, "Popen", popen)
        with pytest.raises(RuntimeError, match="verified compatible Tor bundle"):
            runner.start()
        popen.assert_not_called()


def test_tor_configuration_includes_configured_ports_and_bridge_settings(tmp_path):
    tor_module = importlib.import_module("proxy.tor")
    runner = tor_module.TorRunner(9050, 9051, 9053)
    runner.geoip_path = str(tmp_path / "data" / "geoip")
    runner.geoip6_path = str(tmp_path / "data" / "geoip6")
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
    lyrebird_path = tmp_path / "tor" / "pluggable_transports" / "lyrebird"
    lyrebird_path.parent.mkdir(parents=True)
    lyrebird_path.touch()
    runner.lyrebird_path = str(lyrebird_path)

    config = runner.generate_torcc()

    assert "SocksPort 9050" in config
    assert "ControlPort 9051" in config
    assert "DNSPort 9053" in config
    assert "UseBridges 1" in config
    plugin_command = runner._torrc_quote(runner.lyrebird_path)
    assert f"ClientTransportPlugin obfs4 exec {plugin_command}" in config


def test_invalid_port_is_not_reported_as_available():
    proxy_module = importlib.import_module("proxy.proxy")
    assert proxy_module.is_port_free("127.0.0.1", 65536) is False
