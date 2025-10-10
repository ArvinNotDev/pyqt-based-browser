from dataclasses import dataclass, asdict, field
import json
import os
from managers.profile_manager import Profile
import hashlib

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

    profile: Profile = field(default_factory=Profile)
    file_path: str = "settings.json"
    profiles_list: list = field(default_factory=list)


    @staticmethod
    def _hash_machine_id(machine_id: str) -> str:
        return hashlib.sha256(machine_id.encode()).hexdigest()


    def save(self, profile_name: str):
        data = {}
        if os.path.exists(self.file_path):
            with open(self.file_path, "r", encoding="utf-8") as f:
                try:
                    data = json.load(f)
                except json.JSONDecodeError:
                    data = {}

        profile_data = asdict(self)
        profile_data.pop("file_path", None)
        profile_data.pop("profile", None)
        profile_data.pop("profiles_list", None)

        data[profile_name] = profile_data

        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)



    def load(self, profile_name: str):
        if not os.path.exists(self.file_path):
            return

        with open(self.file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if profile_name not in data:
            return

        for key, value in data[profile_name].items():
            if hasattr(self, key):
                setattr(self, key, value)


    @classmethod
    def save_profiles(cls, profiles: list[str]):
        """Save list of profiles for this machine without overwriting other entries."""
        hashed_machine_id = cls._hash_machine_id(Profile.get_machine_id())
        data = {}

        if os.path.exists("settings.json"):
            with open("settings.json", "r", encoding="utf-8") as f:
                try:
                    data = json.load(f)
                except json.JSONDecodeError:
                    data = {}

        data[hashed_machine_id] = {"profiles": profiles}

        with open("settings.json", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)

        return data


    def load_profile_settings(self):
        """Load profiles list for this machine."""
        machine_id = Profile.get_machine_id()
        if not os.path.exists(self.file_path):
            return
        hashed_machine_id = self._hash_machine_id(machine_id)

        with open(self.file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if hashed_machine_id not in data:
            Settings.save_profiles(["Guest"])
            self.profiles_list = ["Guest"]
        else:
            self.profiles_list = data[hashed_machine_id].get("profiles", ["Guest"])
