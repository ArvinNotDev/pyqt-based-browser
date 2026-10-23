"""Qt WebEngine download handling with safe destinations and UI-friendly state."""

from __future__ import annotations

import os
import re
from copy import deepcopy
from pathlib import Path
from threading import Lock
from typing import Any
from urllib.parse import unquote, urlsplit
from uuid import uuid4
import weakref

from PySide6.QtCore import QObject, QStandardPaths, QUrl, Signal
from PySide6.QtGui import QDesktopServices


class DownloadManager(QObject):
    """Manage accepted WebEngine downloads for the lifetime of a browser profile.

    Public states are ``requested``, ``downloading``, ``completed``,
    ``cancelled``, and ``failed``. Download records are in-memory; browser
    history and private-mode policy are deliberately managed separately.
    """

    downloads_changed = Signal()
    download_started = Signal(str, object)

    _TERMINAL_STATES = {"completed", "cancelled", "failed"}
    _reservation_lock = Lock()
    _reserved_paths: set[str] = set()
    _reservations_by_owner: dict[str, set[str]] = {}

    def __init__(self, profile_name: str, download_dir: str | os.PathLike[str] | None = None):
        super().__init__()
        from managers.storage import validate_profile_name

        self.profile_name = validate_profile_name(profile_name)
        self._download_dir_was_explicit = download_dir is not None
        if download_dir is None:
            download_dir = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation)
            if not download_dir:
                download_dir = str(Path.home() / "Downloads")
        self.download_dir = os.path.abspath(os.path.expanduser(os.fspath(download_dir)))
        self._downloads: list[dict[str, Any]] = []
        self._requests: dict[str, Any] = {}
        self._request_signal_slots: dict[str, list[tuple[Any, Any]]] = {}
        self._closed = False
        self._profile: Any = None
        self._attached_profile_download_path: str | None = None
        self._reservation_owner = uuid4().hex
        self._reserved_by_download: dict[str, str] = {}
        with self._reservation_lock:
            self._reservations_by_owner[self._reservation_owner] = set()
        weakref.finalize(self, DownloadManager._release_owner, self._reservation_owner)

    @staticmethod
    def _release_owner(owner: str) -> None:
        with DownloadManager._reservation_lock:
            paths = DownloadManager._reservations_by_owner.pop(owner, set())
            DownloadManager._reserved_paths.difference_update(paths)

    def _release_path_reservation(self, path_key: str) -> None:
        with self._reservation_lock:
            self._reserved_paths.discard(path_key)
            self._reservations_by_owner.get(self._reservation_owner, set()).discard(path_key)

    def attach_profile(self, profile) -> None:
        """Connect to the profile's Qt WebEngine ``downloadRequested`` signal."""
        if profile is self._profile:
            self._sync_download_dir_from_profile(profile)
            return
        if self._profile is not None:
            try:
                self._profile.downloadRequested.disconnect(self._on_download_requested)
            except (AttributeError, RuntimeError, TypeError):
                pass
        self._profile = profile
        self._sync_download_dir_from_profile(profile)
        profile.downloadRequested.connect(self._on_download_requested)

    def set_download_directory(self, download_dir: str | os.PathLike[str]) -> None:
        """Set the destination used for future requests from this profile."""
        if not isinstance(download_dir, (str, os.PathLike)) or not os.fspath(download_dir):
            raise ValueError("A download folder is required.")
        self.download_dir = os.path.abspath(os.path.expanduser(os.fspath(download_dir)))
        self._download_dir_was_explicit = True

    @staticmethod
    def _profile_download_path(profile) -> str | None:
        getter = getattr(profile, "downloadPath", None)
        if not callable(getter):
            return None
        try:
            value = getter()
        except (RuntimeError, TypeError):
            return None
        if not isinstance(value, (str, os.PathLike)) or not os.fspath(value):
            return None
        return os.path.abspath(os.path.expanduser(os.fspath(value)))

    def _sync_download_dir_from_profile(self, profile) -> None:
        profile_path = self._profile_download_path(profile)
        if profile_path is None:
            return
        previous_profile_path = self._attached_profile_download_path
        if (
            not self._download_dir_was_explicit
            or (
                previous_profile_path is not None
                and os.path.normcase(self.download_dir) == os.path.normcase(previous_profile_path)
            )
        ):
            self.download_dir = profile_path
        self._attached_profile_download_path = profile_path

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
        index = 0
        with self._reservation_lock:
            while True:
                candidate_name = file_name if index == 0 else f"{stem} ({index}){extension}"
                candidate = os.path.abspath(os.path.join(root, candidate_name))
                if os.path.commonpath((root, candidate)) != root:
                    raise ValueError("Download destination escapes the download directory")
                path_key = os.path.normcase(candidate)
                if not os.path.lexists(candidate) and path_key not in self._reserved_paths:
                    self._reserved_paths.add(path_key)
                    self._reservations_by_owner[self._reservation_owner].add(path_key)
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
        if self._closed:
            try:
                request.cancel()
            except (AttributeError, RuntimeError, TypeError):
                pass
            return
        download_id = uuid4().hex
        url = self._url_string(self._request_value(request, "url", ""))
        suggested = self._request_value(request, "suggestedFileName", "")
        if not suggested:
            suggested = self._request_value(request, "downloadFileName", "")
        safe_name = self._safe_file_name(suggested, url)
        record = None
        allocated_path_key = None
        try:
            safe_name, path = self._allocate_path(safe_name)
            allocated_path_key = os.path.normcase(path)
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
                "paused": False,
                "error": "",
            }
            source_page = self._request_value(request, "page", None)
            self._downloads.append(record)
            self._reserved_by_download[download_id] = allocated_path_key
            self._requests[download_id] = request
            for signal_name in (
                "receivedBytesChanged", "totalBytesChanged", "stateChanged", "isPausedChanged"
            ):
                signal = getattr(request, signal_name, None)
                if signal is not None and hasattr(signal, "connect"):
                    slot = lambda *args, current_id=download_id: self._refresh(current_id)
                    signal.connect(slot)
                    self._request_signal_slots.setdefault(download_id, []).append((signal, slot))
            # Publish the requested record before accepting it. Consumers can
            # then observe the same state sequence as the WebEngine request.
            self.downloads_changed.emit()
            request.accept()
            self._refresh(download_id)
            self.download_started.emit(download_id, source_page)
        except Exception as exc:
            try:
                request.cancel()
            except Exception:
                pass
            self._requests.pop(download_id, None)
            failed = next((item for item in self._downloads if item["id"] == download_id), None)
            if failed is None:
                if allocated_path_key is not None:
                    self._release_path_reservation(allocated_path_key)
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
        if self._closed:
            return
        request = self._requests.get(download_id)
        record = next((item for item in self._downloads if item["id"] == download_id), None)
        if request is None or record is None:
            return
        previous = (
            record["received_bytes"],
            record["total_bytes"],
            record["state"],
            record.get("paused", False),
            record["error"],
        )
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
        record["paused"] = bool(self._request_value(request, "isPaused", False))
        if record["state"] == "failed":
            record["error"] = str(self._request_value(request, "interruptReasonString", "") or "Download interrupted")
        elif record["state"] in {"downloading", "completed", "cancelled"}:
            record["error"] = ""
        current = (
            record["received_bytes"],
            record["total_bytes"],
            record["state"],
            record.get("paused", False),
            record["error"],
        )
        if record["state"] in self._TERMINAL_STATES:
            self._requests.pop(download_id, None)
            self._disconnect_request_signals(download_id)
        if current != previous:
            self.downloads_changed.emit()

    def _disconnect_request_signals(self, download_id: str) -> None:
        for signal, slot in self._request_signal_slots.pop(download_id, []):
            try:
                signal.disconnect(slot)
            except (AttributeError, RuntimeError, TypeError):
                pass

    def shutdown(self) -> None:
        """Cancel active downloads and detach Qt callbacks before profile teardown."""
        if self._closed:
            return
        self._closed = True
        profile = self._profile
        self._profile = None
        if profile is not None:
            try:
                profile.downloadRequested.disconnect(self._on_download_requested)
            except (AttributeError, RuntimeError, TypeError):
                pass

        for download_id, request in list(self._requests.items()):
            self._disconnect_request_signals(download_id)
            try:
                request.cancel()
            except (AttributeError, RuntimeError, TypeError):
                pass
            record = next((item for item in self._downloads if item["id"] == download_id), None)
            if record is not None and record["state"] not in self._TERMINAL_STATES:
                record["state"] = "cancelled"
                record["error"] = ""
        self._requests.clear()

    def get_downloads(self) -> list[dict]:
        return [deepcopy(item) for item in self._downloads]

    def cancel(self, download_id: str) -> bool:
        request = self._requests.get(download_id)
        record = next((item for item in self._downloads if item["id"] == download_id), None)
        if request is None or record is None or record["state"] in self._TERMINAL_STATES:
            return False
        try:
            request.cancel()
        except Exception as exc:
            if record["state"] not in self._TERMINAL_STATES:
                record["error"] = str(exc)
                record["state"] = "failed"
                self._requests.pop(download_id, None)
                self.downloads_changed.emit()
            return False
        if record["state"] not in self._TERMINAL_STATES:
            record["state"] = "cancelled"
            record["error"] = ""
            self._requests.pop(download_id, None)
            self.downloads_changed.emit()
        return record["state"] == "cancelled"

    def pause(self, download_id: str) -> bool:
        request = self._requests.get(download_id)
        record = next((item for item in self._downloads if item["id"] == download_id), None)
        if request is None or record is None or record["state"] in self._TERMINAL_STATES:
            return False
        try:
            request.pause()
            record["paused"] = True
        except (AttributeError, RuntimeError, TypeError):
            return False
        self.downloads_changed.emit()
        return True

    def resume(self, download_id: str) -> bool:
        request = self._requests.get(download_id)
        record = next((item for item in self._downloads if item["id"] == download_id), None)
        if request is None or record is None or record["state"] in self._TERMINAL_STATES:
            return False
        try:
            request.resume()
            record["paused"] = False
        except (AttributeError, RuntimeError, TypeError):
            return False
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

    def open_folder(self, download_id: str) -> bool:
        record = next((item for item in self._downloads if item["id"] == download_id), None)
        if record is None or not record["path"]:
            return False
        folder = os.path.dirname(os.path.abspath(record["path"]))
        if not os.path.isdir(folder):
            return False
        return bool(QDesktopServices.openUrl(QUrl.fromLocalFile(folder)))

    def remove_download(self, download_id: str) -> bool:
        record = next((item for item in self._downloads if item["id"] == download_id), None)
        if record is None or record["state"] not in self._TERMINAL_STATES:
            return False
        self._downloads = [item for item in self._downloads if item["id"] != download_id]
        self._requests.pop(download_id, None)
        self._disconnect_request_signals(download_id)
        path_key = self._reserved_by_download.pop(download_id, None)
        if path_key is not None:
            self._release_path_reservation(path_key)
        self.downloads_changed.emit()
        return True

    def delete_download_file(self, download_id: str) -> bool:
        """Delete a completed download only when its resolved path stays in the download folder."""
        record = next((item for item in self._downloads if item["id"] == download_id), None)
        if record is None or record["state"] != "completed" or not record["path"]:
            return False
        root = os.path.realpath(self.download_dir)
        target = os.path.realpath(record["path"])
        try:
            normalized_root = os.path.normcase(root)
            normalized_target = os.path.normcase(target)
            if os.path.commonpath((normalized_root, normalized_target)) != normalized_root:
                return False
            if not os.path.isfile(target):
                return False
            os.remove(record["path"])
        except (OSError, ValueError):
            return False
        return self.remove_download(download_id)

    def clear_finished(self) -> None:
        before = len(self._downloads)
        finished_ids = {
            item["id"] for item in self._downloads
            if item["state"] in self._TERMINAL_STATES
        }
        self._downloads = [item for item in self._downloads if item["state"] not in self._TERMINAL_STATES]
        for download_id in finished_ids:
            path_key = self._reserved_by_download.pop(download_id, None)
            if path_key is not None:
                self._release_path_reservation(path_key)
        kept_ids = {item["id"] for item in self._downloads}
        self._requests = {key: value for key, value in self._requests.items() if key in kept_ids}
        if len(self._downloads) != before:
            self.downloads_changed.emit()
