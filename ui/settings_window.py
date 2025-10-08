from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit,
    QCheckBox, QPushButton
)
from .settings import Settings

class SettingsWindow(QDialog):
    def __init__(self, settings: Settings, selected_profile: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.resize(600, 400)

        self.settings = settings
        self.selected_profile = selected_profile
        
        main_layout = QVBoxLayout()
        form_layout = QFormLayout()

        self.homepage_input = QLineEdit(self.settings.homepage)
        form_layout.addRow("Homepage:", self.homepage_input)

        self.search_input = QLineEdit(self.settings.default_search_engine)
        form_layout.addRow("Search Engine:", self.search_input)

        self.dark_mode_checkbox = QCheckBox()
        self.dark_mode_checkbox.setChecked(self.settings.dark_mode)
        form_layout.addRow("Dark Mode:", self.dark_mode_checkbox)

        self.save_history_checkbox = QCheckBox()
        self.save_history_checkbox.setChecked(self.settings.save_history)
        form_layout.addRow("Save History:", self.save_history_checkbox)

        self.save_cookies_checkbox = QCheckBox()
        self.save_cookies_checkbox.setChecked(self.settings.save_cookies)
        form_layout.addRow("Save Cookies:", self.save_cookies_checkbox)

        main_layout.addLayout(form_layout)

        self.save_btn = QPushButton("Save")
        self.cancel_btn = QPushButton("Cancel")
        self.save_btn.clicked.connect(self.save_settings)
        self.cancel_btn.clicked.connect(self.close)

        main_layout.addWidget(self.save_btn)
        main_layout.addWidget(self.cancel_btn)

        self.setLayout(main_layout)

    def save_settings(self):
        """Apply changes and save settings for current profile"""
        self.settings.homepage = self.homepage_input.text().strip()
        self.settings.default_search_engine = self.search_input.text().strip()
        self.settings.dark_mode = self.dark_mode_checkbox.isChecked()
        self.settings.save_history = self.save_history_checkbox.isChecked()
        self.settings.save_cookies = self.save_cookies_checkbox.isChecked()

        self.settings.save(self.selected_profile)

        self.accept()
        if self.parent():
            self.parent().apply_theme()
