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
        current_time = localtime()
        self.history[link] = {
            "date": f"{current_time.tm_year}/{current_time.tm_mon:02d}/{current_time.tm_mday:02d}",
            "time": f"{current_time.tm_hour:02d}:{current_time.tm_min:02d}:{current_time.tm_sec:02d}",
        }
        self.save()

    def delete(self, link=None, date=None, time=None):
        if link:
            self.history.pop(link, None)
        elif date:
            self.history = {
                k: v for k, v in self.history.items() if v.get("date") != date
            }
        elif time:
            self.history = {
                k: v for k, v in self.history.items() if v.get("time") != time
            }
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
        self.history.clear()
        self.save()
