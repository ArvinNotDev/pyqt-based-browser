from dataclasses import dataclass, asdict
import json
import os

@dataclass
class Settings:
    app_name: str = "R-Browser"
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

    def save(self):
        """Save settings to JSON file"""
        data = asdict(self)

        data.pop("file_path", None)
        with open(self.file_path, "w") as f:
            json.dump(data, f, indent=4)

    def load(self):
        """Load settings from JSON file"""
        if not os.path.exists(self.file_path):
            return
        with open(self.file_path, "r") as f:
            data = json.load(f)
        for key, value in data.items():
            if hasattr(self, key):
                setattr(self, key, value)
