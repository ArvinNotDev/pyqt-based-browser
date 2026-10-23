"""Validated, profile-scoped storage for the browser start page."""

from __future__ import annotations

import logging
import os
import uuid
from copy import deepcopy
from pathlib import Path
from urllib.parse import urlsplit

from managers.storage import atomic_write_json, backup_corrupt_file, profile_data_path


logger = logging.getLogger(__name__)

PRESETS = {
    "aurora": {"title": "Aurora", "background": "linear-gradient(135deg, #182f4e, #536a89 48%, #d7a7b3)"},
    "ocean": {"title": "Blue hour", "background": "linear-gradient(135deg, #091c38, #175d78 54%, #8fb8b4)"},
    "dune": {"title": "Dune", "background": "linear-gradient(135deg, #514c52, #a97e70 54%, #e6c99d)"},
    "forest": {"title": "Forest", "background": "linear-gradient(135deg, #102b2b, #35675d 54%, #b5bca0)"},
}

DEFAULT_SHORTCUTS = [
    {"title": "Google", "url": "https://www.google.com/"},
    {"title": "Wikipedia", "url": "https://www.wikipedia.org/"},
    {"title": "YouTube", "url": "https://www.youtube.com/"},
]

DEFAULT_WIDGET_ORDER = ["bookmarks", "recent", "closed", "notes", "focus"]
WIDGET_SIZES = {"compact", "standard", "wide"}
DEFAULT_WIDGET_SIZES = {name: "standard" for name in DEFAULT_WIDGET_ORDER}

DEFAULTS = {
    "wallpaper": "aurora",
    "overlay": 20,
    "blur": 0,
    "glass": 58,
    "accent": "#8db8ff",
    "clock_24h": True,
    "show_seconds": False,
    "animations": True,
    "density": "comfortable",
    "widgets": {"bookmarks": True, "recent": True, "closed": True, "notes": True, "focus": True},
    "widget_order": DEFAULT_WIDGET_ORDER,
    "widget_sizes": DEFAULT_WIDGET_SIZES,
    "shortcuts": DEFAULT_SHORTCUTS,
    "notes": "",
    "quick_notes": [],
    "focus_minutes": 25,
    "break_minutes": 5,
}


def _valid_url(value: object) -> bool:
    if not isinstance(value, str) or not value or len(value) > 2048:
        return False
    if any(char.isspace() or ord(char) < 32 for char in value):
        return False
    try:
        parts = urlsplit(value)
        _ = parts.port
        hostname = parts.hostname
        if hostname:
            hostname.encode("idna")
    except ValueError:
        return False
    except UnicodeError:
        return False
    return (
        parts.scheme.lower() in {"http", "https"}
        and bool(parts.hostname)
        and parts.username is None
        and parts.password is None
    )


def normalize_shortcuts(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return deepcopy(DEFAULT_SHORTCUTS)
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in value[:30]:
        if not isinstance(item, dict):
            continue
        url = item.get("url")
        title = item.get("title")
        if not _valid_url(url):
            continue
        canonical = url.rstrip("/").casefold()
        if canonical in seen:
            continue
        seen.add(canonical)
        clean_title = title.strip()[:80] if isinstance(title, str) else ""
        result.append({"title": clean_title or url, "url": url.strip()})
    return result


class DashboardManager:
    """Own dashboard preferences and imported wallpapers for one profile."""

    def __init__(self, profile_name: str, base_dir: str | os.PathLike[str] = "profile_data"):
        self.profile_name = profile_name
        self.base_dir = Path(base_dir)
        self.file_path = profile_data_path(profile_name, "dashboard.json", base_dir=base_dir)
        self.wallpaper_dir = Path(profile_data_path(profile_name, "dashboard", "wallpapers", base_dir=base_dir))
        self._corrupt_source = False
        self.data = deepcopy(DEFAULTS)
        self.load()

    @staticmethod
    def _normalize(data: object) -> dict:
        result = deepcopy(DEFAULTS)
        if not isinstance(data, dict):
            return result
        wallpaper = data.get("wallpaper")
        if isinstance(wallpaper, str) and (wallpaper in PRESETS or wallpaper.startswith("file:")):
            result["wallpaper"] = wallpaper
        for key, minimum, maximum in (("overlay", 0, 70), ("blur", 0, 12), ("glass", 20, 90)):
            value = data.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                result[key] = max(minimum, min(maximum, value))
        accent = data.get("accent")
        if isinstance(accent, str) and len(accent) == 7 and accent.startswith("#"):
            try:
                int(accent[1:], 16)
            except ValueError:
                pass
            else:
                result["accent"] = accent.lower()
        for key in ("clock_24h", "show_seconds", "animations"):
            if isinstance(data.get(key), bool):
                result[key] = data[key]
        density = data.get("density")
        if isinstance(density, str) and density in {"comfortable", "compact"}:
            result["density"] = density
        widgets = data.get("widgets")
        if isinstance(widgets, dict):
            result["widgets"].update({key: value for key, value in widgets.items() if key in result["widgets"] and isinstance(value, bool)})
        widget_order = data.get("widget_order")
        if isinstance(widget_order, list):
            seen_widgets = set()
            normalized_order = []
            for name in widget_order:
                if name in DEFAULT_WIDGET_ORDER and name not in seen_widgets:
                    normalized_order.append(name)
                    seen_widgets.add(name)
            result["widget_order"] = normalized_order + [
                name for name in DEFAULT_WIDGET_ORDER if name not in seen_widgets
            ]
        widget_sizes = data.get("widget_sizes")
        if isinstance(widget_sizes, dict):
            result["widget_sizes"].update({
                name: size for name, size in widget_sizes.items()
                if name in result["widget_sizes"] and size in WIDGET_SIZES
            })
        result["shortcuts"] = normalize_shortcuts(data.get("shortcuts", DEFAULT_SHORTCUTS))
        notes = data.get("notes")
        if isinstance(notes, str):
            result["notes"] = notes[:10000]
        quick_notes = data.get("quick_notes")
        if isinstance(quick_notes, list):
            result["quick_notes"] = [
                note[:5000] for note in quick_notes[:10] if isinstance(note, str)
            ]
        for key, minimum, maximum in (("focus_minutes", 1, 180), ("break_minutes", 1, 60)):
            value = data.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                result[key] = max(minimum, min(maximum, value))
        return result

    def load(self) -> None:
        try:
            with open(self.file_path, "r", encoding="utf-8") as stream:
                import json

                self.data = self._normalize(json.load(stream))
        except FileNotFoundError:
            self.data = deepcopy(DEFAULTS)
        except (OSError, UnicodeError, TypeError, ValueError) as exc:
            logger.warning("Could not load dashboard settings for %s: %s", self.profile_name, exc)
            self.data = deepcopy(DEFAULTS)
            self._corrupt_source = True

        wallpaper = self.data["wallpaper"]
        if wallpaper.startswith("file:"):
            path = self._wallpaper_path(wallpaper)
            if path is None or not path.is_file():
                logger.warning("Dashboard wallpaper is missing for profile %s", self.profile_name)
                self.data["wallpaper"] = "aurora"

    def save(self) -> None:
        if self._corrupt_source and os.path.exists(self.file_path):
            backup_corrupt_file(self.file_path)
        atomic_write_json(self.file_path, self._normalize(self.data))
        self._corrupt_source = False

    def export(self) -> dict:
        result = deepcopy(self.data)
        wallpaper = result["wallpaper"]
        result["wallpaper_url"] = (
            f"arma://dashboard/wallpaper/{wallpaper[5:]}" if wallpaper.startswith("file:") else ""
        )
        result["presets"] = PRESETS
        return result

    def _wallpaper_path(self, key: str) -> Path | None:
        if not isinstance(key, str) or not key.startswith("file:"):
            return None
        filename = key[5:]
        if not filename or Path(filename).name != filename or filename in {".", ".."}:
            return None
        path = self.wallpaper_dir / filename
        try:
            if os.path.commonpath((str(self.wallpaper_dir.resolve()), str(path.resolve()))) != str(self.wallpaper_dir.resolve()):
                return None
        except (OSError, ValueError):
            return None
        return path

    def wallpaper_data_url(self, key: str | None = None) -> str:
        import base64

        path = self._wallpaper_path(key or self.data["wallpaper"])
        if path is None:
            return ""
        try:
            raw = path.read_bytes()
        except OSError:
            return ""
        if not raw or len(raw) > 2_000_000:
            return ""
        return "data:image/jpeg;base64," + base64.b64encode(raw).decode("ascii")

    def read_wallpaper(self, filename: str) -> bytes | None:
        path = self._wallpaper_path(f"file:{filename}")
        if path is None:
            return None
        try:
            if path.stat().st_size > 2_000_000:
                return None
            content = path.read_bytes()
        except OSError:
            return None
        return content or None

    def import_wallpaper(self, source: str, *, activate: bool = True) -> str:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QImageReader

        source_path = Path(source)
        if source_path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
            raise ValueError("Choose a JPG, PNG, or WEBP image.")
        if not source_path.is_file() or source_path.stat().st_size > 25_000_000:
            raise ValueError("The selected image is missing or larger than 25 MB.")
        reader = QImageReader(str(source_path))
        reader.setAutoTransform(True)
        dimensions = reader.size()
        if dimensions.isValid() and dimensions.width() * dimensions.height() > 40_000_000:
            raise ValueError("The selected image dimensions are too large.")
        image = reader.read()
        if image.isNull():
            raise ValueError("The selected image could not be decoded.")
        if image.width() * image.height() > 40_000_000:
            raise ValueError("The selected image dimensions are too large.")
        self.wallpaper_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{uuid.uuid4().hex}.jpg"
        target = self.wallpaper_dir / filename
        for width, height, quality in (
            (2560, 1600, 84), (1920, 1200, 80), (1600, 1000, 76),
            (1280, 800, 70), (960, 600, 62),
        ):
            resized = image.scaled(
                width, height, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            if not resized.save(str(target), "JPG", quality):
                raise OSError("The selected image could not be saved.")
            if target.stat().st_size <= 2_000_000:
                break
        else:
            try:
                target.unlink()
            except OSError:
                pass
            raise ValueError("The selected image could not be compressed to a suitable size.")
        key = f"file:{filename}"
        if activate:
            self.data["wallpaper"] = key
            self.save()
        return key

    def set_wallpaper(self, key: str) -> None:
        if not isinstance(key, str):
            raise ValueError("That wallpaper is unavailable.")
        if key in PRESETS:
            self.data["wallpaper"] = key
        elif key.startswith("file:") and self._wallpaper_path(key) is not None and self._wallpaper_path(key).is_file():
            self.data["wallpaper"] = key
        else:
            raise ValueError("That wallpaper is unavailable.")
        self.save()

    def cycle_wallpaper(self) -> str:
        available = list(PRESETS)
        try:
            available.extend(f"file:{path.name}" for path in self.wallpaper_dir.glob("*.jpg") if path.is_file())
        except OSError:
            pass
        current = self.data["wallpaper"]
        try:
            index = available.index(current)
        except ValueError:
            index = -1
        self.set_wallpaper(available[(index + 1) % len(available)])
        return self.data["wallpaper"]

    def set_shortcuts(self, shortcuts: object) -> None:
        if not isinstance(shortcuts, list):
            raise ValueError("Shortcuts must be a list.")
        normalized = normalize_shortcuts(shortcuts)
        if len(normalized) != len(shortcuts):
            raise ValueError("One or more shortcuts have an invalid or duplicate address.")
        self.data["shortcuts"] = normalized
        self.save()

    def update(self, values: dict) -> None:
        if not isinstance(values, dict):
            raise ValueError("Dashboard preferences must be an object.")
        numeric_fields = {"overlay", "blur", "glass", "focus_minutes", "break_minutes"}
        boolean_fields = {"clock_24h", "show_seconds", "animations"}
        for key, value in values.items():
            if key in numeric_fields and (not isinstance(value, int) or isinstance(value, bool)):
                raise ValueError(f"{key} must be a number.")
            if key in boolean_fields and not isinstance(value, bool):
                raise ValueError(f"{key} must be true or false.")
            if key == "density" and (
                not isinstance(value, str) or value not in {"comfortable", "compact"}
            ):
                raise ValueError("Density must be comfortable or compact.")
            if key == "accent":
                if not isinstance(value, str) or len(value) != 7 or not value.startswith("#"):
                    raise ValueError("Accent must be a six-digit hex color.")
                try:
                    int(value[1:], 16)
                except ValueError as exc:
                    raise ValueError("Accent must be a six-digit hex color.") from exc
            if key == "widgets":
                if not isinstance(value, dict) or any(
                    name in DEFAULTS["widgets"] and not isinstance(enabled, bool)
                    for name, enabled in value.items()
                ):
                    raise ValueError("Widget preferences must be boolean values.")
            if key == "widget_order":
                if (
                    not isinstance(value, list)
                    or len(value) > len(DEFAULT_WIDGET_ORDER)
                    or any(not isinstance(name, str) or name not in DEFAULT_WIDGET_ORDER for name in value)
                    or len(set(value)) != len(value)
                ):
                    raise ValueError("Widget order contains an invalid or duplicate widget.")
            if key == "widget_sizes":
                if not isinstance(value, dict) or any(
                    not isinstance(name, str)
                    or name not in DEFAULT_WIDGET_SIZES
                    or not isinstance(size, str)
                    or size not in WIDGET_SIZES
                    for name, size in value.items()
                ):
                    raise ValueError("Widget sizes must map known widgets to compact, standard, or wide.")
            if key == "notes" and not isinstance(value, str):
                raise ValueError("Notes must be text.")
            if key == "quick_notes" and (
                not isinstance(value, list)
                or len(value) > 10
                or any(not isinstance(note, str) for note in value)
            ):
                raise ValueError("You can save up to 10 text notes.")
            if key == "wallpaper":
                if not isinstance(value, str):
                    raise ValueError("That wallpaper is unavailable.")
                if value not in PRESETS:
                    path = self._wallpaper_path(value)
                    if path is None or not path.is_file():
                        raise ValueError("That wallpaper is unavailable.")
        merged = {**self.data, **values}
        self.data = self._normalize(merged)
        self.save()

    def reset(self) -> None:
        self.data = deepcopy(DEFAULTS)
        self.save()
