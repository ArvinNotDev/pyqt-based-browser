"""Regression tests for preserving malformed settings documents safely."""

import json
import tempfile
import unittest
from pathlib import Path

from ui.settings import Settings


class SettingsRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.settings_path = Path(self.temp_dir.name) / "settings.json"

    def tearDown(self):
        self.temp_dir.cleanup()

    def _backups(self):
        return list(self.settings_path.parent.glob("settings.json.corrupt-*.bak"))

    def test_load_recovers_complete_profiles_and_preserves_original(self):
        original = (
            '{"Broken": {oops}, '
            '"Work":{"homepage":"https://work.test","private_mode":true}, '
            '"Incomplete":'
        )
        self.settings_path.write_text(original, encoding="utf-8")

        guest = Settings(file_path=str(self.settings_path))
        guest.load("Guest")

        self.assertEqual(guest.homepage, "https://www.google.com")
        self.assertFalse(guest.private_mode)
        backups = self._backups()
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(encoding="utf-8"), original)

        recovered = json.loads(self.settings_path.read_text(encoding="utf-8"))
        self.assertIn("Work", recovered)
        self.assertNotIn("Incomplete", recovered)
        work = Settings(file_path=str(self.settings_path))
        work.load("Work")
        self.assertEqual(work.homepage, "https://work.test")
        self.assertTrue(work.private_mode)

        guest.homepage = "https://guest.test"
        guest.save("Guest")
        reopened = Settings(file_path=str(self.settings_path))
        reopened.load("Guest")
        self.assertEqual(reopened.homepage, "https://guest.test")
        self.assertEqual(len(self._backups()), 1)

    def test_save_recovers_unrelated_profiles_and_persists_new_values(self):
        original = (
            '{"Broken":[1,], '
            '"Other":{"homepage":"https://other.test","save_history":false}, '
            '"Truncated":[1,'
        )
        self.settings_path.write_text(original, encoding="utf-8")

        current = Settings(file_path=str(self.settings_path))
        current.homepage = "https://new.test"
        current.save("Guest")

        backups = self._backups()
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(encoding="utf-8"), original)
        document = json.loads(self.settings_path.read_text(encoding="utf-8"))
        self.assertEqual(document["Other"]["homepage"], "https://other.test")
        self.assertFalse(document["Other"]["save_history"])
        self.assertEqual(document["Guest"]["homepage"], "https://new.test")

        reopened = Settings(file_path=str(self.settings_path))
        reopened.load("Guest")
        self.assertEqual(reopened.homepage, "https://new.test")
        reopened.load("Other")
        self.assertEqual(reopened.homepage, "https://other.test")
        self.assertFalse(reopened.save_history)
        self.assertEqual(len(self._backups()), 1)

    def test_irrecoverable_document_loads_defaults_after_backup(self):
        original = "[this is not a settings object"
        self.settings_path.write_text(original, encoding="utf-8")
        settings = Settings(file_path=str(self.settings_path))
        settings.homepage = "https://stale.test"

        settings.load("Guest")

        self.assertEqual(settings.homepage, "https://www.google.com")
        self.assertTrue(settings.save_history)
        self.assertEqual(len(self._backups()), 1)
        self.assertEqual(self._backups()[0].read_text(encoding="utf-8"), original)
        self.assertEqual(json.loads(self.settings_path.read_text(encoding="utf-8")), {})

    def test_loading_healthy_document_does_not_rewrite_it(self):
        original = '{\n  "Guest": {"homepage": "https://healthy.test"}\n}\n'
        self.settings_path.write_text(original, encoding="utf-8")
        settings = Settings(file_path=str(self.settings_path))

        settings.load("Guest")

        self.assertEqual(settings.homepage, "https://healthy.test")
        self.assertEqual(self.settings_path.read_text(encoding="utf-8"), original)
        self.assertEqual(self._backups(), [])


if __name__ == "__main__":
    unittest.main()
