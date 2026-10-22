"""Profile-scoped bookmark storage."""

from __future__ import annotations

import json
import logging
import os
from copy import deepcopy
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from managers.storage import atomic_write_json, backup_corrupt_file, profile_data_path


logger = logging.getLogger(__name__)


class BookmarksManager:
    def __init__(self, profile_name: str):
        self.profile_name = profile_name
        self.file_path = profile_data_path(profile_name, "bookmarks.json")
        self._bookmarks: list[dict] = []
        self._storage_format = "envelope"
        self._storage_document: dict = {"version": 1, "bookmarks": []}
        self._corrupt_source = False
        self.last_error: str | None = None
        self._load()

    @staticmethod
    def _validate_url(url: str) -> str:
        if not isinstance(url, str):
            raise ValueError("Bookmark URL must be a string")
        url = url.strip()
        if not url or any(ord(char) < 32 or char.isspace() for char in url):
            raise ValueError("Bookmark URL must be non-empty and contain no whitespace")
        try:
            parts = urlsplit(url)
            hostname = parts.hostname
            _port = parts.port
        except ValueError as exc:
            raise ValueError(f"Invalid bookmark URL: {exc}") from exc
        if parts.scheme.lower() not in {"http", "https"} or not hostname:
            raise ValueError("Bookmark URL must be an absolute HTTP or HTTPS URL")
        if parts.username is not None or parts.password is not None:
            raise ValueError("Bookmark URLs cannot contain embedded credentials")
        try:
            hostname.encode("idna")
        except UnicodeError as exc:
            raise ValueError("Bookmark URL contains an invalid hostname") from exc
        return url

    @staticmethod
    def _duplicate_key(url: str) -> str:
        parts = urlsplit(url)
        scheme = parts.scheme.lower()
        host = (parts.hostname or "").encode("idna").decode("ascii").lower()
        port = parts.port
        if port == (443 if scheme == "https" else 80):
            port = None
        if ":" in host:
            host = f"[{host}]"
        netloc = host if port is None else f"{host}:{port}"
        return urlunsplit((scheme, netloc, parts.path or "/", parts.query, parts.fragment))

    @classmethod
    def _normalize_record(cls, record) -> dict | None:
        if not isinstance(record, dict):
            return None
        bookmark_id = record.get("id")
        title = record.get("title")
        created_at = record.get("created_at")
        try:
            url = cls._validate_url(record.get("url"))
        except ValueError:
            return None
        if not isinstance(bookmark_id, str) or not bookmark_id.strip():
            return None
        if not isinstance(title, str) or not isinstance(created_at, str):
            return None
        normalized = dict(record)
        normalized.update({"id": bookmark_id, "title": title, "url": url, "created_at": created_at})
        return normalized

    def _load(self) -> None:
        if not os.path.exists(self.file_path):
            return
        try:
            with open(self.file_path, "r", encoding="utf-8") as stream:
                document = json.load(stream)
            records = []
            if isinstance(document, list):
                self._storage_format = "list"
                records = document
            elif isinstance(document, dict):
                self._storage_document = dict(document)
                if isinstance(document.get("bookmarks"), list):
                    self._storage_format = "envelope-list"
                    records = document["bookmarks"]
                elif isinstance(document.get("bookmarks"), dict):
                    self._storage_format = "envelope-map"
                    records = list(document["bookmarks"].values())
                elif document and all(isinstance(value, dict) for value in document.values()):
                    self._storage_format = "map"
                    records = list(document.values())
                elif not document:
                    self._storage_format = "envelope"
                else:
                    # Keep unknown keys when a future or hand-edited document
                    # is updated; valid records remain independently readable.
                    self._storage_format = "envelope"
                    records = document.get("items", []) if isinstance(document.get("items"), list) else []
                    self._storage_document = {**document, "version": document.get("version", 1)}
            else:
                raise ValueError("Bookmarks JSON root must be an object or list")

            seen_ids: set[str] = set()
            for record in records:
                normalized = self._normalize_record(record)
                if normalized is None or normalized["id"] in seen_ids:
                    continue
                self._bookmarks.append(normalized)
                seen_ids.add(normalized["id"])
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            self._bookmarks = []
            self._corrupt_source = True
            self.last_error = str(exc)
            logger.warning("Could not load bookmarks from %s: %s", self.file_path, exc)

    def list_bookmarks(self) -> list[dict]:
        return [deepcopy(bookmark) for bookmark in self._bookmarks]

    def _save(self) -> None:
        if self._corrupt_source and os.path.exists(self.file_path):
            backup_corrupt_file(self.file_path)
        records = [dict(bookmark) for bookmark in self._bookmarks]
        if self._storage_format == "list":
            document = records
        elif self._storage_format == "map":
            document = {bookmark["id"]: bookmark for bookmark in records}
        elif self._storage_format == "envelope-list":
            document = {**self._storage_document, "bookmarks": records}
        elif self._storage_format == "envelope-map":
            document = {**self._storage_document, "bookmarks": {b["id"]: b for b in records}}
        else:
            document = {**self._storage_document, "version": 1, "bookmarks": records}
        atomic_write_json(self.file_path, document)
        self.last_error = None
        self._corrupt_source = False

    def add_bookmark(self, title: str, url: str) -> dict:
        if not isinstance(title, str):
            raise ValueError("Bookmark title must be a string")
        url = self._validate_url(url)
        duplicate_key = self._duplicate_key(url)
        for bookmark in self._bookmarks:
            if self._duplicate_key(bookmark["url"]) == duplicate_key:
                return deepcopy(bookmark)
        bookmark = {
            "id": uuid4().hex,
            "title": title.strip() or url,
            "url": url,
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        self._bookmarks.append(bookmark)
        self._save()
        return deepcopy(bookmark)

    def remove_bookmark(self, bookmark_id: str) -> bool:
        if not isinstance(bookmark_id, str):
            return False
        remaining = [bookmark for bookmark in self._bookmarks if bookmark["id"] != bookmark_id]
        if len(remaining) == len(self._bookmarks):
            return False
        self._bookmarks = remaining
        self._save()
        return True

    def get_bookmark_for_url(self, url: str) -> dict | None:
        """Return the saved record matching a URL, including normalized variants."""
        try:
            duplicate_key = self._duplicate_key(self._validate_url(url))
        except ValueError:
            return None
        for bookmark in self._bookmarks:
            if self._duplicate_key(bookmark["url"]) == duplicate_key:
                return deepcopy(bookmark)
        return None

    def update_bookmark(self, bookmark_id: str, title: str, url: str) -> dict:
        """Update a saved record while preserving its id and creation time."""
        if not isinstance(bookmark_id, str) or not bookmark_id:
            raise ValueError("Bookmark id must be a non-empty string")
        if not isinstance(title, str):
            raise ValueError("Bookmark title must be a string")
        url = self._validate_url(url)
        duplicate_key = self._duplicate_key(url)
        target = next((item for item in self._bookmarks if item["id"] == bookmark_id), None)
        if target is None:
            raise ValueError("Bookmark no longer exists")
        if any(
            item["id"] != bookmark_id and self._duplicate_key(item["url"]) == duplicate_key
            for item in self._bookmarks
        ):
            raise ValueError("Another bookmark already uses this address")
        target["title"] = title.strip() or url
        target["url"] = url
        self._save()
        return deepcopy(target)

    def is_bookmarked(self, url: str) -> bool:
        try:
            key = self._duplicate_key(self._validate_url(url))
        except ValueError:
            return False
        return any(self._duplicate_key(bookmark["url"]) == key for bookmark in self._bookmarks)
