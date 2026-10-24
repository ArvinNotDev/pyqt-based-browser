"""Backward-compatible, atomic persistence for browser settings."""

from dataclasses import asdict, dataclass, field, fields
import json
import logging
import os
from typing import Any

from PySide6.QtCore import QStandardPaths

from managers.profile_manager import Profile
from managers.storage import atomic_write_json, backup_corrupt_file, validate_profile_name
from app_paths import user_data_path


logger = logging.getLogger(__name__)
_META_KEY = "__pyqt_browser_meta_v1__"
_LEGACY_FLAT_KEY = "__pyqt_browser_legacy_flat_settings_v1__"


def default_download_directory() -> str:
    """Return the operating system's user Downloads location."""
    location = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.DownloadLocation
    )
    if not location:
        location = os.path.join(os.path.expanduser("~"), "Downloads")
    return os.path.abspath(os.path.expanduser(location))


@dataclass
class Settings:
    homepage: str = "arma://dashboard/"
    startup_page: str = "dashboard"
    new_tab_page: str = "dashboard"
    default_search_engine: str = "https://www.google.com/search?q="
    window_width: int = 1280
    window_height: int = 720
    dark_mode: bool = False
    save_history: bool = True
    save_cookies: bool = True
    private_mode: bool = False
    download_folder: str = field(default_factory=default_download_directory)
    show_dev_tools: bool = False
    hardware_acceleration: bool = True
    webgpu_enabled: bool = False
    proxy_panel_visible: bool = True
    site_compatibility_mode: bool = True
    tabs_in_title_bar: bool = False

    # Retained for callers that used these public attributes. Neither is
    # serialized as a per-profile setting.
    profile: Profile = field(default_factory=Profile)
    file_path: str = field(default_factory=lambda: user_data_path("settings.json"))
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
            with open(path, "r", encoding="utf-8-sig") as stream:
                raw = stream.read()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError as exc:
                data = Settings._recover_top_level_entries(raw)
                logger.warning("Could not fully read settings from %s: %s", path, exc)
                return data, True
            if not isinstance(data, dict):
                raise ValueError("Settings JSON root must be an object")
            return data, False
        except (OSError, UnicodeError, ValueError) as exc:
            logger.warning("Could not read settings from %s: %s", path, exc)
            return {}, True

    @staticmethod
    def _recover_top_level_entries(raw: str) -> dict[str, Any]:
        """Recover complete members preceding an error in a JSON object.

        JSON cannot recover arbitrary damaged values, but it can often retain
        other complete profile records around a malformed top-level entry.
        The original document is backed up before this recovered object is
        written by a caller.
        """
        start = len(raw) - len(raw.lstrip())
        if start >= len(raw) or raw[start] != "{":
            return {}

        cursor = start + 1
        recovered: dict[str, Any] = {}
        while cursor < len(raw):
            while cursor < len(raw) and raw[cursor].isspace():
                cursor += 1
            if cursor >= len(raw) or raw[cursor] == "}":
                break
            if raw[cursor] == ",":
                cursor += 1
                continue
            member_start = cursor
            curly_depth = 0
            bracket_depth = 0
            in_string = False
            escaped = False
            delimiter = ""
            while cursor < len(raw):
                char = raw[cursor]
                if in_string:
                    if escaped:
                        escaped = False
                    elif char == "\\":
                        escaped = True
                    elif char == '"':
                        in_string = False
                elif char == '"':
                    in_string = True
                elif char == "{":
                    curly_depth += 1
                elif char == "}":
                    if curly_depth == 0 and bracket_depth == 0:
                        delimiter = "}"
                        break
                    curly_depth = max(0, curly_depth - 1)
                elif char == "[":
                    bracket_depth += 1
                elif char == "]":
                    bracket_depth = max(0, bracket_depth - 1)
                elif char == "," and curly_depth == 0 and bracket_depth == 0:
                    delimiter = ","
                    break
                cursor += 1

            member = raw[member_start:cursor].strip()
            if member:
                try:
                    parsed_member = json.loads("{" + member + "}")
                except (json.JSONDecodeError, ValueError):
                    pass
                else:
                    if isinstance(parsed_member, dict):
                        recovered.update(parsed_member)

            if delimiter == "}":
                break
            if delimiter == ",":
                cursor += 1
                continue
            break
        return recovered

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
        string_fields.update({"startup_page", "new_tab_page"})
        boolean_fields = {
            "dark_mode", "save_history", "save_cookies", "private_mode",
            "show_dev_tools", "hardware_acceleration", "webgpu_enabled",
            "proxy_panel_visible", "site_compatibility_mode", "tabs_in_title_bar",
        }
        for name in string_fields:
            value = values.get(name)
            if isinstance(value, str):
                valid[name] = value
        if valid.get("startup_page") not in {"dashboard", "homepage"}:
            valid.pop("startup_page", None)
        if valid.get("new_tab_page") not in {"dashboard", "homepage"}:
            valid.pop("new_tab_page", None)
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
            "homepage": "arma://dashboard/",
            "startup_page": "dashboard",
            "new_tab_page": "dashboard",
            "default_search_engine": "https://www.google.com/search?q=",
            "window_width": 1280,
            "window_height": 720,
            "dark_mode": False,
            "save_history": True,
            "save_cookies": True,
            "private_mode": False,
            "download_folder": default_download_directory(),
            "show_dev_tools": False,
            "hardware_acceleration": True,
            "webgpu_enabled": False,
            "proxy_panel_visible": True,
            "site_compatibility_mode": True,
            "tabs_in_title_bar": False,
        }
        # Settings instances are reused while switching profiles. Reset every
        # profile field first so an absent/partial profile cannot inherit the
        # previous profile's values.
        for key, default in defaults.items():
            setattr(self, key, default)
        data, corrupt = self._read_document(self.file_path)
        if corrupt:
            # Keep the damaged source intact before atomically replacing it
            # with recovered entries (or an empty object when none survived).
            self._prepare_for_write(self.file_path, data, True)
        values = data.get(profile_name)
        if not isinstance(values, dict) and profile_name == "Guest":
            values = self._legacy_profile_settings(data)
        valid_values = self._valid_settings_values(values)
        # Older releases opened the homepage at startup and in new tabs. Move
        # only the known old homepage default to the dashboard. Preserve a
        # custom homepage as the startup choice for an unmigrated profile.
        if isinstance(values, dict) and "startup_page" not in values:
            if values.get("homepage") == "https://www.google.com":
                valid_values["homepage"] = "arma://dashboard/"
                valid_values["startup_page"] = "dashboard"
            elif isinstance(values.get("homepage"), str) and values["homepage"].strip():
                valid_values["startup_page"] = "homepage"
        if isinstance(values, dict) and values.get("download_folder") in {"./downloads", ".\\downloads"}:
            # Replace the old project-relative default while preserving any
            # explicitly selected custom destination.
            valid_values["download_folder"] = default_download_directory()
        for key, value in valid_values.items():
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

    @classmethod
    def remove_profile(
        cls,
        profile_name: str,
        remaining_profiles: list[str],
        file_path: str | None = None,
    ) -> dict[str, Any]:
        """Remove a profile's settings and persist the remaining profile list atomically."""
        name = cls._validate_profile_key(profile_name)
        if not isinstance(remaining_profiles, list):
            raise ValueError("Profiles must be supplied as a list")

        clean_profiles: list[str] = []
        seen: set[str] = set()
        for value in remaining_profiles:
            valid_name = cls._validate_profile_key(value)
            if valid_name == name:
                raise ValueError("The removed profile cannot remain in the profile list")
            if valid_name not in seen:
                clean_profiles.append(valid_name)
                seen.add(valid_name)
        if not clean_profiles:
            raise ValueError("At least one browser profile must remain")

        target_path = file_path or user_data_path("settings.json")
        data, corrupt = cls._read_document(target_path)
        if cls._is_flat_legacy_settings(data):
            data = {_LEGACY_FLAT_KEY: data}
        data.pop(name, None)
        metadata = data.get(_META_KEY)
        if not isinstance(metadata, dict):
            metadata = {}
        metadata["profiles"] = clean_profiles
        data[_META_KEY] = metadata
        cls._prepare_for_write(target_path, data, corrupt)
        return data

    def load_profile_settings(self) -> None:
        """Load profile names, including the previous machine-hash schema."""
        data, corrupt = self._read_document(self.file_path)
        if corrupt:
            self._prepare_for_write(self.file_path, data, True)
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
    def configure_webgpu(cls, enabled: bool) -> None:
        """Configure WebGPU without disabling normal GPU composition.

        QtWebEngine reads QTWEBENGINE_CHROMIUM_FLAGS before its first WebEngine
        initialization, so call this at startup. Runtime changes require a
        browser restart. Existing Chromium feature switches and unrelated flags
        are preserved.
        """
        flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "").split()
        passthrough: list[str] = []
        enabled_features: list[str] = []
        disabled_features: list[str] = []

        def feature_key(value: str) -> str:
            return value.split("<", 1)[0].strip().casefold()

        for flag in flags:
            if flag.startswith("--enable-features="):
                enabled_features.extend(
                    part.strip() for part in flag.split("=", 1)[1].split(",") if part.strip()
                )
            elif flag.startswith("--disable-features="):
                disabled_features.extend(
                    part.strip() for part in flag.split("=", 1)[1].split(",") if part.strip()
                )
            else:
                passthrough.append(flag)

        if enabled:
            disabled_features = [
                item for item in disabled_features if feature_key(item) != "webgpu"
            ]
        else:
            enabled_features = [
                item for item in enabled_features if feature_key(item) != "webgpu"
            ]
            if not any(feature_key(item) == "webgpu" for item in disabled_features):
                disabled_features.append("WebGPU")

        def unique_features(values: list[str]) -> list[str]:
            seen: set[str] = set()
            result: list[str] = []
            for item in values:
                key = feature_key(item)
                if key not in seen:
                    seen.add(key)
                    result.append(item)
            return result

        enabled_features = unique_features(enabled_features)
        disabled_features = unique_features(disabled_features)
        if enabled_features:
            passthrough.append("--enable-features=" + ",".join(enabled_features))
        if disabled_features:
            passthrough.append("--disable-features=" + ",".join(disabled_features))

        if passthrough:
            os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = " ".join(passthrough)
        else:
            os.environ.pop("QTWEBENGINE_CHROMIUM_FLAGS", None)

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
