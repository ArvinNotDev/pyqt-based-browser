import json

import pytest
from PySide6.QtGui import QColor, QImage

from managers.dashboard_manager import DashboardManager


def test_dashboard_preferences_are_profile_scoped_and_persist(tmp_path):
    base = tmp_path / "profile_data"
    first = DashboardManager("Guest", base_dir=base)
    first.update({"notes": "remember the draft", "clock_24h": False, "overlay": 34})
    first.set_shortcuts([
        {"title": "Example", "url": "https://example.test"},
        {"title": "Docs", "url": "https://docs.example.test/guide"},
    ])

    loaded = DashboardManager("Guest", base_dir=base)
    work = DashboardManager("Work", base_dir=base)
    assert loaded.data["notes"] == "remember the draft"
    assert loaded.data["clock_24h"] is False
    assert loaded.data["overlay"] == 34
    assert [item["title"] for item in loaded.data["shortcuts"]] == ["Example", "Docs"]
    assert work.data["notes"] == ""
    assert work.data["clock_24h"] is True


def test_additional_quick_notes_persist_per_profile_and_are_bounded(tmp_path):
    base = tmp_path / "profile_data"
    guest = DashboardManager("Guest", base_dir=base)
    guest.update({"quick_notes": ["first thought", "second thought"]})

    loaded = DashboardManager("Guest", base_dir=base)
    work = DashboardManager("Work", base_dir=base)
    assert loaded.data["quick_notes"] == ["first thought", "second thought"]
    assert work.data["quick_notes"] == []
    with pytest.raises(ValueError):
        loaded.update({"quick_notes": ["note"] * 11})


def test_shortcuts_reject_bad_urls_and_duplicates(tmp_path):
    manager = DashboardManager("Guest", base_dir=tmp_path / "profiles")
    with pytest.raises(ValueError):
        manager.set_shortcuts([{"title": "Local", "url": "file:///private"}])
    with pytest.raises(ValueError):
        manager.set_shortcuts([
            {"title": "One", "url": "https://example.test/"},
            {"title": "Duplicate", "url": "https://example.test"},
        ])
    manager.set_shortcuts([])
    assert manager.data["shortcuts"] == []


def test_malformed_dashboard_actions_do_not_replace_preferences(tmp_path):
    manager = DashboardManager("Guest", base_dir=tmp_path / "profiles")
    manager.update({"overlay": 42, "widgets": {"notes": False}})
    before = dict(manager.data)

    with pytest.raises(ValueError):
        manager.set_shortcuts({"url": "https://example.test"})
    with pytest.raises(ValueError):
        manager.set_wallpaper(42)
    with pytest.raises(ValueError):
        manager.update({"widgets": []})
    with pytest.raises(ValueError):
        manager.update({"overlay": "bad"})
    with pytest.raises(ValueError):
        manager.update({"wallpaper": 42})
    with pytest.raises(ValueError):
        manager.update({"notes": None})

    assert manager.data == before


def test_missing_wallpaper_falls_back_and_corrupt_data_is_backed_up(tmp_path):
    base = tmp_path / "profiles"
    profile = base / "Guest"
    profile.mkdir(parents=True)
    (profile / "dashboard.json").write_text(
        json.dumps({"wallpaper": "file:missing.jpg", "notes": "safe"}), encoding="utf-8"
    )
    loaded = DashboardManager("Guest", base_dir=base)
    assert loaded.data["wallpaper"] == "aurora"
    assert loaded.data["notes"] == "safe"

    with open(loaded.file_path, "w", encoding="utf-8") as stream:
        stream.write("{broken")
    recovered = DashboardManager("Guest", base_dir=base)
    assert recovered.data["wallpaper"] == "aurora"
    recovered.save()
    assert list(profile.glob("dashboard.json.corrupt-*.bak"))


def test_wallpaper_reader_rejects_paths_outside_managed_assets(tmp_path):
    manager = DashboardManager("Guest", base_dir=tmp_path / "profiles")
    assert manager.read_wallpaper("../dashboard.json") is None
    assert manager.read_wallpaper("..\\dashboard.json") is None


def test_imported_wallpaper_is_managed_and_survives_reload(tmp_path):
    image = QImage(32, 20, QImage.Format.Format_RGB32)
    image.fill(QColor("#6789ab"))
    source = tmp_path / "wallpaper.png"
    assert image.save(str(source), "PNG")

    base = tmp_path / "profiles"
    manager = DashboardManager("Guest", base_dir=base)
    wallpaper_key = manager.import_wallpaper(str(source))
    assert wallpaper_key.startswith("file:")
    assert manager.wallpaper_dir.joinpath(wallpaper_key[5:]).is_file()
    assert manager.wallpaper_data_url().startswith("data:image/jpeg;base64,")

    reloaded = DashboardManager("Guest", base_dir=base)
    assert reloaded.data["wallpaper"] == wallpaper_key
    assert reloaded.wallpaper_data_url()



def test_dashboard_widget_sizes_are_profile_scoped_normalized_and_validated(tmp_path):
    base = tmp_path / "profiles"
    manager = DashboardManager("Guest", base_dir=base)
    manager.update({"widget_sizes": {"notes": "wide", "bookmarks": "compact"}})

    loaded = DashboardManager("Guest", base_dir=base)
    work = DashboardManager("Work", base_dir=base)
    assert loaded.data["widget_sizes"]["notes"] == "wide"
    assert loaded.data["widget_sizes"]["bookmarks"] == "compact"
    assert loaded.data["widget_sizes"]["recent"] == "standard"
    assert work.data["widget_sizes"]["notes"] == "standard"

    with pytest.raises(ValueError):
        loaded.update({"widget_sizes": {"notes": "gigantic"}})
    with pytest.raises(ValueError):
        loaded.update({"widget_sizes": {"unknown": "wide"}})
    with pytest.raises(ValueError):
        loaded.update({"widget_sizes": []})
