"""Application resource and writable-data paths for source and frozen builds."""
from __future__ import annotations

import os
import sys
from pathlib import Path


APP_DIRECTORY_NAME = "ARMA Browser"


def is_frozen() -> bool:
    """Return whether the application is running from a PyInstaller bundle."""
    return bool(getattr(sys, "frozen", False))


def resource_root() -> Path:
    """Locate bundled, read-only resources independently from the current directory."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS"))
    return Path(__file__).resolve().parent


def resource_path(*parts: str | os.PathLike[str]) -> str:
    """Return an absolute path to a bundled resource (icons, dashboard files, etc.)."""
    return str(resource_root().joinpath(*(os.fspath(part) for part in parts)))


def app_data_dir() -> str:
    """Return the writable application directory.

    Source runs retain their historical working-directory behavior. Frozen Windows
    builds store mutable data under LocalAppData, never in PyInstaller's temp folder
    or beside an executable that may live in a protected directory.
    """
    if not is_frozen():
        return os.path.abspath(os.getcwd())

    if os.name == "nt":
        root = os.environ.get("LOCALAPPDATA")
        base = Path(root) if root else Path.home() / "AppData" / "Local"
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        root = os.environ.get("XDG_DATA_HOME")
        base = Path(root) if root else Path.home() / ".local" / "share"

    directory = base / APP_DIRECTORY_NAME
    directory.mkdir(parents=True, exist_ok=True)
    return str(directory)


def user_data_path(*parts: str | os.PathLike[str]) -> str:
    """Build a path for mutable data such as settings, profiles, and proxy state."""
    return os.path.join(app_data_dir(), *(os.fspath(part) for part in parts))


__all__ = [
    "APP_DIRECTORY_NAME",
    "app_data_dir",
    "is_frozen",
    "resource_path",
    "resource_root",
    "user_data_path",
]
