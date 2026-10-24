"""Safe session persistence helpers which do not import Qt WebEngine.

This module is intentionally safe to use before QApplication is constructed,
so the restored profile's process-wide Chromium preferences can be applied
before Qt WebEngine initializes.
"""

from __future__ import annotations

import json
import os
from urllib.parse import urlsplit


def sanitize_session_data(value):
    """Validate a saved session before opening URLs from it."""
    if not isinstance(value, dict):
        return None
    raw_tabs = value.get("tabs")
    if not isinstance(raw_tabs, list):
        return None

    tabs = []
    for raw_url in raw_tabs[:50]:
        if not isinstance(raw_url, str) or len(raw_url) > 8192:
            continue
        candidate = raw_url.strip()
        try:
            parsed = urlsplit(candidate)
            # Reject malformed authorities and out-of-range ports.
            _ = parsed.port
        except ValueError:
            continue
        if (
            parsed.scheme.lower() in {"http", "https"}
            and parsed.hostname
            and parsed.username is None
            and parsed.password is None
        ):
            tabs.append(candidate)
        elif parsed.scheme.lower() == "arma" and parsed.netloc.casefold() == "dashboard":
            tabs.append("arma://dashboard/")
    if not tabs:
        return None

    active_index = value.get("active_index", 0)
    if not isinstance(active_index, int) or isinstance(active_index, bool):
        active_index = 0
    active_index = max(0, min(active_index, len(tabs) - 1))
    profile = value.get("profile", "Guest")
    if not isinstance(profile, str) or not profile.strip() or len(profile) > 80:
        profile = "Guest"
    return {"profile": profile.strip(), "tabs": tabs, "active_index": active_index}


def _session_path(profile_name: str) -> str:
    return os.path.join(os.getcwd(), "profile_data", profile_name, "session.json")


def _last_session_path() -> str:
    return os.path.join(os.getcwd(), "profile_data", "last_session.json")


def _read_json(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as stream:
            value = json.load(stream)
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, json.JSONDecodeError):
        return {}


def load_last_session():
    """Load the most recent allowed session without initializing Qt WebEngine."""
    from ui.settings import Settings

    settings = Settings()
    settings.load_profile_settings()
    profiles = settings.profiles_list or ["Guest"]
    default_profile = "Guest" if "Guest" in profiles else profiles[0]

    last_session = sanitize_session_data(_read_json(_last_session_path()))
    if last_session is not None and last_session.get("profile") in profiles:
        profile_name = last_session["profile"]
        session = last_session
    else:
        profile_name = default_profile
        session = sanitize_session_data(_read_json(_session_path(profile_name)))

    settings.load(profile_name)
    if not bool(getattr(settings, "restore_session", True)) or bool(settings.private_mode):
        return None
    if session is None:
        session = sanitize_session_data(_read_json(_session_path(profile_name)))
    if session is None:
        return None
    session["profile"] = profile_name
    return session
