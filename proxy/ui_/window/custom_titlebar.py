from PySide6.QtWidgets import (
    QLabel,
    QWidget,
    QHBoxLayout,
    QPushButton,
)
from PySide6.QtCore import Qt

class CustomTitleBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(40)
        self.parent_ = parent
        self.layout = QHBoxLayout(self)
        self.title = QLabel("T⭕®️🌐🅿️®️⭕❌Y")
        self.title.setStyleSheet("margin-left: 10px;")
        self.setLayout(self.layout)
        self.layout.addWidget(self.title)
        
   
    