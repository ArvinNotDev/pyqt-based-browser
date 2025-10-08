from PySide6.QtWidgets import QToolBar, QLineEdit, QSizePolicy
from PySide6.QtGui import QAction, QIcon, QFont
from PySide6.QtCore import QSize, Signal


class NavigationBar(QToolBar):
    url_submitted = Signal(str)
    home_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__("Navigation", parent)
        self.setMovable(False)

        self.setIconSize(QSize(24, 24))
        self.setFixedHeight(60)

        icon_path = "assets/icons/"

        self.back_btn = QAction(QIcon(f"{icon_path}back.png"), "Back", self)
        self.forward_btn = QAction(QIcon(f"{icon_path}forward.png"), "Forward", self)
        self.reload_btn = QAction(QIcon(f"{icon_path}reload.png"), "Reload", self)
        self.home_btn = QAction(QIcon(f"{icon_path}home.png"), "Home", self)
        self.settings_btn = QAction(QIcon(f"{icon_path}settings.png"), "Settings", self)

        for btn in [self.back_btn, self.forward_btn, self.reload_btn, self.home_btn, self.settings_btn]:
            self.addAction(btn)

        self.addSeparator()

        self.url_bar = QLineEdit()
        self.url_bar.setPlaceholderText("Enter URL or search...")
        self.url_bar.setFont(QFont("Segoe UI", 12))
        self.url_bar.setMinimumHeight(38)
        self.url_bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.addWidget(self.url_bar)

        self.url_bar.returnPressed.connect(self._on_url_entered)
        self.home_btn.triggered.connect(self.home_clicked.emit)


    def _on_url_entered(self):
        url = self.url_bar.text().strip()
        if url:
            self.url_submitted.emit(url)
