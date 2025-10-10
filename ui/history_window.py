from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QListWidget, QPushButton,
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
            self.list_widget.addItem(f"🔗 {link}")

            if isinstance(visits, list):
                for visit in visits:
                    date = visit.get("date", "Unknown date")
                    time = visit.get("time", "Unknown time")
                    self.list_widget.addItem(f"   • {date} {time}")
            elif isinstance(visits, dict):
                date = visits.get("date", "Unknown date")
                time = visits.get("time", "Unknown time")
                self.list_widget.addItem(f"   • {date} {time}")
            else:
                self.list_widget.addItem(f"   • {visits}")

            self.list_widget.addItem("")

    def filter_history(self):
        """Filter visible items by search query."""
        query = self.search_input.text().lower().strip()
        self.list_widget.clear()

        if not query:
            self.load_history()
            return

        found = False
        for link, visits in self.history.history.items():
            if query in link.lower():
                self.list_widget.addItem(f"🔗 {link}")
                found = True
            if isinstance(visits, list):
                for visit in visits:
                    date, time = visit.get("date", ""), visit.get("time", "")
                    if query in date.lower() or query in time.lower():
                        self.list_widget.addItem(f"   • {date} {time}  -  {link}")
                        found = True

        if not found:
            self.list_widget.addItem("No results found.")

    def delete_selected(self):
        """Delete selected history entry (either a whole link or a specific datetime)."""
        selected_item = self.list_widget.currentItem()
        if not selected_item:
            QMessageBox.warning(self, "No Selection", "Select an item to delete.")
            return

        text = selected_item.text().strip()
        if text.startswith("🔗 "):
            link = text[2:].strip()
            confirm = QMessageBox.question(
                self, "Confirm Delete", f"Delete ALL history for:\n{link}?"
            )
            if confirm == QMessageBox.Yes:
                self.history.delete(link=link)
                self.load_history()
        elif text.startswith("•") or text.startswith("• "):
            # Try to identify link above
            index = self.list_widget.row(selected_item)
            link = None
            for i in range(index - 1, -1, -1):
                item = self.list_widget.item(i)
                if item and item.text().startswith("🔗 "):
                    link = item.text()[2:].strip()
                    break
            if not link:
                QMessageBox.warning(self, "Error", "Could not determine link for this entry.")
                return

            date_time = text.replace("•", "").strip().split()
            if len(date_time) >= 2:
                date, time = date_time[0], date_time[1]
                confirm = QMessageBox.question(
                    self,
                    "Confirm Delete",
                    f"Delete visit at {date} {time} for:\n{link}?",
                )
                if confirm == QMessageBox.Yes:
                    visits = self.history.history.get(link, [])
                    self.history.history[link] = [
                        v for v in visits if not (v["date"] == date and v["time"] == time)
                    ]
                    if not self.history.history[link]:
                        del self.history.history[link]
                    self.history.save()
                    self.load_history()

    def delete_by_date_time(self):
        """Delete all visits on a given date or time."""
        text, ok = QInputDialog.getText(
            self, "Delete by Date/Time",
            "Enter date (YYYY/MM/DD) or time (HH:MM):"
        )
        if not ok or not text.strip():
            return

        text = text.strip()
        confirm = QMessageBox.question(
            self, "Confirm Delete",
            f"Delete all history entries with date/time containing '{text}'?"
        )
        if confirm != QMessageBox.Yes:
            return

        for link in list(self.history.history.keys()):
            visits = self.history.history[link]

            if isinstance(visits, dict):
                visits = [visits]
            elif isinstance(visits, str):
                continue
            elif not isinstance(visits, list):
                continue

            cleaned = []
            for v in visits:
                if not isinstance(v, dict):
                    continue
                if text in v.get("date", "") or text in v.get("time", ""):
                    continue
                cleaned.append(v)

            if cleaned:
                self.history.history[link] = cleaned
            else:
                del self.history.history[link]

        self.history.save()
        self.load_history()


    def clear_all(self):
        """Delete all history entries."""
        confirm = QMessageBox.question(
            self, "Confirm Clear", "Are you sure you want to clear ALL history?"
        )
        if confirm == QMessageBox.Yes:
            self.history.clear()
            self.load_history()
