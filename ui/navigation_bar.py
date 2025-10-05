from PySide6.QtWidgets import QToolBar, QLineEdit, QSizePolicy
from PySide6.QtGui import QAction
from PySide6.QtCore import QSize, Signal

class NavigationBar(QToolBar):
    url_submitted = Signal(str)
    home_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__("Navigation", parent)
        self.setMovable(False)
        self.setIconSize(QSize(24, 24))

        # === Toolbar buttons using emojis ===
        self.back_btn = QAction("←", self)
        self.forward_btn = QAction("→", self)
        self.reload_btn = QAction("⟳", self)
        self.home_btn = QAction("🏠", self)
        self.settings_btn = QAction("⚙️", self)

        # Add buttons to toolbar
        for btn in [self.back_btn, self.forward_btn, self.reload_btn, self.home_btn, self.settings_btn]:
            self.addAction(btn)

        self.addSeparator()

        # === URL bar ===
        self.url_bar = QLineEdit()
        self.url_bar.setPlaceholderText("Enter URL or search...")
        self.url_bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.addWidget(self.url_bar)

        # === Connections ===
        self.url_bar.returnPressed.connect(self._on_url_entered)
        self.home_btn.triggered.connect(self.home_clicked.emit)

    def _on_url_entered(self):
        url = self.url_bar.text().strip()
        if url:
            self.url_submitted.emit(url)

    def apply_theme(self, toolbar_color: str, urlbar_color: str, urlbar_text_color: str):
        """Set the toolbar and URL bar colors dynamically"""
        self.setStyleSheet(f"""
            QToolBar {{
                background-color: {toolbar_color};
            }}
            QLineEdit {{
                background-color: {urlbar_color};
                color: {urlbar_text_color};
                border-radius: 8px;
                border: 1px solid #555;
                padding: 5px;
            }}
        """)
