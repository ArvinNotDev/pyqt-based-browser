"""Shared safe storage helpers for per-profile browser data."""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


logger = logging.getLogger(__name__)


def validate_profile_name(profile_name: str) -> str:
    """Return a safe, unchanged single path segment for a profile name.

    Unicode names, spaces, and ordinary punctuation remain valid. Invalid names
    are rejected instead of being normalized so existing names are never
    silently renamed.
    """
    if not isinstance(profile_name, str) or not profile_name:
        raise ValueError("Profile name must be a non-empty string")
    if profile_name in {".", ".."} or profile_name.isspace():
        raise ValueError("Profile name must identify a profile")
    if any(ord(char) < 32 or ord(char) == 127 for char in profile_name):
        raise ValueError("Profile name contains control characters")
    if any(char in profile_name for char in ("/", "\\", ":", "*", "?", '"', "<", ">", "|")):
        raise ValueError("Profile name contains a path or filename separator")
    if profile_name.endswith((".", " ")):
        raise ValueError("Profile name cannot end with a dot or space")
    if len(profile_name) > 120:
        raise ValueError("Profile name is too long")
    device_stem = profile_name.split(".", 1)[0].upper()
    if device_stem in {"CON", "PRN", "AUX", "NUL"} or re.fullmatch(
        r"(?:COM|LPT)[1-9]", device_stem
    ):
        raise ValueError("Profile name is reserved by the operating system")
    return profile_name


def profile_data_path(profile_name: str, *parts: str, base_dir: str | os.PathLike[str] = "profile_data") -> str:
    """Build a path below the profile data directory, rejecting escapes."""
    safe_name = validate_profile_name(profile_name)
    base = Path(base_dir).resolve()
    target = base.joinpath(safe_name, *parts)
    resolved_target = target.resolve()
    try:
        if os.path.commonpath((str(base), str(resolved_target))) != str(base):
            raise ValueError("Profile data path escapes the profile data directory")
    except ValueError:
        raise ValueError("Profile data path escapes the profile data directory") from None
    return str(target)


def atomic_write_json(path: str | os.PathLike[str], value: Any) -> None:
    """Write JSON by replacing the destination only after a complete flush."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_path = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent)
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=4)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, target)
    except Exception:
        try:
            os.unlink(temporary_path)
        except OSError:
            pass
        raise


def backup_corrupt_file(path: str | os.PathLike[str]) -> str:
    """Copy a malformed data file to a unique backup before it is replaced."""
    source = Path(path)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    for sequence in range(1000):
        suffix = f".corrupt-{stamp}-{sequence}.bak"
        backup = source.with_name(source.name + suffix)
        try:
            with source.open("rb") as reader, backup.open("xb") as writer:
                shutil.copyfileobj(reader, writer)
                writer.flush()
                os.fsync(writer.fileno())
            logger.warning("Preserved malformed JSON data at %s", backup)
            return str(backup)
        except FileExistsError:
            continue
    raise OSError(f"Could not create a backup for malformed data: {source}")
