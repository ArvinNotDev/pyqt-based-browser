"""Validate manager records before presenting them in browser UI components."""

from collections.abc import Mapping
import os


def normalize_bookmark(record):
    """Return the documented bookmark fields or ``None`` for a stale record."""
    if not isinstance(record, Mapping):
        return None

    bookmark_id = record.get("id")
    title = record.get("title")
    url = record.get("url")
    if not isinstance(bookmark_id, str) or not bookmark_id.strip():
        return None
    if not isinstance(url, str) or not url.strip():
        return None
    if not isinstance(title, str):
        return None

    url = url.strip()
    title = title.strip() or url
    return {"id": bookmark_id, "title": title, "url": url}


def normalize_download(record):
    """Return the documented download fields in a display-friendly form."""
    if not isinstance(record, Mapping):
        return None

    download_id = record.get("id")
    file_name = record.get("file_name")
    path = record.get("path")
    url = record.get("url")
    state = record.get("state")

    if download_id is not None and not isinstance(download_id, str):
        download_id = str(download_id)
    if isinstance(file_name, str):
        file_name = file_name.strip()
    else:
        file_name = ""
    if isinstance(path, str):
        path = path.strip()
    else:
        path = ""
    if not file_name:
        file_name = os.path.basename(path) or "Download"
    if not isinstance(url, str):
        url = ""
    if not isinstance(state, str):
        state = "unknown"
    state = state.strip().casefold()
    if state not in {"requested", "downloading", "completed", "cancelled", "failed"}:
        state = "unknown"

    return {
        "id": download_id,
        "filename": file_name,
        "path": path,
        "url": url.strip(),
        "status": state,
        "received": _nonnegative_integer(record.get("received_bytes")),
        "total": _known_size(record.get("total_bytes")),
        "error": str(record.get("error") or "").strip(),
    }


def _nonnegative_integer(value):
    try:
        return max(0, int(value)) if value is not None else 0
    except (TypeError, ValueError, OverflowError):
        return 0


def _known_size(value):
    """A manager's negative total means unknown; zero is a known empty size."""
    try:
        value = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return value if value >= 0 else None
