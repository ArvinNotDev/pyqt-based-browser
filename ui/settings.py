from dataclasses import dataclass, asdict, field
import json
import os
from .profile_manager import Profile
import hashlib

@dataclass
class Settings:
    profile: Profile = field(default_factory=Profile)
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

    file_path: str = "settings.json"

    def _hash_machine_id(self, machine_id: str) -> str:
        """Return SHA256 hash of machine_id for safe storage."""
        return hashlib.sha256(machine_id.encode()).hexdigest()

    def save(self, machine_id: str):
        """Save settings for the current machine, excluding non-serializable fields."""
        hashed_machine_id = self._hash_machine_id(machine_id)
        data = {hashed_machine_id: asdict(self)}

        data[hashed_machine_id].pop("file_path", None)
        data[hashed_machine_id].pop("profile", None)

        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)

    def load(self, machine_id: str):
        """Load settings for the current machine safely."""
        if not os.path.exists(self.file_path):
            return

        hashed_machine_id = self._hash_machine_id(machine_id)
        with open(self.file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if hashed_machine_id not in data:
            return  # No settings stored for this machine

        for key, value in data[hashed_machine_id].items():
            if hasattr(self, key):
                setattr(self, key, value)
