"""Qt WebEngine download handling with safe destinations and UI-friendly state."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit
from uuid import uuid4

from PySide6.QtCore import QObject, QStandardPaths, QUrl, Signal
from PySide6.QtGui import QDesktopServices


class DownloadManager(QObject):
    """Manage accepted WebEngine downloads for the lifetime of a browser profile.

    Public states are ``requested``, ``downloading``, ``completed``,
    ``cancelled``, and ``failed``. Download records are in-memory; browser
    history and private-mode policy are deliberately managed separately.
    """

    downloads_changed = Signal()

    _TERMINAL_STATES = {"completed", "cancelled", "failed"}

    def __init__(self, profile_name: str, download_dir: str | os.PathLike[str] | None = None):
        super().__init__()
        from managers.storage import validate_profile_name

        self.profile_name = validate_profile_name(profile_name)
        if download_dir is None:
            download_dir = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation)
            if not download_dir:
                download_dir = str(Path.home() / "Downloads")
        self.download_dir = os.path.abspath(os.path.expanduser(os.fspath(download_dir)))
        self._downloads: list[dict[str, Any]] = []
        self._requests: dict[str, Any] = {}
        self._profile: Any = None

    def attach_profile(self, profile) -> None:
        """Connect to the profile's Qt WebEngine ``downloadRequested`` signal."""
        if profile is self._profile:
            return
        if self._profile is not None:
            try:
                self._profile.downloadRequested.disconnect(self._on_download_requested)
            except (AttributeError, RuntimeError, TypeError):
                pass
        self._profile = profile
        profile.downloadRequested.connect(self._on_download_requested)

    @staticmethod
    def _request_value(request, method: str, fallback=None):
        value = getattr(request, method, fallback)
        if callable(value):
            try:
                return value()
            except (RuntimeError, TypeError):
                return fallback
        return value

    @staticmethod
    def _url_string(value) -> str:
        if hasattr(value, "toString"):
            try:
                return value.toString()
            except RuntimeError:
                pass
        return str(value or "")

    @staticmethod
    def _safe_file_name(suggested: str, url: str) -> str:
        raw_name = os.path.basename(str(suggested or "").replace("\\", "/"))
        if not raw_name or raw_name in {".", ".."}:
            try:
                raw_name = unquote(os.path.basename(urlsplit(url).path))
            except ValueError:
                raw_name = ""
        raw_name = re.sub(r'[<>:"/\\|?*\x00-\x1f\x7f]', "_", raw_name).strip(" .")
        if not raw_name:
            raw_name = "download"
        if raw_name.split(".", 1)[0].upper() in {
            "CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))
        }:
            raw_name = f"_{raw_name}"
        if len(raw_name) > 180:
            stem, extension = os.path.splitext(raw_name)
            raw_name = stem[: max(1, 180 - len(extension))] + extension[:60]
        return raw_name

    def _allocate_path(self, file_name: str) -> tuple[str, str]:
        os.makedirs(self.download_dir, exist_ok=True)
        root = os.path.realpath(self.download_dir)
        stem, extension = os.path.splitext(file_name)
        reserved = {os.path.normcase(item["path"]) for item in self._downloads}
        index = 0
        while True:
            candidate_name = file_name if index == 0 else f"{stem} ({index}){extension}"
            candidate = os.path.abspath(os.path.join(root, candidate_name))
            if os.path.commonpath((root, candidate)) != root:
                raise ValueError("Download destination escapes the download directory")
            if not os.path.lexists(candidate) and os.path.normcase(candidate) not in reserved:
                return candidate_name, candidate
            index += 1

    @staticmethod
    def _state_name(request) -> str:
        state = DownloadManager._request_value(request, "state", "")
        name = getattr(state, "name", str(state)).split(".")[-1].replace("_", "").lower()
        if "requested" in name:
            return "requested"
        if "inprogress" in name or "progress" in name:
            return "downloading"
        if "completed" in name or "complete" in name:
            return "completed"
        if "cancelled" in name or "canceled" in name:
            return "cancelled"
        if "interrupted" in name or "failed" in name:
            return "failed"
        return "requested"

    def _on_download_requested(self, request) -> None:
        download_id = uuid4().hex
        url = self._url_string(self._request_value(request, "url", ""))
        suggested = self._request_value(request, "suggestedFileName", "")
        if not suggested:
            suggested = self._request_value(request, "downloadFileName", "")
        safe_name = self._safe_file_name(suggested, url)
        record = None
        try:
            safe_name, path = self._allocate_path(safe_name)
            request.setDownloadDirectory(self.download_dir)
            request.setDownloadFileName(safe_name)
            total_bytes = self._request_value(request, "totalBytes", -1)
            record = {
                "id": download_id,
                "file_name": safe_name,
                "path": path,
                "url": url,
                "received_bytes": max(0, int(self._request_value(request, "receivedBytes", 0) or 0)),
                "total_bytes": int(total_bytes if total_bytes is not None else -1),
                "state": "requested",
                "error": "",
            }
            self._downloads.append(record)
            self._requests[download_id] = request
            for signal_name in ("receivedBytesChanged", "totalBytesChanged", "stateChanged"):
                signal = getattr(request, signal_name, None)
                if signal is not None and hasattr(signal, "connect"):
                    signal.connect(lambda *args, current_id=download_id: self._refresh(current_id))
            request.accept()
            self._refresh(download_id)
        except Exception as exc:
            try:
                request.cancel()
            except Exception:
                pass
            self._requests.pop(download_id, None)
            failed = next((item for item in self._downloads if item["id"] == download_id), None)
            if failed is None:
                self._downloads.append({
                    "id": download_id,
                    "file_name": safe_name,
                    "path": "",
                    "url": url,
                    "received_bytes": 0,
                    "total_bytes": -1,
                    "state": "failed",
                    "error": str(exc),
                })
            else:
                failed["state"] = "failed"
                failed["error"] = str(exc)
        self.downloads_changed.emit()

    def _refresh(self, download_id: str) -> None:
        request = self._requests.get(download_id)
        record = next((item for item in self._downloads if item["id"] == download_id), None)
        if request is None or record is None:
            return
        received = self._request_value(request, "receivedBytes", record["received_bytes"])
        total = self._request_value(request, "totalBytes", record["total_bytes"])
        try:
            record["received_bytes"] = max(0, int(received))
        except (TypeError, ValueError):
            pass
        try:
            record["total_bytes"] = int(total)
        except (TypeError, ValueError):
            pass
        record["state"] = self._state_name(request)
        if record["state"] == "failed":
            record["error"] = str(self._request_value(request, "interruptReasonString", "") or "Download interrupted")
        self.downloads_changed.emit()

    def get_downloads(self) -> list[dict]:
        return [dict(item) for item in self._downloads]

    def cancel(self, download_id: str) -> bool:
        request = self._requests.get(download_id)
        record = next((item for item in self._downloads if item["id"] == download_id), None)
        if request is None or record is None or record["state"] in self._TERMINAL_STATES:
            return False
        try:
            request.cancel()
        except Exception as exc:
            record["error"] = str(exc)
            record["state"] = "failed"
            self.downloads_changed.emit()
            return False
        record["state"] = "cancelled"
        record["error"] = ""
        self.downloads_changed.emit()
        return True

    def open_file(self, download_id: str) -> bool:
        record = next((item for item in self._downloads if item["id"] == download_id), None)
        if record is None or record["state"] != "completed" or not record["path"]:
            return False
        path = os.path.realpath(record["path"])
        if not os.path.isfile(path):
            return False
        return bool(QDesktopServices.openUrl(QUrl.fromLocalFile(path)))

    def clear_finished(self) -> None:
        before = len(self._downloads)
        self._downloads = [item for item in self._downloads if item["state"] not in self._TERMINAL_STATES]
        kept_ids = {item["id"] for item in self._downloads}
        self._requests = {key: value for key, value in self._requests.items() if key in kept_ids}
        if len(self._downloads) != before:
            self.downloads_changed.emit()
