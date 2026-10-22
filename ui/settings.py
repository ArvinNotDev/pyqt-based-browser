"""Backward-compatible, atomic persistence for browser settings."""

from dataclasses import asdict, dataclass, field, fields
import json
import logging
import os
from typing import Any

from managers.profile_manager import Profile
from managers.storage import atomic_write_json, backup_corrupt_file, validate_profile_name


logger = logging.getLogger(__name__)
_META_KEY = "__pyqt_browser_meta_v1__"
_LEGACY_FLAT_KEY = "__pyqt_browser_legacy_flat_settings_v1__"


@dataclass
class Settings:
    homepage: str = "https://www.google.com"
    default_search_engine: str = "https://www.google.com/search?q="
    window_width: int = 1280
    window_height: int = 720
    dark_mode: bool = False
    save_history: bool = True
    save_cookies: bool = True
    private_mode: bool = False
    download_folder: str = "./downloads"
    show_dev_tools: bool = False
    hardware_acceleration: bool = True

    # Retained for callers that used these public attributes. Neither is
    # serialized as a per-profile setting.
    profile: Profile = field(default_factory=Profile)
    file_path: str = "settings.json"
    profiles_list: list[str] = field(default_factory=list)

    @staticmethod
    def _hash_machine_id(machine_id: str) -> str:
        """Legacy helper retained for source compatibility; new writes do not use it."""
        import hashlib

        return hashlib.sha256(machine_id.encode("utf-8")).hexdigest()

    @staticmethod
    def _validate_profile_key(profile_name: str) -> str:
        profile_name = validate_profile_name(profile_name)
        if profile_name in {_META_KEY, _LEGACY_FLAT_KEY}:
            raise ValueError("Profile name is reserved for settings metadata")
        return profile_name

    @staticmethod
    def _read_document(path: str) -> tuple[dict[str, Any], bool]:
        if not os.path.exists(path):
            return {}, False
        try:
            with open(path, "r", encoding="utf-8") as stream:
                data = json.load(stream)
            if not isinstance(data, dict):
                raise ValueError("Settings JSON root must be an object")
            return data, False
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            logger.warning("Could not read settings from %s: %s", path, exc)
            return {}, True

    @staticmethod
    def _prepare_for_write(path: str, data: dict[str, Any], corrupt: bool) -> None:
        if corrupt and os.path.exists(path):
            backup_corrupt_file(path)
        atomic_write_json(path, data)

    @staticmethod
    def _is_flat_legacy_settings(data: dict[str, Any]) -> bool:
        setting_names = {item.name for item in fields(Settings)} - {
            "profile", "file_path", "profiles_list"
        }
        return any(name in data and not isinstance(data.get(name), dict) for name in setting_names)

    @staticmethod
    def _legacy_profile_settings(data: dict[str, Any]) -> dict[str, Any] | None:
        legacy = data.get(_LEGACY_FLAT_KEY)
        if isinstance(legacy, dict):
            return legacy
        if Settings._is_flat_legacy_settings(data):
            return data
        return None

    @staticmethod
    def _valid_settings_values(values: Any) -> dict[str, Any]:
        if not isinstance(values, dict):
            return {}
        valid: dict[str, Any] = {}
        string_fields = {"homepage", "default_search_engine", "download_folder"}
        boolean_fields = {
            "dark_mode", "save_history", "save_cookies", "private_mode",
            "show_dev_tools", "hardware_acceleration",
        }
        for name in string_fields:
            value = values.get(name)
            if isinstance(value, str):
                valid[name] = value
        for name in boolean_fields:
            value = values.get(name)
            if isinstance(value, bool):
                valid[name] = value
        for name in ("window_width", "window_height"):
            value = values.get(name)
            if isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 16384:
                valid[name] = value
        return valid

    def save(self, profile_name: str) -> dict[str, Any]:
        """Save this profile while preserving all other valid settings entries."""
        profile_name = self._validate_profile_key(profile_name)
        data, corrupt = self._read_document(self.file_path)
        if self._is_flat_legacy_settings(data):
            # Preserve the original flat document as a named migration record.
            data = {_LEGACY_FLAT_KEY: data}

        profile_data = asdict(self)
        profile_data.pop("file_path", None)
        profile_data.pop("profile", None)
        profile_data.pop("profiles_list", None)
        data[profile_name] = profile_data
        self._prepare_for_write(self.file_path, data, corrupt)
        return data

    def load(self, profile_name: str) -> None:
        """Load recognized values for a profile; missing or bad fields keep defaults."""
        profile_name = self._validate_profile_key(profile_name)
        defaults = {
            "homepage": "https://www.google.com",
            "default_search_engine": "https://www.google.com/search?q=",
            "window_width": 1280,
            "window_height": 720,
            "dark_mode": False,
            "save_history": True,
            "save_cookies": True,
            "private_mode": False,
            "download_folder": "./downloads",
            "show_dev_tools": False,
            "hardware_acceleration": True,
        }
        # Settings instances are reused while switching profiles. Reset every
        # profile field first so an absent/partial profile cannot inherit the
        # previous profile's values.
        for key, default in defaults.items():
            setattr(self, key, default)
        data, _corrupt = self._read_document(self.file_path)
        values = data.get(profile_name)
        if not isinstance(values, dict) and profile_name == "Guest":
            values = self._legacy_profile_settings(data)
        for key, value in self._valid_settings_values(values).items():
            setattr(self, key, value)

    @classmethod
    def save_profiles(cls, profiles: list[str], file_path: str = "settings.json") -> dict[str, Any]:
        """Persist profile names in portable metadata and retain legacy entries.

        Older versions stored this list under a hash of a machine identifier.
        That record is still read during migration and is not removed.
        """
        if not isinstance(profiles, list):
            raise ValueError("Profiles must be supplied as a list")
        clean_profiles: list[str] = []
        seen: set[str] = set()
        for profile_name in profiles:
            name = cls._validate_profile_key(profile_name)
            if name not in seen:
                clean_profiles.append(name)
                seen.add(name)

        data, corrupt = cls._read_document(file_path)
        if cls._is_flat_legacy_settings(data):
            data = {_LEGACY_FLAT_KEY: data}
        metadata = data.get(_META_KEY)
        if not isinstance(metadata, dict):
            if _META_KEY in data:
                data[_META_KEY + "_legacy"] = data[_META_KEY]
            metadata = {}
        metadata["profiles"] = clean_profiles
        data[_META_KEY] = metadata
        cls._prepare_for_write(file_path, data, corrupt)
        return data

    def load_profile_settings(self) -> None:
        """Load profile names, including the previous machine-hash schema."""
        data, _corrupt = self._read_document(self.file_path)
        metadata = data.get(_META_KEY)
        profiles = metadata.get("profiles") if isinstance(metadata, dict) else None
        if not isinstance(profiles, list):
            # Old releases kept {"profiles": [...]} at a hashed machine key.
            for value in data.values():
                if isinstance(value, dict) and isinstance(value.get("profiles"), list):
                    profiles = value["profiles"]
                    break
        if not isinstance(profiles, list):
            legacy_flat = self._legacy_profile_settings(data)
            if isinstance(legacy_flat, dict):
                profiles = legacy_flat.get("profiles")

        clean_profiles: list[str] = []
        if isinstance(profiles, list):
            for name in profiles:
                try:
                    valid_name = self._validate_profile_key(name)
                except ValueError:
                    logger.warning("Ignoring an invalid stored profile name")
                    continue
                if valid_name not in clean_profiles:
                    clean_profiles.append(valid_name)
        self.profiles_list = clean_profiles or ["Guest"]

        # Migrate only when a legacy list was found. The old machine-hash
        # entry remains untouched for downgrade compatibility.
        if profiles is not None and not (isinstance(metadata, dict) and metadata.get("profiles") == self.profiles_list):
            self.save_profiles(self.profiles_list, self.file_path)

    @classmethod
    def disable_hardware_acceleration(cls) -> None:
        """Set startup flags used by older callers to request software rendering."""
        flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "").split()
        if "--disable-gpu" not in flags:
            flags.append("--disable-gpu")
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = " ".join(flags)
        os.environ["QT_OPENGL"] = "software"

    @classmethod
    def configure_hardware_acceleration(cls, enabled: bool) -> None:
        """Update startup environment without dropping unrelated Chromium flags."""
        flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "").split()
        flags = [flag for flag in flags if flag != "--disable-gpu"]
        if not enabled and "--disable-gpu" not in flags:
            flags.append("--disable-gpu")
        if flags:
            os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = " ".join(flags)
        else:
            os.environ.pop("QTWEBENGINE_CHROMIUM_FLAGS", None)
        if enabled:
            if os.environ.get("QT_OPENGL") == "software":
                os.environ.pop("QT_OPENGL", None)
        else:
            os.environ["QT_OPENGL"] = "software"
