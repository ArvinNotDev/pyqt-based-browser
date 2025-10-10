from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QListWidget, QPushButton
)
from PySide6.QtCore import Qt
import os
import sqlite3
from datetime import datetime, timedelta

class HistoryWindow(QDialog):
    def __init__(self, selected_profile: str, parent=None):
        super().__init__(parent)
        self.selected_profile = selected_profile
        self.setWindowTitle(f"History - {selected_profile}")
        self.resize(600, 400)

        main_layout = QVBoxLayout()
        self.setLayout(main_layout)

        self.list_widget = QListWidget()
        main_layout.addWidget(self.list_widget)

        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.close)
        main_layout.addWidget(self.close_btn, alignment=Qt.AlignRight)

        self.load_history()

    def load_history(self):
        profile_path = os.path.join(os.getcwd(), "profile_data", self.selected_profile, "storage")
        history_db = os.path.join(profile_path, "History")

        if not os.path.exists(history_db):
            return

        try:
            conn = sqlite3.connect(history_db)
            cursor = conn.cursor()
            cursor.execute("SELECT url, title, last_visit_time FROM urls ORDER BY last_visit_time DESC")
            rows = cursor.fetchall()
            for url, title, last_visit_time in rows:
                visit_time = datetime(1601, 1, 1) + timedelta(microseconds=last_visit_time)
                display_text = f"{visit_time.strftime('%Y-%m-%d %H:%M:%S')} - {title} ({url})"
                self.list_widget.addItem(display_text)
            conn.close()
        except Exception as e:
            self.list_widget.addItem(f"Error loading history: {e}")
