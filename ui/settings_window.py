from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit,
    QCheckBox, QPushButton, QHBoxLayout, QLabel, QFrame, QMessageBox
)
from PySide6.QtCore import Qt
from .settings import Settings
from .history_window import HistoryWindow
from managers.history_manager import History
import copy
import sys
import os

class SettingsWindow(QDialog):
    def __init__(self, settings: Settings, selected_profile: str, history: History, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.resize(650, 560)

        self.settings = settings
        self.selected_profile = selected_profile
        self.history = history
        self.restart_required = False 

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        title = QLabel("Browser Settings")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 20px; font-weight: bold;")
        main_layout.addWidget(title)

        form_layout = QFormLayout()
        form_layout.setLabelAlignment(Qt.AlignLeft)
        form_layout.setFormAlignment(Qt.AlignTop)
        form_layout.setHorizontalSpacing(20)
        form_layout.setVerticalSpacing(12)

        self.homepage_input = QLineEdit(self.settings.homepage)
        self.homepage_input.setPlaceholderText("Enter homepage URL")
        form_layout.addRow("Homepage:", self.homepage_input)

        self.search_input = QLineEdit(self.settings.default_search_engine)
        self.search_input.setPlaceholderText("Enter default search engine URL")
        form_layout.addRow("Search Engine:", self.search_input)

        self.dark_mode_checkbox = QCheckBox("Enable dark mode")
        self.dark_mode_checkbox.setChecked(self.settings.dark_mode)
        form_layout.addRow("", self.dark_mode_checkbox)

        self.save_history_checkbox = QCheckBox("Save browsing history")
        self.save_history_checkbox.setChecked(self.settings.save_history)
        form_layout.addRow("", self.save_history_checkbox)

        self.save_cookies_checkbox = QCheckBox("Persist cookies between sessions")
        self.save_cookies_checkbox.setChecked(self.settings.save_cookies)
        form_layout.addRow("", self.save_cookies_checkbox)

        self.private_mode_checkbox = QCheckBox("Private mode")
        self.private_mode_checkbox.setChecked(self.settings.private_mode)
        form_layout.addRow("", self.private_mode_checkbox)

        self.hw_accel_checkbox = QCheckBox("Enable hardware acceleration (restart required)")
        self.hw_accel_checkbox.setChecked(self.settings.hardware_acceleration)
        form_layout.addRow("", self.hw_accel_checkbox)

        integration_note = QLabel(
            "Cookie persistence, history saving, and private mode are stored preferences; "
            "browser integration must apply them for browsing behavior to change."
        )
        integration_note.setWordWrap(True)
        integration_note.setStyleSheet("color: #666; font-size: 11px;")
        form_layout.addRow("", integration_note)

        self.hw_accel_note = QLabel(
            "The acceleration preference is applied when this dialog restarts the browser. "
            "Startup integration is needed for later launches."
        )
        self.hw_accel_note.setWordWrap(True)
        self.hw_accel_note.setStyleSheet("color: #666; font-size: 11px;")
        form_layout.addRow("", self.hw_accel_note)

        main_layout.addLayout(form_layout)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        main_layout.addWidget(line)

        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(10)

        self.history_btn = QPushButton("View History")
        self.history_btn.setStyleSheet("background-color: #4CAF50; color: white; padding: 8px 20px; border-radius: 5px;")
        self.history_btn.clicked.connect(self.open_history)

        self.save_btn = QPushButton("Save")
        self.save_btn.setStyleSheet("background-color: #2196F3; color: white; padding: 8px 20px; border-radius: 5px;")
        self.save_btn.clicked.connect(self.save_settings)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setStyleSheet("background-color: #f44336; color: white; padding: 8px 20px; border-radius: 5px;")
        self.cancel_btn.clicked.connect(self.reject)

        buttons_layout.addWidget(self.history_btn)
        buttons_layout.addStretch()
        buttons_layout.addWidget(self.save_btn)
        buttons_layout.addWidget(self.cancel_btn)

        main_layout.addLayout(buttons_layout)

        self.setLayout(main_layout)
        self.setStyleSheet("QLineEdit {padding: 6px; border-radius: 5px; border: 1px solid #ccc;}")

    def open_history(self):
        dialog = HistoryWindow(self.selected_profile, History(self.selected_profile), self)
        dialog.exec()

    def save_settings(self):
        homepage = self.homepage_input.text().strip()
        search_engine = self.search_input.text().strip()
        if not homepage or not search_engine:
            QMessageBox.warning(self, "Invalid Settings", "Homepage and search engine cannot be empty.")
            return

        old_hardware_acceleration = self.settings.hardware_acceleration
        candidate = copy.copy(self.settings)
        candidate.homepage = homepage
        candidate.default_search_engine = search_engine
        candidate.dark_mode = self.dark_mode_checkbox.isChecked()
        candidate.save_history = self.save_history_checkbox.isChecked()
        candidate.save_cookies = self.save_cookies_checkbox.isChecked()
        candidate.private_mode = self.private_mode_checkbox.isChecked()
        candidate.hardware_acceleration = self.hw_accel_checkbox.isChecked()

        try:
            candidate.save(self.selected_profile)
        except (OSError, ValueError, TypeError) as exc:
            QMessageBox.critical(self, "Could Not Save Settings", str(exc))
            return

        # Apply the in-memory settings only after the atomic persistence succeeds.
        for name in (
            "homepage", "default_search_engine", "dark_mode", "save_history",
            "save_cookies", "private_mode", "hardware_acceleration",
        ):
            setattr(self.settings, name, getattr(candidate, name))

        if old_hardware_acceleration != candidate.hardware_acceleration:
            Settings.configure_hardware_acceleration(candidate.hardware_acceleration)
            self.restart_required = True

        self.accept()
        if self.parent() and hasattr(self.parent(), "apply_theme"):
            self.parent().apply_theme()

        if self.restart_required:
            result = QMessageBox.question(
                self,
                "Restart Required",
                "The hardware acceleration preference requires restarting the browser. Restart now?",
                QMessageBox.Yes | QMessageBox.No
            )
            if result == QMessageBox.Yes:
                self.restart_browser()

    def restart_browser(self):
        """Restart the current Python application."""
        python = sys.executable
        os.execl(python, python, *sys.argv)

