from PySide6.QtWidgets import QDialog, QVBoxLayout, QListWidget, QPushButton
from PySide6.QtCore import Qt
from managers.history_manager import History


class HistoryWindow(QDialog):
    def __init__(self, selected_profile: str, history: History, parent=None):
        super().__init__(parent)
        self.history = history
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
        """Load history data from the History manager"""
        self.list_widget.clear()

        if not self.history.history:
            self.list_widget.addItem("No history found.")
            return

        for link, visits in self.history.history.items():
            self.list_widget.addItem(f"🔗 {link}")

            if isinstance(visits, dict):
                date = visits.get("date", "Unknown date")
                time = visits.get("time", "Unknown time")
                self.list_widget.addItem(f"   • {date} {time}")

            elif isinstance(visits, list):
                for visit in visits:
                    if isinstance(visit, dict):
                        date = visit.get("date", "Unknown date")
                        time = visit.get("time", "Unknown time")
                        self.list_widget.addItem(f"   • {date} {time}")
                    else:
                        self.list_widget.addItem(f"   • {visit}")

            else:
                self.list_widget.addItem(f"   • {visits}")

            self.list_widget.addItem("")
