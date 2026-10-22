import json
import importlib


def test_proxy_config_defaults_serialize_and_reload(tmp_path, monkeypatch):
    config_module = importlib.import_module("proxy.config")
    monkeypatch.setattr(
        config_module.Config, "default_data", dict(config_module.Config.default_data)
    )
    config_file = tmp_path / "proxy-config.json"
    monkeypatch.setattr(config_module, "resource_path", lambda _path: str(config_file))

    config = config_module.Config()
    config.data = {}
    assert config.load() == config_module.Config.default_data
    assert config["mode"] == "dark"

    config["proxy_port"] = 8118
    config["bridge"] = True
    saved = json.loads(config_file.read_text(encoding="utf-8"))
    assert saved["proxy_port"] == 8118
    assert saved["bridge"] is True

    reloaded = config_module.Config()
    reloaded.data = {}
    monkeypatch.setattr(config_module, "resource_path", lambda _path: str(config_file))
    reloaded.load()
    assert reloaded["proxy_port"] == 8118
    assert reloaded["bridge"] is True


def test_proxy_config_malformed_json_falls_back_to_defaults(tmp_path, monkeypatch):
    config_module = importlib.import_module("proxy.config")
    monkeypatch.setattr(
        config_module.Config, "default_data", dict(config_module.Config.default_data)
    )
    config_file = tmp_path / "proxy-config.json"
    config_file.write_text("{broken", encoding="utf-8")
    monkeypatch.setattr(config_module, "resource_path", lambda _path: str(config_file))

    config = config_module.Config()
    config.data = {}

    assert config.load() == config_module.Config.default_data
    assert config_file.read_text(encoding="utf-8") == "{broken"
