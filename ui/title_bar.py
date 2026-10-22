"""Custom, draggable title bar for the frameless browser window."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QToolButton, QWidget


class CustomTitleBar(QWidget):
    def __init__(self, window):
        super().__init__(window)
        self.host = window
        self.setObjectName("customTitleBar")
        self.setFixedHeight(38)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 7, 0)
        layout.setSpacing(8)

        self.logo = QLabel("A", self)
        self.logo.setObjectName("titleBarLogo")
        self.logo.setAlignment(Qt.AlignCenter)
        self.logo.setFixedSize(25, 25)
        self.logo.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout.addWidget(self.logo)

        self.title = QLabel("ARMA Browser", self)
        self.title.setObjectName("titleBarTitle")
        self.title.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout.addWidget(self.title)
        layout.addStretch(1)

        self.minimize_button = self._button("—", "Minimize", "windowMinimizeButton")
        self.maximize_button = self._button("□", "Maximize", "windowMaximizeButton")
        self.close_button = self._button("×", "Close", "windowCloseButton")
        layout.addWidget(self.minimize_button)
        layout.addWidget(self.maximize_button)
        layout.addWidget(self.close_button)

        self.minimize_button.clicked.connect(window.showMinimized)
        self.maximize_button.clicked.connect(self._toggle_maximized)
        self.close_button.clicked.connect(window.close)
        self.sync_maximize_button()

    def _button(self, text, tooltip, object_name):
        button = QToolButton(self)
        button.setObjectName(object_name)
        button.setText(text)
        button.setToolTip(tooltip)
        button.setAccessibleName(tooltip)
        button.setFixedSize(34, 27)
        button.setFocusPolicy(Qt.NoFocus)
        return button

    def _toggle_maximized(self):
        if self.host.isMaximized():
            self.host.showNormal()
        else:
            self.host.showMaximized()
        self.sync_maximize_button()

    def sync_maximize_button(self):
        maximized = self.host.isMaximized()
        self.maximize_button.setText("❐" if maximized else "□")
        self.maximize_button.setToolTip("Restore" if maximized else "Maximize")
        self.maximize_button.setAccessibleName(self.maximize_button.toolTip())

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            handle = self.host.windowHandle()
            if handle is not None and handle.startSystemMove():
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._toggle_maximized()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class ResizeHandle(QWidget):
    """Thin frameless-window edge that delegates resizing to the window system."""

    def __init__(self, host, edges, cursor):
        super().__init__(host)
        self.host = host
        self.edges = edges
        self.setCursor(cursor)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFocusPolicy(Qt.NoFocus)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            handle = self.host.windowHandle()
            if handle is not None and handle.startSystemResize(self.edges):
                event.accept()
                return
        super().mousePressEvent(event)
