from ui.essential_features import is_blocked_host
from ui.session_store import sanitize_session_data


def test_ad_and_tracker_rules_match_host_boundaries():
    assert is_blocked_host("doubleclick.net")
    assert is_blocked_host("stats.doubleclick.net")
    assert is_blocked_host("GOOGLESYNDICATION.COM.")
    assert not is_blocked_host("notdoubleclick.net")
    assert not is_blocked_host("doubleclick.net.attacker.example")
    assert not is_blocked_host("")
    assert not is_blocked_host(None)


def test_session_data_accepts_only_safe_browser_urls_and_clamps_active_tab():
    session = sanitize_session_data({
        "profile": "Research",
        "tabs": [
            "https://example.test/path",
            "javascript:alert(1)",
            "file:///C:/secret.txt",
            "arma://dashboard/",
            "https://user:password@example.test/",
            "https://second.example/",
            "arma://dashboard-malicious/",
        ],
        "active_index": 99,
    })

    assert session == {
        "profile": "Research",
        "tabs": [
            "https://example.test/path",
            "arma://dashboard/",
            "https://second.example/",
        ],
        "active_index": 2,
    }


def test_invalid_or_empty_session_is_not_restored():
    assert sanitize_session_data(None) is None
    assert sanitize_session_data({"tabs": []}) is None
    assert sanitize_session_data({"tabs": ["javascript:alert(1)"]}) is None


def test_session_validation_limits_tabs_and_replaces_invalid_profile():
    raw = {
        "profile": " " * 100,
        "tabs": [f"https://site-{index}.example/" for index in range(60)],
        "active_index": True,
    }
    session = sanitize_session_data(raw)
    assert session is not None
    assert len(session["tabs"]) == 50
    assert session["active_index"] == 0
    assert session["profile"] == "Guest"
