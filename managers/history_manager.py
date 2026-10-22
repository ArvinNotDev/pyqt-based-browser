"""Profile-scoped browsing history with tolerant legacy loading."""

from __future__ import annotations

import json
import logging
import os
from time import localtime
from typing import Any

from managers.storage import atomic_write_json, backup_corrupt_file, profile_data_path


logger = logging.getLogger(__name__)


class History:
    def __init__(self, username: str, enabled: bool = True, base_dir: str = "profile_data"):
        self.username = username
        self.enabled = bool(enabled)
        self.history: dict[str, list[dict[str, Any]]] = {}
        self.file_path = profile_data_path(username, "history.json", base_dir=base_dir)
        self.last_error: str | None = None
        self._corrupt_source = False
        self.load()

    @staticmethod
    def _normalize_visits(value: Any) -> list[dict[str, Any]]:
        if isinstance(value, dict):
            candidates = [value]
        elif isinstance(value, list):
            candidates = value
        else:
            return []
        normalized: list[dict[str, Any]] = []
        for visit in candidates:
            if not isinstance(visit, dict):
                continue
            item = dict(visit)
            for key in ("date", "time"):
                field = item.get(key)
                if field is not None and not isinstance(field, str):
                    item[key] = str(field)
            normalized.append(item)
        return normalized

    @classmethod
    def _normalize_document(cls, data: Any) -> dict[str, list[dict[str, Any]]]:
        if isinstance(data, dict) and set(data) == {"history"} and isinstance(data.get("history"), (dict, list)):
            data = data["history"]
        normalized: dict[str, list[dict[str, Any]]] = {}
        if isinstance(data, dict):
            for link, visits in data.items():
                if not isinstance(link, str):
                    continue
                cleaned = cls._normalize_visits(visits)
                if cleaned:
                    normalized[link] = cleaned
        elif isinstance(data, list):
            # Also accept older exported lists of {url/link, date, time} rows.
            for row in data:
                if not isinstance(row, dict):
                    continue
                link = row.get("url", row.get("link"))
                if not isinstance(link, str):
                    continue
                visit = {key: value for key, value in row.items() if key not in {"url", "link"}}
                normalized.setdefault(link, []).extend(cls._normalize_visits(visit))
        else:
            raise ValueError("History JSON root must be an object or legacy row list")
        return normalized

    def add(self, link: str) -> bool:
        """Record a visit unless history is disabled for this manager."""
        if not self.enabled:
            return False
        if not isinstance(link, str) or not link.strip():
            raise ValueError("History link must be a non-empty string")
        current_time = localtime()
        entry = {
            "date": f"{current_time.tm_year}/{current_time.tm_mon:02d}/{current_time.tm_mday:02d}",
            "time": f"{current_time.tm_hour:02d}:{current_time.tm_min:02d}:{current_time.tm_sec:02d}",
        }
        self.history.setdefault(link, []).append(entry)
        self.save()
        return True

    def delete(self, link: str | None = None, date: str | None = None, time: str | None = None) -> None:
        """Delete a whole URL, or visits matching every supplied date/time filter."""
        if link is not None and date is None and time is None:
            self.history.pop(link, None)
        elif date is not None or time is not None:
            links = [link] if link is not None else list(self.history)
            for link_key in links:
                visits = self.history.get(link_key)
                if not isinstance(visits, list):
                    continue
                remaining = [
                    visit for visit in visits
                    if not (
                        (date is None or visit.get("date") == date)
                        and (time is None or visit.get("time") == time)
                    )
                ]
                if remaining:
                    self.history[link_key] = remaining
                else:
                    self.history.pop(link_key, None)
        self.save()

    def delete_visit(self, link: str, date: str, time: str, index: int | None = None) -> None:
        """Delete one visit, including legacy records without timestamps."""
        visits = self.history.get(link, [])
        if index is not None and isinstance(visits, list) and 0 <= index < len(visits):
            visits.pop(index)
            if not visits:
                self.history.pop(link, None)
            self.save()
            return
        self.delete(link=link, date=date, time=time)

    def save(self) -> None:
        if self._corrupt_source and os.path.exists(self.file_path):
            backup_corrupt_file(self.file_path)
        atomic_write_json(self.file_path, self.history)
        self._corrupt_source = False
        self.last_error = None

    def load(self) -> None:
        if not os.path.exists(self.file_path):
            self.history = {}
            return
        try:
            with open(self.file_path, "r", encoding="utf-8") as stream:
                data = json.load(stream)
            self.history = self._normalize_document(data)
            self._corrupt_source = False
            self.last_error = None
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            self.history = {}
            self._corrupt_source = True
            self.last_error = str(exc)
            logger.warning("Could not load history from %s: %s", self.file_path, exc)

    def clear(self) -> None:
        """Clear all history records in a single atomic write."""
        self.history.clear()
        self.save()
