import hashlib
import json

import pytest

from managers.profile_manager import Profile
from ui.settings import Settings


@pytest.fixture(autouse=True)
def stable_machine_id(monkeypatch):
    monkeypatch.setattr(Profile, "get_machine_id", staticmethod(lambda: "test-machine"))


def test_defaults_are_independent_and_stable():
    first = Settings()
    second = Settings()

    assert first.homepage == "https://www.google.com"
    assert first.default_search_engine == "https://www.google.com/search?q="
    assert (first.window_width, first.window_height) == (1280, 720)
    assert first.dark_mode is False
    assert first.save_history is True
    assert first.save_cookies is True
    assert first.private_mode is False
    assert first.download_folder == "./downloads"
    assert first.show_dev_tools is False
    assert first.hardware_acceleration is True
    assert first.profile is not second.profile
    assert first.profiles_list is not second.profiles_list


def test_save_and_load_are_scoped_by_profile_name(tmp_path):
    settings_file = tmp_path / "settings.json"
    guest = Settings(file_path=str(settings_file))
    guest.homepage = "https://guest.example/"
    guest.save("Guest")

    work = Settings(file_path=str(settings_file))
    work.homepage = "https://work.example/"
    work.save("Work")

    loaded = Settings(file_path=str(settings_file))
    loaded.load("Guest")
    assert loaded.homepage == "https://guest.example/"

    loaded.load("Work")
    assert loaded.homepage == "https://work.example/"
    assert set(json.loads(settings_file.read_text(encoding="utf-8"))) == {"Guest", "Work"}


def test_loading_older_settings_keeps_new_defaults_and_ignores_unknown_keys(tmp_path):
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(
        json.dumps({"Guest": {"homepage": "https://old.example/", "future_option": True}}),
        encoding="utf-8",
    )

    settings = Settings(file_path=str(settings_file))
    settings.load("Guest")

    assert settings.homepage == "https://old.example/"
    assert settings.hardware_acceleration is True
    assert not hasattr(settings, "future_option")


def test_save_recovers_from_malformed_json(tmp_path):
    settings_file = tmp_path / "settings.json"
    settings_file.write_text("{broken", encoding="utf-8")

    settings = Settings(file_path=str(settings_file))
    settings.save("Guest")

    saved = json.loads(settings_file.read_text(encoding="utf-8"))
    assert saved["Guest"]["homepage"] == settings.homepage


def test_load_recovers_from_malformed_json(tmp_path):
    settings_file = tmp_path / "settings.json"
    settings_file.write_text("{broken", encoding="utf-8")

    Settings(file_path=str(settings_file)).load("Guest")


def test_profile_lists_are_isolated_by_machine_hash(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    machine_id = "machine-one"
    monkeypatch.setattr(Profile, "get_machine_id", staticmethod(lambda: machine_id))
    Settings.save_profiles(["Guest", "Personal"])

    machine_id = "machine-two"
    Settings.save_profiles(["Guest", "Work"])

    data = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    assert data[hashlib.sha256(b"machine-one").hexdigest()]["profiles"] == ["Guest", "Personal"]
    assert data[hashlib.sha256(b"machine-two").hexdigest()]["profiles"] == ["Guest", "Work"]


def test_load_profile_settings_uses_this_machines_profile_list(tmp_path, monkeypatch):
    settings_file = tmp_path / "settings.json"
    machine_hash = hashlib.sha256(b"test-machine").hexdigest()
    settings_file.write_text(
        json.dumps({machine_hash: {"profiles": ["Guest", "Research"]}}), encoding="utf-8"
    )

    settings = Settings(file_path=str(settings_file))
    settings.load_profile_settings()

    assert settings.profiles_list == ["Guest", "Research"]
