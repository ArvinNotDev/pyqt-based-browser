import os
import json
from time import localtime


class History:
    def __init__(self, username: str):
        self.username = username
        self.history = {}
        self.file_path = os.path.join("profile_data", username, "history.json")
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
        self.load()

    def add(self, link: str):
        """Add a new visit record for a link."""
        current_time = localtime()
        entry = {
            "date": f"{current_time.tm_year}/{current_time.tm_mon:02d}/{current_time.tm_mday:02d}",
            "time": f"{current_time.tm_hour:02d}:{current_time.tm_min:02d}:{current_time.tm_sec:02d}",
        }

        if link not in self.history:
            self.history[link] = []

        self.history[link].append(entry)
        self.save()

    def delete(self, link=None, date=None, time=None):
        """Delete by link or filter visits by date/time."""
        if link:
            self.history.pop(link, None)
        elif date or time:
            for link_key, visits in list(self.history.items()):
                filtered = [
                    v for v in visits
                    if (date and v.get("date") != date) or (time and v.get("time") != time)
                ]
                if filtered:
                    self.history[link_key] = filtered
                else:
                    self.history.pop(link_key, None)
        self.save()

    def save(self):
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(self.history, f, indent=4)

    def load(self):
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    self.history = json.load(f)
            except json.JSONDecodeError:
                self.history = {}
        else:
            self.history = {}

    def clear(self):
        """Clear all history records."""
        self.history.clear()
        self.save()
