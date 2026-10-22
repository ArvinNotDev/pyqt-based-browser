from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QListWidget, QListWidgetItem, QPushButton,
    QHBoxLayout, QLineEdit, QMessageBox, QLabel, QInputDialog
)
from PySide6.QtCore import Qt
from managers.history_manager import History


class HistoryWindow(QDialog):
    def __init__(self, selected_profile: str, history: History, parent=None):
        super().__init__(parent)
        self.history = history
        self.selected_profile = selected_profile

        self.setWindowTitle(f"History - {selected_profile}")
        self.resize(700, 500)

        main_layout = QVBoxLayout()
        self.setLayout(main_layout)

        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search history (URL, date, or time)...")
        self.search_input.textChanged.connect(self.filter_history)
        search_layout.addWidget(QLabel("🔍"))
        search_layout.addWidget(self.search_input)
        main_layout.addLayout(search_layout)

        self.list_widget = QListWidget()
        main_layout.addWidget(self.list_widget)

        btn_layout = QHBoxLayout()

        self.delete_selected_btn = QPushButton("Delete Selected")
        self.delete_selected_btn.clicked.connect(self.delete_selected)
        btn_layout.addWidget(self.delete_selected_btn)

        self.delete_by_date_btn = QPushButton("Delete by Date/Time")
        self.delete_by_date_btn.clicked.connect(self.delete_by_date_time)
        btn_layout.addWidget(self.delete_by_date_btn)

        self.clear_btn = QPushButton("Clear All History")
        self.clear_btn.clicked.connect(self.clear_all)
        btn_layout.addWidget(self.clear_btn)

        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.close)
        btn_layout.addWidget(self.close_btn)

        main_layout.addLayout(btn_layout)

        self.load_history()

    def load_history(self):
        """Load history items into the list."""
        self.list_widget.clear()

        if not self.history.history:
            self.list_widget.addItem("No history found.")
            return

        for link, visits in self.history.history.items():
            self._add_link_item(link)
            for index, visit in enumerate(visits):
                self._add_visit_item(link, visit, index)
            self.list_widget.addItem("")

    def _add_link_item(self, link):
        item = QListWidgetItem(f"🔗 {link}")
        item.setData(Qt.UserRole, {"kind": "link", "link": link})
        self.list_widget.addItem(item)

    def _add_visit_item(self, link, visit, index):
        date = str(visit.get("date", "Unknown date"))
        time = str(visit.get("time", "Unknown time"))
        item = QListWidgetItem(f"   • {date} {time}")
        item.setData(Qt.UserRole, {"kind": "visit", "link": link, "date": date, "time": time, "index": index})
        self.list_widget.addItem(item)

    def filter_history(self):
        """Filter visible items by search query."""
        query = self.search_input.text().casefold().strip()
        self.list_widget.clear()

        if not query:
            self.load_history()
            return

        found = False
        for link, visits in self.history.history.items():
            link_matches = query in link.casefold()
            matching_visits = [
                (index, visit) for index, visit in enumerate(visits)
                if link_matches
                or query in str(visit.get("date", "")).casefold()
                or query in str(visit.get("time", "")).casefold()
            ]
            if link_matches or matching_visits:
                self._add_link_item(link)
                for index, visit in matching_visits:
                    self._add_visit_item(link, visit, index)
                self.list_widget.addItem("")
                found = True

        if not found:
            self.list_widget.addItem("No results found.")

    def delete_selected(self):
        """Delete selected history entry (either a whole link or a specific datetime)."""
        selected_item = self.list_widget.currentItem()
        if not selected_item:
            QMessageBox.warning(self, "No Selection", "Select an item to delete.")
            return

        metadata = selected_item.data(Qt.UserRole)
        if not isinstance(metadata, dict):
            QMessageBox.warning(self, "No Selection", "Select a history URL or visit entry.")
            return
        if metadata.get("kind") == "link":
            link = metadata.get("link")
            confirm = QMessageBox.question(
                self, "Confirm Delete", f"Delete ALL history for:\n{link}?"
            )
            if confirm == QMessageBox.Yes:
                self.history.delete(link=link)
                self.load_history()
        elif metadata.get("kind") == "visit":
            link = metadata.get("link")
            date = metadata.get("date")
            time = metadata.get("time")
            confirm = QMessageBox.question(
                self,
                "Confirm Delete",
                f"Delete visit at {date} {time} for:\n{link}?",
            )
            if confirm == QMessageBox.Yes:
                self.history.delete_visit(link, date, time, metadata.get("index"))
                self.filter_history()

    def delete_by_date_time(self):
        """Delete all visits on a given date or time."""
        text, ok = QInputDialog.getText(
            self, "Delete by Date/Time",
            "Enter an exact date (YYYY/MM/DD) or time (HH:MM):"
        )
        if not ok or not text.strip():
            return

        text = text.strip()
        confirm = QMessageBox.question(
            self, "Confirm Delete",
            f"Delete all history entries with the exact date or time '{text}'?"
        )
        if confirm != QMessageBox.Yes:
            return

        if "/" in text:
            self.history.delete(date=text)
        else:
            self.history.delete(time=text)
        self.load_history()


    def clear_all(self):
        """Delete all history entries."""
        confirm = QMessageBox.question(
            self, "Confirm Clear", "Are you sure you want to clear ALL history?"
        )
        if confirm == QMessageBox.Yes:
            self.history.clear()
            self.load_history()
