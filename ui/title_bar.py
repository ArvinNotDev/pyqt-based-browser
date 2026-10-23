"""Custom, draggable title bar for the frameless browser window."""

import ctypes
import sys
from ctypes import wintypes

from PySide6.QtCore import QPoint, QRect, QSize, Qt, QTimer
from PySide6.QtWidgets import QHBoxLayout, QLabel, QToolButton, QWidget

import qtawesome as qta


def _start_native_caption_operation(window, hit_test: int) -> bool:
    """Delegate a fallback move/resize to Windows instead of emulating every pixel."""
    if sys.platform != "win32":
        return False
    try:
        hwnd = wintypes.HWND(int(window.winId()))
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.ReleaseCapture()
        send_message = user32.SendMessageW
        send_message.argtypes = (
            wintypes.HWND, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t
        )
        send_message.restype = ctypes.c_ssize_t
        # WM_NCLBUTTONDOWN: let Windows own snapping, sizing and drag feedback.
        send_message(hwnd, 0x00A1, hit_test, 0)
        return True
    except (AttributeError, OSError, TypeError, ValueError):
        return False


class CustomTitleBar(QWidget):
    def __init__(self, window):
        super().__init__(window)
        self.host = window
        self.setObjectName("customTitleBar")
        self.setFixedHeight(34)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 10, 0)
        layout.setSpacing(8)

        self.logo = QLabel("A", self)
        self.logo.setObjectName("titleBarLogo")
        self.logo.setAlignment(Qt.AlignCenter)
        self.logo.setFixedSize(24, 24)
        self.logo.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout.addWidget(self.logo)

        self.title = QLabel("ARMA Browser", self)
        self.title.setObjectName("titleBarTitle")
        self.title.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout.addWidget(self.title)
        layout.addStretch(1)

        self.minimize_button = self._button("Minimize", "windowMinimizeButton", "fa5s.minus")
        self.maximize_button = self._button("Maximize", "windowMaximizeButton", "fa5s.window-maximize")
        self.close_button = self._button("Close", "windowCloseButton", "fa5s.times")
        layout.addWidget(self.minimize_button)
        layout.addWidget(self.maximize_button)
        layout.addWidget(self.close_button)

        self._manual_move_active = False
        self._manual_move_origin = QPoint()
        self._manual_move_geometry = QRect()
        self.minimize_button.clicked.connect(window.showMinimized)
        self.maximize_button.clicked.connect(self._toggle_maximized)
        self.close_button.clicked.connect(window.close)
        self.sync_maximize_button()

    def _button(self, tooltip, object_name, icon_name):
        button = QToolButton(self)
        button.setObjectName(object_name)
        button.setToolButtonStyle(Qt.ToolButtonIconOnly)
        button.setIcon(qta.icon(icon_name, color="#68778c"))
        button.setIconSize(QSize(13, 13))
        button.setToolTip(tooltip)
        button.setAccessibleName(tooltip)
        button.setFixedSize(34, 28)
        button.setFocusPolicy(Qt.NoFocus)
        return button

    def _toggle_maximized(self):
        if self.host.isMaximized():
            self.host.showNormal()
        else:
            self.host.showMaximized()
        self.sync_maximize_button()
        # Some window managers apply the state after the clicked signal returns.
        QTimer.singleShot(0, self.sync_maximize_button)

    def apply_icon_theme(self, dark: bool) -> None:
        color = "#c4cedd" if dark else "#68778c"
        self.minimize_button.setIcon(qta.icon("fa5s.minus", color=color))
        self.close_button.setIcon(qta.icon("fa5s.times", color=color))
        self.sync_maximize_button(color)

    def sync_maximize_button(self, color: str | None = None):
        maximized = self.host.isMaximized()
        if color is None:
            dark = bool(getattr(getattr(self.host, "settings", None), "dark_mode", False))
            color = "#c4cedd" if dark else "#68778c"
        self.maximize_button.setIcon(
            qta.icon("fa5s.window-restore" if maximized else "fa5s.window-maximize", color=color)
        )
        self.maximize_button.setToolTip("Restore" if maximized else "Maximize")
        self.maximize_button.setAccessibleName(self.maximize_button.toolTip())

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            handle = self.host.windowHandle()
            if handle is not None and handle.startSystemMove():
                self._manual_move_active = False
                event.accept()
                return
            if _start_native_caption_operation(self.host, 2):  # HTCAPTION
                self._manual_move_active = False
                event.accept()
                return
            self._manual_move_origin = event.globalPosition().toPoint()
            self._manual_move_geometry = self.host.geometry()
            self._manual_move_active = not self.host.isMaximized() and not self.host.isFullScreen()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (
            self._manual_move_active
            and event.buttons() & Qt.MouseButton.LeftButton
            and not self.host.isMaximized()
            and not self.host.isFullScreen()
        ):
            delta = event.globalPosition().toPoint() - self._manual_move_origin
            self.host.move(self._manual_move_geometry.topLeft() + delta)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._manual_move_active = False
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._manual_move_active = False
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
        self._manual_resize_active = False
        self._resize_origin = QPoint()
        self._resize_geometry = QRect()
        self.setCursor(cursor)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFocusPolicy(Qt.NoFocus)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            handle = self.host.windowHandle()
            if handle is not None and handle.startSystemResize(self.edges):
                event.accept()
                return
            left = bool(self.edges & Qt.Edge.LeftEdge)
            right = bool(self.edges & Qt.Edge.RightEdge)
            top = bool(self.edges & Qt.Edge.TopEdge)
            bottom = bool(self.edges & Qt.Edge.BottomEdge)
            hit_test = (
                13 if top and left else 14 if top and right
                else 16 if bottom and left else 17 if bottom and right
                else 10 if left else 11 if right else 12 if top else 15
            )
            if _start_native_caption_operation(self.host, hit_test):
                event.accept()
                return
            self._resize_origin = event.globalPosition().toPoint()
            self._resize_geometry = self.host.geometry()
            self._manual_resize_active = not self.host.isMaximized() and not self.host.isFullScreen()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (
            self._manual_resize_active
            and event.buttons() & Qt.MouseButton.LeftButton
            and not self.host.isMaximized()
            and not self.host.isFullScreen()
        ):
            delta = event.globalPosition().toPoint() - self._resize_origin
            start = self._resize_geometry
            left, top = start.left(), start.top()
            right, bottom = start.right(), start.bottom()
            min_width = max(1, self.host.minimumWidth())
            min_height = max(1, self.host.minimumHeight())
            if self.edges & Qt.Edge.LeftEdge:
                left = min(left + delta.x(), right - min_width + 1)
            elif self.edges & Qt.Edge.RightEdge:
                right = max(right + delta.x(), left + min_width - 1)
            if self.edges & Qt.Edge.TopEdge:
                top = min(top + delta.y(), bottom - min_height + 1)
            elif self.edges & Qt.Edge.BottomEdge:
                bottom = max(bottom + delta.y(), top + min_height - 1)
            self.host.setGeometry(QRect(
                left, top,
                max(min_width, right - left + 1),
                max(min_height, bottom - top + 1),
            ))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._manual_resize_active = False
        super().mouseReleaseEvent(event)
