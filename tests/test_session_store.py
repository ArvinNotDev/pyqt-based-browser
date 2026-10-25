import json

from ui.session_store import load_last_session
from ui.settings import Settings


def test_last_session_restores_valid_profile_tabs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Settings.save_profiles(["Guest", "Research"])

    research = Settings()
    research.restore_session = True
    research.private_mode = False
    research.save("Research")

    session_dir = tmp_path / "profile_data"
    (session_dir / "Research").mkdir(parents=True)
    (session_dir / "last_session.json").write_text(
        json.dumps({
            "profile": "Research",
            "tabs": ["https://example.test/docs", "arma://dashboard/"],
            "active_index": 1,
        }),
        encoding="utf-8",
    )

    session = load_last_session()
    assert session == {
        "profile": "Research",
        "tabs": ["https://example.test/docs", "arma://dashboard/"],
        "active_index": 1,
    }


def test_private_or_disabled_profiles_do_not_restore_sessions(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Settings.save_profiles(["Guest"])
    settings = Settings()
    settings.private_mode = True
    settings.save("Guest")

    root = tmp_path / "profile_data"
    root.mkdir()
    (root / "last_session.json").write_text(
        json.dumps({
            "profile": "Guest",
            "tabs": ["https://example.test/"],
            "active_index": 0,
        }),
        encoding="utf-8",
    )
    assert load_last_session() is None

    settings.private_mode = False
    settings.restore_session = False
    settings.save("Guest")
    assert load_last_session() is None
