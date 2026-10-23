import os
import sys
from pathlib import Path

from app_paths import app_data_dir, resource_path, user_data_path


def test_source_paths_follow_the_current_working_directory(monkeypatch, tmp_path):
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.chdir(tmp_path)

    assert app_data_dir() == str(tmp_path)
    assert user_data_path("settings.json") == str(tmp_path / "settings.json")


def test_frozen_build_keeps_user_data_outside_the_extraction_directory(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "bundle"), raising=False)
    if os.name == "nt":
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local-app-data"))
    else:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "local-app-data"))

    data_dir = Path(app_data_dir())
    bundle_dir = Path(resource_path("assets", "icons"))
    settings_path = Path(user_data_path("settings.json"))

    assert data_dir == tmp_path / "local-app-data" / "ARMA Browser"
    assert bundle_dir == tmp_path / "bundle" / "assets" / "icons"
    assert settings_path == data_dir / "settings.json"
    assert data_dir.is_dir()
    assert data_dir != Path(sys._MEIPASS)
