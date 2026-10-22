import json
import time

from managers.history_manager import History


def test_history_is_persistent_and_isolated_per_profile(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    first = History("Guest")
    second = History("Work")

    first.add("https://example.test/one")
    second.add("https://example.test/two")

    assert History("Guest").history.keys() == {"https://example.test/one"}
    assert History("Work").history.keys() == {"https://example.test/two"}
    assert first.file_path != second.file_path


def test_add_records_visit_and_delete_can_filter_by_date_and_time(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    fixed_time = time.struct_time((2026, 10, 22, 9, 8, 7, 3, 295, -1))
    monkeypatch.setattr("managers.history_manager.localtime", lambda: fixed_time)
    history = History("Guest")

    history.add("https://example.test/")
    history.add("https://example.test/")

    assert history.history["https://example.test/"] == [
        {"date": "2026/10/22", "time": "09:08:07"},
        {"date": "2026/10/22", "time": "09:08:07"},
    ]
    history.delete(date="2026/10/22", time="09:08:07")
    assert history.history == {}


def test_delete_link_and_clear_persist(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    history = History("Guest")
    history.history = {"https://remove.test": [{"date": "2026/01/01", "time": "00:00:00"}]}
    history.save()

    history.delete(link="https://remove.test")
    assert History("Guest").history == {}

    history.history["https://clear.test"] = [{"date": "2026/01/01", "time": "00:00:00"}]
    history.clear()
    assert History("Guest").history == {}


def test_load_migrates_single_visit_dict_to_visit_list(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "profile_data" / "Guest" / "history.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps({"https://legacy.test": {"date": "2024/02/03", "time": "04:05:06"}}),
        encoding="utf-8",
    )

    assert History("Guest").history == {
        "https://legacy.test": [{"date": "2024/02/03", "time": "04:05:06"}]
    }


def test_malformed_history_starts_empty_without_touching_other_profiles(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    guest_path = tmp_path / "profile_data" / "Guest" / "history.json"
    guest_path.parent.mkdir(parents=True)
    guest_path.write_text("{broken", encoding="utf-8")

    history = History("Guest")

    assert history.history == {}
    assert guest_path.read_text(encoding="utf-8") == "{broken"
