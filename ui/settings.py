from dataclasses import dataclass, asdict, field
import json
import os
from .profile_manager import Profile
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
    profiles_list: list = []    

    @classmethod
    def _hash_machine_id(cls, machine_id: str) -> str:
        """Return SHA256 hash of machine_id for safe storage."""
        return hashlib.sha256(machine_id.encode()).hexdigest()

    def save(self, profile_name: str):
        """Save settings for the current machine, excluding non-serializable fields."""
        data = {profile_name: asdict(self)}

        data[profile_name].pop("file_path", None)
        data[profile_name].pop("profile", None)

        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)

    def load(self, profile_name: str):
        """Load settings for the current machine safely."""
        if not os.path.exists(self.file_path):
            return

        with open(self.file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if profile_name not in data:
            return  # No settings stored for this machine

        for key, value in data[profile_name].items():
            if hasattr(self, key):
                setattr(self, key, value)

    @classmethod
    def save_profile_settings(cls, profiles_list: list[str]):
        hashed_machine_id = cls._hash_machine_id(Profile.get_machine_id())
        data = {}
        if os.path.exists("settings.json"):
            with open("settings.json", "r", encoding="utf-8") as f:
                data = json.load(f)

        data[hashed_machine_id] = {"profiles": profiles_list}

        with open("settings.json", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)

        return data
    
    def load_profile_settings(self):
        machine_id = Profile.get_machine_id()   
        if not os.path.exists(self.file_path):
            return
        hashed_machine_id = self._hash_machine_id(machine_id)
        with open(self.file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if hashed_machine_id not in data:
            self.save_profile_settings(["Guest", ])
            return  # No settings stored for this machine
        
        self.profiles_list = data[hashed_machine_id]["profiles"]
