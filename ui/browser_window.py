import os
import re
import time
import json
import copy
import ctypes
from ctypes import wintypes
import logging
import heapq
import sys
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import List, Optional, Dict

from PySide6.QtCore import (
    QEvent, Qt, QUrl, QUrlQuery, QTimer, Signal, QPoint, QRect, QSize, QPropertyAnimation, QProcess,
    QVariantAnimation, QEasingCurve,
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QToolButton, QLabel, QProgressBar, QFrame, QSizePolicy,
    QScrollArea, QGraphicsOpacityEffect, QInputDialog,
    QLineEdit, QMenu, QMessageBox, QSplitter, QFileDialog, QToolButton
)
from PySide6.QtGui import QPixmap, QIcon, QAction, QKeySequence, QFontMetrics, QDesktopServices, QPainter, QPainterPath, QColor, QCursor
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineSettings, QWebEngineLoadingInfo
from PySide6.QtWebEngineCore import QWebEngineFullScreenRequest
from PySide6.QtWebChannel import QWebChannel

import qtawesome as qta

from .settings import Settings
from .navigation_bar import NavigationBar
from .settings_window import SettingsWindow
from .title_bar import CustomTitleBar, ResizeHandle
from .history_window import HistoryWindow
from .downloads_panel import DownloadsPanel
from .dashboard.internal_page import (
    DASHBOARD_SCHEME,
    DASHBOARD_URL,
    INTERNAL_PAGE_HOSTS,
    DashboardSchemeHandler,
    register_dashboard_scheme,
)
# Custom URL schemes must be registered before QApplication/QWebEngine profiles exist.
register_dashboard_scheme()
from .internal_pages import render_internal_page
from managers.history_manager import History
from managers.dashboard_manager import DashboardManager
from .dashboard.bridge import DashboardBridge
from .themes import light_theme, dark_theme
from .url_utils import URLInputError, resolve_address_input
from proxy import proxy as proxy_routing
from proxy.set_proxy import manage_proxy
from proxy.ui import Window

try:
    from managers.bookmarks_manager import BookmarksManager
except ModuleNotFoundError as exc:
    if exc.name != "managers.bookmarks_manager":
        raise
    BookmarksManager = None

try:
    from managers.download_manager import DownloadManager
except ModuleNotFoundError as exc:
    if exc.name != "managers.download_manager":
        raise
    DownloadManager = None

try:
    from .bookmarks_bar import BookmarksBar
except ModuleNotFoundError as exc:
    if exc.name != "ui.bookmarks_bar":
        raise
    BookmarksBar = None

try:
    from .bookmarks_dialog import BookmarksDialog
except ModuleNotFoundError as exc:
    if exc.name != "ui.bookmarks_dialog":
        raise
    BookmarksDialog = None

TAB_WIDTH = 150
MIN_TAB_WIDTH = 92
MAX_TAB_WIDTH = 198
TAB_HEIGHT = 30
TAB_SPACING = 4
SCROLL_STEP = 220

# Keep Qt's custom frameless chrome while restoring native Windows resizing and
# snap capabilities that Qt normally removes with FramelessWindowHint.
_WIN_GWL_STYLE = -16
_WIN_WS_CAPTION = 0x00C00000
_WIN_WS_SYSMENU = 0x00080000
_WIN_WS_THICKFRAME = 0x00040000
_WIN_WS_MINIMIZEBOX = 0x00020000
_WIN_WS_MAXIMIZEBOX = 0x00010000
_WIN_SWP_NOSIZE = 0x0001
_WIN_SWP_NOMOVE = 0x0002
_WIN_SWP_NOZORDER = 0x0004
_WIN_SWP_NOACTIVATE = 0x0010
_WIN_SWP_FRAMECHANGED = 0x0020
_WIN_WM_NCHITTEST = 0x0084
_WIN_HTCLIENT = 1
_WIN_HTCAPTION = 2
_WIN_DWMWA_WINDOW_CORNER_PREFERENCE = 33
_WIN_DWMWCP_DONOTROUND = 1
_WIN_DWMWCP_ROUND = 2
_WIN_HTLEFT = 10
_WIN_HTRIGHT = 11
_WIN_HTTOP = 12
_WIN_HTTOPLEFT = 13
_WIN_HTTOPRIGHT = 14
_WIN_HTBOTTOM = 15
_WIN_HTBOTTOMLEFT = 16
_WIN_HTBOTTOMRIGHT = 17


def _with_resizable_frameless_windows_style(style: int) -> int:
    """Retain the custom title bar, but keep the native resize/snap styles."""
    style |= (
        _WIN_WS_THICKFRAME
        | _WIN_WS_SYSMENU
        | _WIN_WS_MINIMIZEBOX
        | _WIN_WS_MAXIMIZEBOX
    )
    return style & ~_WIN_WS_CAPTION

def _is_snap_aligned_geometry(frame: QRect, available: QRect) -> bool:
    """Detect common Windows Snap Layout cells without relying on maximize state."""
    if frame.isEmpty() or available.isEmpty():
        return False
    tolerance = max(8, int(min(available.width(), available.height()) * 0.006))
    fractions = (0.0, 0.25, 1 / 3, 0.5, 2 / 3, 0.75, 1.0)

    def boundaries(origin: int, length: int) -> tuple[int, ...]:
        return tuple(origin + round(length * fraction) for fraction in fractions)

    x_grid = boundaries(available.x(), available.width())
    y_grid = boundaries(available.y(), available.height())
    frame_edges = (
        frame.x(),
        frame.x() + frame.width(),
        frame.y(),
        frame.y() + frame.height(),
    )
    x_aligned = (
        any(abs(frame_edges[0] - value) <= tolerance for value in x_grid)
        and any(abs(frame_edges[1] - value) <= tolerance for value in x_grid)
    )
    y_aligned = (
        any(abs(frame_edges[2] - value) <= tolerance for value in y_grid)
        and any(abs(frame_edges[3] - value) <= tolerance for value in y_grid)
    )
    # Avoid classifying a small, ordinary window as snapped just because two
    # of its edges happen to land near grid lines.
    large_enough = (
        frame.width() >= available.width() * 0.18
        and frame.height() >= available.height() * 0.18
    )
    return bool(x_aligned and y_aligned and large_enough)


class _DownloadsOverlayDismissArea(QFrame):
    """Transparent click target that dismisses the drawer without obscuring the page."""

    dismissed = Signal()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.dismissed.emit()
        event.accept()


class _PageLoadOverlay(QFrame):
    """A small, non-blocking loading HUD attached to its own web page."""

    def __init__(self, view: QWidget):
        super().__init__(view)
        self.view = view
        self.setObjectName("pageLoadOverlay")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setFixedHeight(56)
        self.setMinimumWidth(220)
        self.setMaximumWidth(360)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 9)
        layout.setSpacing(6)
        heading = QHBoxLayout()
        heading.setContentsMargins(0, 0, 0, 0)
        heading.setSpacing(8)
        self.title_label = QLabel("Loading page", self)
        self.title_label.setObjectName("pageLoadOverlayTitle")
        heading.addWidget(self.title_label, 1)
        self.percent_label = QLabel("Connecting…", self)
        self.percent_label.setObjectName("pageLoadOverlayPercent")
        self.percent_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        heading.addWidget(self.percent_label)
        layout.addLayout(heading)

        self.progress_bar = QProgressBar(self)
        self.progress_bar.setObjectName("pageLoadOverlayProgress")
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(4)
        self.progress_bar.setRange(0, 0)
        layout.addWidget(self.progress_bar)

        view.installEventFilter(self)
        self.hide()

    def _position_over_page(self) -> None:
        if self.view is None:
            return
        parent_width = max(1, self.view.width())
        width = min(336, max(1, parent_width - 24))
        x = max(8, (parent_width - width) // 2)
        self.setGeometry(x, 14, width, self.height())
        self.raise_()

    def show_loading(self, progress: int | None = None) -> None:
        if progress is None:
            self.progress_bar.setRange(0, 0)
            self.percent_label.setText("Connecting…")
        else:
            value = max(0, min(100, int(progress)))
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(value)
            self.percent_label.setText(f"{value}%")
        self._position_over_page()
        self.show()
        self.raise_()

    def eventFilter(self, watched, event) -> bool:
        if watched is self.view and event.type() == QEvent.Type.Resize:
            self._position_over_page()
        return super().eventFilter(watched, event)


class _RoundedCornerCutout(QWidget):
    """Antialiased corner patch that visually rounds a WebEngine surface without masking it."""

    _BEZIER_CIRCLE = 0.5522847498

    def __init__(self, parent: QWidget, corner: str, radius: int):
        super().__init__(parent)
        self.corner = corner
        self._radius = float(radius)
        self._color = QColor("#e9edf3")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.hide()

    def set_color(self, color: str | QColor) -> None:
        next_color = QColor(color)
        if next_color != self._color:
            self._color = next_color
            self.update()

    def set_radius(self, radius: int) -> None:
        radius = max(0, int(radius))
        if radius != self._radius:
            self._radius = float(radius)
            self.update()

    def paintEvent(self, event) -> None:
        radius = min(self._radius, float(self.width()), float(self.height()))
        if radius < 1:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._color)
        if self.corner.endswith("right"):
            painter.translate(self.width(), 0)
            painter.scale(-1, 1)
        if self.corner.startswith("bottom"):
            painter.translate(0, self.height())
            painter.scale(1, -1)

        # Paint only the area outside the quarter-circle. The page itself keeps
        # its normal compositor surface; antialiasing happens in this tiny patch.
        control = radius * self._BEZIER_CIRCLE
        path = QPainterPath()
        path.moveTo(0.0, 0.0)
        path.lineTo(radius, 0.0)
        path.cubicTo(radius - control, 0.0, 0.0, radius - control, 0.0, radius)
        path.closeSubpath()
        painter.drawPath(path)
        painter.end()


class _RoundedWebView(QWebEngineView):
    """WebEngine viewport with antialiased visual corners and no compositor mask."""

    CORNER_RADIUS = 14
    CORNERS = ("top-left", "top-right", "bottom-left", "bottom-right")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("browserPageView")
        self._rounded_corners_enabled = True
        self._corner_color = QColor("#e9edf3")
        self._corner_cutouts = {
            corner: _RoundedCornerCutout(self, corner, self.CORNER_RADIUS)
            for corner in self.CORNERS
        }

    def set_corner_color(self, color: str) -> None:
        next_color = QColor(color)
        if next_color == self._corner_color:
            return
        self._corner_color = next_color
        for cutout in self._corner_cutouts.values():
            cutout.set_color(next_color)

    def set_rounded_corners(self, enabled: bool) -> None:
        self._rounded_corners_enabled = bool(enabled)
        self._update_corner_cutouts()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_corner_cutouts()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._update_corner_cutouts()

    def _update_corner_cutouts(self) -> None:
        width, height = self.width(), self.height()
        radius = min(self.CORNER_RADIUS, width // 2, height // 2)
        if not self._rounded_corners_enabled or radius < 1:
            for cutout in self._corner_cutouts.values():
                cutout.hide()
            return

        geometries = {
            "top-left": QRect(0, 0, radius, radius),
            "top-right": QRect(width - radius, 0, radius, radius),
            "bottom-left": QRect(0, height - radius, radius, radius),
            "bottom-right": QRect(width - radius, height - radius, radius, radius),
        }
        for corner, cutout in self._corner_cutouts.items():
            cutout.set_radius(radius)
            cutout.set_color(self._corner_color)
            cutout.setGeometry(geometries[corner])
            cutout.show()
            cutout.raise_()


class _ProxyPanelHost(QFrame):
    """Opaque, resizable proxy pane aligned with the browser tabs and viewport."""

    visibilityChanged = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("proxyDock")
        self.setMinimumWidth(0)
        self.setMaximumWidth(420)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self._panel_layout = QVBoxLayout(self)
        self._panel_layout.setContentsMargins(0, 0, 0, 0)
        self._panel_layout.setSpacing(0)
        self._hosted_widget = None
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

    def setWidget(self, widget):
        if self._hosted_widget is widget:
            return
        if self._hosted_widget is not None:
            self._panel_layout.removeWidget(self._hosted_widget)
            self._hosted_widget.setParent(None)
        self._hosted_widget = widget
        if widget is not None:
            widget.setParent(self)
            self._panel_layout.addWidget(widget)

    def setVisible(self, visible):
        visible = bool(visible)
        was_hidden = self.isHidden()
        super().setVisible(visible)
        # Only explicit pane toggles emit this signal; minimization/hiding the
        # whole browser window must not silently change the saved preference.
        if was_hidden == visible:
            self.visibilityChanged.emit(visible)


class TabButton(QFrame):
    """A compact, draggable browser tab with favicon, loading state and hover close."""

    clicked = Signal()
    closed = Signal()
    requested_preview = Signal()
    context_requested = Signal(QPoint)
    drag_moved = Signal(QPoint)

    def __init__(self, title: str = "New Tab"):
        super().__init__()
        self.setObjectName("browserTab")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMinimumWidth(MIN_TAB_WIDTH)
        self.setMaximumWidth(MAX_TAB_WIDTH)
        self.setFixedHeight(TAB_HEIGHT - 4)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self._title = title or "New Tab"
        self._active = False
        self._dark_mode = False
        self._loading = False
        self._site_icon: QIcon | None = None
        self._press_pos = QPoint()
        self._dragging = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(7, 1, 4, 1)
        layout.setSpacing(5)

        self.favicon = QLabel(self)
        self.favicon.setObjectName("tabFavicon")
        self.favicon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.favicon.setFixedSize(16, 16)
        self.favicon.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self.label = QLabel(self._title, self)
        self.label.setObjectName("tabTitle")
        self.label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.label.setMinimumWidth(0)
        self.label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self.label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self.close_btn = QPushButton(self)
        self.close_btn.setObjectName("tabCloseButton")
        self.close_btn.setIconSize(QSize(11, 11))
        self.close_btn.setFixedSize(18, 18)
        self.close_btn.hide()
        self.close_btn.setMouseTracking(True)
        self.close_btn.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.close_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.close_btn.setToolTip("Close tab")
        self.close_btn.setAccessibleName("Close tab")
        self.close_btn.clicked.connect(self.closed.emit)

        layout.addWidget(self.favicon)
        layout.addWidget(self.label, 1)
        layout.addWidget(self.close_btn)

        self._hover_timer = QTimer(self)
        self._hover_timer.setSingleShot(True)
        self._hover_timer.setInterval(520)
        self._hover_timer.timeout.connect(self._emit_preview)
        self.installEventFilter(self)
        self.close_btn.installEventFilter(self)
        self.set_title(title)
        self.apply_icon_theme(False)
        self.set_active(False)

    def apply_icon_theme(self, dark: bool) -> None:
        self._dark_mode = bool(dark)
        close_color = "#a8b6c9" if self._dark_mode else "#6a788d"
        self.close_btn.setIcon(qta.icon("fa5s.times", color=close_color))
        self._refresh_favicon()

    def set_site_icon(self, icon: QIcon | None) -> None:
        self._site_icon = icon if isinstance(icon, QIcon) and not icon.isNull() else None
        self._refresh_favicon()

    def set_loading(self, loading: bool) -> None:
        self._loading = bool(loading)
        self._refresh_favicon()

    def _refresh_favicon(self) -> None:
        accent = "#82aff4" if self._dark_mode else "#3477d4"
        if self._loading:
            icon = qta.icon("fa5s.sync-alt", color=accent)
        elif self._site_icon is not None:
            icon = self._site_icon
        else:
            icon = qta.icon("fa5s.globe", color=accent if self._active else (
                "#a4b0c0" if self._dark_mode else "#8795a8"
            ))
        self.favicon.setPixmap(icon.pixmap(QSize(16, 16)))
        self.favicon.setToolTip("Loading page…" if self._loading else "Site icon")

    def _emit_preview(self) -> None:
        if not self._dragging:
            self.requested_preview.emit()

    def _sync_close_button_visibility(self) -> None:
        if self._dragging:
            self.close_btn.hide()
            return
        local_cursor = self.mapFromGlobal(QCursor.pos())
        self.close_btn.setVisible(self.rect().contains(local_cursor))

    def enterEvent(self, event) -> None:
        if not self._dragging:
            self.close_btn.show()
            self._hover_timer.start()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover_timer.stop()
        # Qt may report Leave as the pointer crosses the child close button.
        # Recheck the cursor after event dispatch before deciding to hide it.
        QTimer.singleShot(0, self._sync_close_button_visibility)
        super().leaveEvent(event)

    def event(self, event) -> bool:
        if event.type() == QEvent.Type.HoverEnter and not self._dragging:
            self.close_btn.show()
        elif event.type() == QEvent.Type.HoverLeave:
            self._hover_timer.stop()
            QTimer.singleShot(0, self._sync_close_button_visibility)
        return super().event(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_pos = event.position().toPoint()
            self._dragging = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if not (event.buttons() & Qt.MouseButton.LeftButton) and not self._dragging:
            # Some windowing backends deliver a move before the hover enter.
            self.close_btn.show()
        if event.buttons() & Qt.MouseButton.LeftButton:
            current = event.position().toPoint()
            if not self._dragging and (current - self._press_pos).manhattanLength() >= QApplication.startDragDistance():
                self._dragging = True
                self._hover_timer.stop()
                self.close_btn.hide()
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
            if self._dragging:
                self.drag_moved.emit(event.globalPosition().toPoint())
                event.accept()
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._dragging:
            self._dragging = False
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            if self.underMouse():
                self.close_btn.show()
            else:
                self.close_btn.hide()
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton and not self.close_btn.underMouse():
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def eventFilter(self, obj, event) -> bool:
        if obj is self.close_btn:
            if event.type() in (QEvent.Type.Enter, QEvent.Type.HoverEnter):
                if not self._dragging:
                    self.close_btn.show()
            elif event.type() in (QEvent.Type.Leave, QEvent.Type.HoverLeave):
                QTimer.singleShot(0, self._sync_close_button_visibility)
        if event.type() == QEvent.Type.ContextMenu:
            self.context_requested.emit(event.globalPos())
            return True
        return super().eventFilter(obj, event)

    def set_active(self, active: bool) -> None:
        self._active = bool(active)
        self.setProperty("active", self._active)
        self.setAccessibleName(self._title if not self._loading else f"{self._title}, loading")
        self.style().unpolish(self)
        self.style().polish(self)
        self._refresh_favicon()
        self.update()

    def set_title(self, title: str) -> None:
        self._title = str(title or "New Tab")
        self.setToolTip(self._title)
        self.setAccessibleName(self._title)
        self._update_elided_title()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_elided_title()

    def _update_elided_title(self) -> None:
        metrics = QFontMetrics(self.label.font())
        self.label.setText(
            metrics.elidedText(self._title, Qt.TextElideMode.ElideRight, max(0, self.label.width()))
        )


class CustomTabBar(QFrame):
    """Responsive tab strip with favicon updates, scrolling and drag reordering."""

    tab_changed = Signal(int)
    tab_closed = Signal(int)
    tab_reordered = Signal(int, int)
    new_tab_requested = Signal()
    tab_preview_requested = Signal(int)
    tab_context_requested = Signal(int, QPoint)

    def __init__(self):
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(TAB_HEIGHT + 4)
        self.tabs: List[TabButton] = []
        self.active_index: int = -1
        self.plus_inside = True
        self._updating = False

        root = QHBoxLayout(self)
        root.setContentsMargins(7, 2, 7, 2)
        root.setSpacing(3)

        self._dark_mode = False
        self.btn_left = QPushButton(self)
        self.btn_left.setObjectName("tabScrollButton")
        self.btn_left.setIconSize(QSize(11, 11))
        self.btn_left.setFixedSize(22, TAB_HEIGHT - 4)
        self.btn_left.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_left.setToolTip("Scroll tabs left")
        self.btn_left.clicked.connect(lambda: self._scroll(-SCROLL_STEP))
        self.btn_left.hide()

        self.btn_right = QPushButton(self)
        self.btn_right.setObjectName("tabScrollButton")
        self.btn_right.setIconSize(QSize(11, 11))
        self.btn_right.setFixedSize(22, TAB_HEIGHT - 4)
        self.btn_right.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_right.setToolTip("Scroll tabs right")
        self.btn_right.clicked.connect(lambda: self._scroll(SCROLL_STEP))
        self.btn_right.hide()

        self.holder = QWidget()
        self.holder.setObjectName("tabStripHolder")
        self.holder_layout = QHBoxLayout(self.holder)
        self.holder_layout.setContentsMargins(0, 0, 0, 0)
        self.holder_layout.setSpacing(TAB_SPACING)
        self.holder_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        self.scroll = QScrollArea(self)
        self.scroll.setObjectName("tabStripScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setWidget(self.holder)
        self.scroll.setFixedHeight(TAB_HEIGHT - 4)
        self.scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.scroll.installEventFilter(self)
        self.scroll.viewport().installEventFilter(self)

        self.plus_tab = QPushButton(self)
        self.plus_tab.setObjectName("tabPlusButton")
        self.plus_tab.setIconSize(QSize(13, 13))
        self.plus_tab.setFixedSize(24, TAB_HEIGHT - 6)
        self.plus_tab.setToolTip("New tab")
        self.plus_tab.setAccessibleName("New tab")
        self.plus_tab.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.plus_tab.clicked.connect(self.new_tab_requested.emit)

        self.external_plus = QPushButton(self)
        self.external_plus.setObjectName("tabPlusButton")
        self.external_plus.setIconSize(QSize(13, 13))
        self.external_plus.setFixedSize(24, TAB_HEIGHT - 6)
        self.external_plus.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.external_plus.setToolTip("New tab")
        self.external_plus.setAccessibleName("New tab")
        self.external_plus.clicked.connect(self.new_tab_requested.emit)
        self.external_plus.hide()
        self.holder_layout.addWidget(self.plus_tab)

        self.tab_list_button = QToolButton(self)
        self.tab_list_button.setObjectName("tabListButton")
        self.tab_list_button.setIconSize(QSize(12, 12))
        self.tab_list_button.setFixedSize(22, TAB_HEIGHT - 4)
        self.tab_list_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.tab_list_button.setAutoRaise(True)
        self.tab_list_button.setToolTip("List all open tabs")
        self.tab_list_button.setAccessibleName("List all open tabs")
        self.tab_list_menu = QMenu(self.tab_list_button)
        self.tab_list_menu.aboutToShow.connect(self._populate_tab_list_menu)
        self.tab_list_button.setMenu(self.tab_list_menu)
        self.tab_list_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.tab_list_button.hide()

        root.addWidget(self.btn_left)
        root.addWidget(self.scroll, 1)
        root.addWidget(self.btn_right)
        root.addWidget(self.tab_list_button)
        root.addWidget(self.external_plus)
        self.apply_icon_theme(False)

    def apply_icon_theme(self, dark: bool) -> None:
        self._dark_mode = bool(dark)
        color = "#a9b7c9" if self._dark_mode else "#68778b"
        plus_color = "#c2d0e4" if self._dark_mode else "#526985"
        self.btn_left.setIcon(qta.icon("fa5s.chevron-left", color=color))
        self.btn_right.setIcon(qta.icon("fa5s.chevron-right", color=color))
        self.tab_list_button.setIcon(qta.icon("fa5s.list-ul", color=color))
        self.plus_tab.setIcon(qta.icon("fa5s.plus", color=plus_color))
        self.external_plus.setIcon(qta.icon("fa5s.plus", color=plus_color))
        for tab in self.tabs:
            tab.apply_icon_theme(self._dark_mode)

    def add_tab(self, title: str = "New Tab", make_active: bool = True) -> int:
        tab = TabButton(title)
        tab.apply_icon_theme(self._dark_mode)
        tab.clicked.connect(lambda target=tab: self._on_tab_clicked(target))
        tab.closed.connect(lambda target=tab: self._on_tab_closed(target))
        tab.requested_preview.connect(lambda target=tab: self._on_tab_preview_requested(target))
        tab.drag_moved.connect(lambda pos, target=tab: self._on_tab_drag_moved(target, pos))
        tab.context_requested.connect(
            lambda pos, target=tab: self.tab_context_requested.emit(self.tabs.index(target), pos)
            if target in self.tabs else None
        )

        insert_pos = max(0, self.holder_layout.count() - (1 if self.plus_inside else 0))
        self.holder_layout.insertWidget(insert_pos, tab)
        self.tabs.append(tab)

        index = len(self.tabs) - 1
        if make_active or self.active_index < 0:
            self.set_active(index)
        QTimer.singleShot(0, self._update_overflow)
        return index

    def remove_tab(self, index: int, activate: bool = True) -> None:
        if index < 0 or index >= len(self.tabs):
            return
        old_active_index = self.active_index
        tab = self.tabs.pop(index)
        self.holder_layout.removeWidget(tab)
        tab.setParent(None)
        tab.deleteLater()

        if not self.tabs:
            self.active_index = -1
            if activate and old_active_index != -1:
                self.tab_changed.emit(-1)
            QTimer.singleShot(0, self._update_overflow)
            return

        if self.active_index == index:
            self.active_index = min(index, len(self.tabs) - 1)
        elif self.active_index > index:
            self.active_index -= 1
        for current, item in enumerate(self.tabs):
            item.set_active(current == self.active_index)
        if activate and self.active_index != old_active_index:
            self.tab_changed.emit(self.active_index)
        QTimer.singleShot(0, self._update_overflow)

    def set_active(self, index: int) -> None:
        if not self.tabs:
            self.active_index = -1
            self.tab_changed.emit(-1)
            return
        index = max(0, min(index, len(self.tabs) - 1))
        changed = index != self.active_index
        self.active_index = index
        for current, tab in enumerate(self.tabs):
            tab.set_active(current == index)
        if changed:
            self.tab_changed.emit(index)
        QTimer.singleShot(0, lambda target=index: self.ensure_tab_visible(target))

    def set_title(self, index: int, title: str) -> None:
        if 0 <= index < len(self.tabs):
            self.tabs[index].set_title(title)

    def set_icon(self, index: int, icon: QIcon | None) -> None:
        if 0 <= index < len(self.tabs):
            self.tabs[index].set_site_icon(icon)

    def set_loading(self, index: int, loading: bool) -> None:
        if 0 <= index < len(self.tabs):
            self.tabs[index].set_loading(loading)

    def _populate_tab_list_menu(self) -> None:
        """Build a quick-access list when many tabs no longer fit in one row."""
        self.tab_list_menu.clear()
        for index, tab in enumerate(self.tabs):
            if tab._loading:
                color = "#82aff4" if self._dark_mode else "#3477d4"
                icon = qta.icon("fa5s.sync-alt", color=color)
            elif tab._site_icon is not None:
                icon = tab._site_icon
            else:
                color = "#a9b7c9" if self._dark_mode else "#68778b"
                icon = qta.icon("fa5s.globe", color=color)
            label = tab._title.strip() or "New Tab"
            action = QAction(icon, label, self.tab_list_menu)
            action.setCheckable(True)
            action.setChecked(index == self.active_index)
            action.setToolTip(tab._title)
            action.triggered.connect(lambda _checked=False, target=index: self.set_active(target))
            self.tab_list_menu.addAction(action)
        if self.tabs:
            self.tab_list_menu.addSeparator()
        new_tab_action = QAction(qta.icon("fa5s.plus"), "New tab", self.tab_list_menu)
        new_tab_action.triggered.connect(self.new_tab_requested.emit)
        self.tab_list_menu.addAction(new_tab_action)

    def ensure_tab_visible(self, index: int) -> None:
        if index < 0 or index >= len(self.tabs):
            return
        tab = self.tabs[index]
        try:
            local_x = tab.mapTo(self.holder, tab.rect().topLeft()).x()
            tab_width = tab.width()
            visible_width = self.scroll.viewport().width()
            current = self.scroll.horizontalScrollBar().value()
            if local_x < current:
                self.scroll.horizontalScrollBar().setValue(local_x)
            elif local_x + tab_width > current + visible_width:
                self.scroll.horizontalScrollBar().setValue(local_x + tab_width - visible_width)
        except RuntimeError:
            logger.debug("Skipped tab visibility update for a widget being destroyed", exc_info=True)

    def _scroll(self, delta: int) -> None:
        bar = self.scroll.horizontalScrollBar()
        bar.setValue(max(bar.minimum(), min(bar.maximum(), bar.value() + int(delta))))

    def _move_tab_to(self, tab: TabButton, target_index: int) -> None:
        if tab not in self.tabs:
            return
        old_index = self.tabs.index(tab)
        target_index = max(0, min(int(target_index), len(self.tabs) - 1))
        if old_index == target_index:
            return

        active = self.active_index
        self.tabs.pop(old_index)
        self.tabs.insert(target_index, tab)
        self.holder_layout.removeWidget(tab)
        self.holder_layout.insertWidget(target_index, tab)

        if active == old_index:
            self.active_index = target_index
        elif old_index < active <= target_index:
            self.active_index = active - 1
        elif target_index <= active < old_index:
            self.active_index = active + 1

        for index, current in enumerate(self.tabs):
            current.set_active(index == self.active_index)
        self.tab_reordered.emit(old_index, target_index)
        QTimer.singleShot(0, self._update_overflow)
        if self.active_index >= 0:
            QTimer.singleShot(0, lambda index=self.active_index: self.ensure_tab_visible(index))

    def _on_tab_drag_moved(self, tab: TabButton, global_position: QPoint) -> None:
        if tab not in self.tabs or len(self.tabs) < 2:
            return
        pointer_x = self.holder.mapFromGlobal(global_position).x()
        target_index = sum(
            1 for other in self.tabs
            if other is not tab and pointer_x > other.geometry().center().x()
        )
        self._move_tab_to(tab, target_index)

    def _update_overflow(self) -> None:
        if self._updating:
            return
        self._updating = True
        try:
            count = len(self.tabs)
            width_without_controls = max(0, self.width() - 16)
            preferred_tab_width = (
                width_without_controls - self.plus_tab.width() - TAB_SPACING * count
            ) // max(1, count)
            overflow = bool(count and preferred_tab_width < MIN_TAB_WIDTH)

            self.btn_left.setVisible(overflow)
            self.btn_right.setVisible(overflow)
            self.tab_list_button.setVisible(overflow)
            if overflow and self.plus_inside:
                self.holder_layout.removeWidget(self.plus_tab)
                self.plus_tab.setParent(None)
                self.external_plus.show()
                self.plus_inside = False
            elif not overflow and not self.plus_inside:
                self.holder_layout.addWidget(self.plus_tab)
                self.plus_tab.setParent(self.holder)
                self.external_plus.hide()
                self.plus_inside = True

            if overflow:
                tab_width = MIN_TAB_WIDTH
            else:
                margins = self.layout().contentsMargins()
                available = max(
                    0,
                    self.width() - margins.left() - margins.right()
                    - self.plus_tab.width() - TAB_SPACING * count
                    - self.layout().spacing() * max(0, count),
                )
                tab_width = min(MAX_TAB_WIDTH, max(MIN_TAB_WIDTH, available // max(1, count)))
            for tab in self.tabs:
                tab.setFixedWidth(tab_width)

            content_width = count * tab_width + TAB_SPACING * max(0, count - 1)
            if self.plus_inside:
                content_width += self.plus_tab.width() + (TAB_SPACING if count else 0)
            self.holder.setMinimumWidth(content_width)
            if overflow:
                self.scroll.horizontalScrollBar().setPageStep(max(1, self.scroll.viewport().width()))
                if self.active_index >= 0:
                    QTimer.singleShot(0, lambda index=self.active_index: self.ensure_tab_visible(index))
        finally:
            self._updating = False

    def eventFilter(self, watched, event) -> bool:
        if watched in (getattr(self, "scroll", None), getattr(getattr(self, "scroll", None), "viewport", lambda: None)()) and event.type() == QEvent.Type.Wheel:
            delta = event.angleDelta().y() or event.angleDelta().x()
            if delta:
                self._scroll(-int(delta / 120 * SCROLL_STEP))
                event.accept()
                return True
        return super().eventFilter(watched, event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        QTimer.singleShot(0, self._update_overflow)

    def _on_tab_clicked(self, tab: TabButton) -> None:
        if tab in self.tabs:
            self.set_active(self.tabs.index(tab))

    def _on_tab_closed(self, tab: TabButton) -> None:
        if tab in self.tabs:
            self.tab_closed.emit(self.tabs.index(tab))

    def _on_tab_preview_requested(self, tab: TabButton) -> None:
        try:
            index = self.tabs.index(tab)
        except ValueError:
            return
        if index != self.active_index:
            self.tab_preview_requested.emit(index)


class BrowserPage(QWebEnginePage):
    """Page that routes web requests for a new window into a browser tab."""

    def __init__(self, browser: "BrowserWindow", profile: QWebEngineProfile, parent):
        super().__init__(profile, parent)
        self.browser = browser
        self._dashboard_active = False
        self._dashboard_channel: QWebChannel | None = None
        self._dashboard_bridge: DashboardBridge | None = None
        self._media_decode_warning_shown = False
        self.loadStarted.connect(self._reset_media_decode_warning)

    def _reset_media_decode_warning(self) -> None:
        self._media_decode_warning_shown = False

    @staticmethod
    def _is_audio_decode_error(message: str) -> bool:
        normalized = str(message).casefold()
        return (
            "loading fsb failed for audio clip" in normalized
            or "unable to decode audio data" in normalized
        )

    def javaScriptConsoleMessage(self, level, message, line_number, source_id) -> None:
        """Keep Chromium diagnostics intact and surface a helpful audio compatibility hint."""
        if self._is_audio_decode_error(message) and not self._media_decode_warning_shown:
            self._media_decode_warning_shown = True
            QTimer.singleShot(0, self._show_audio_decode_warning)
        super().javaScriptConsoleMessage(level, message, line_number, source_id)

    def _show_audio_decode_warning(self) -> None:
        browser = self.browser
        if getattr(browser, "_closing", False):
            return
        view = next(
            (candidate for candidate in getattr(browser, "views", ()) if candidate.page() is self),
            None,
        )
        if view is None or view is not browser.current_view():
            return
        _show_status_message(browser, 
            "This page could not decode an audio asset. Try Browser menu → Open in default browser; audio codec support may differ.",
            10000,
        )

    def _enable_dashboard_bridge(self) -> None:
        was_active = self._dashboard_active
        self._dashboard_active = True
        if self._dashboard_channel is None:
            self._dashboard_channel = QWebChannel(self)
            self._dashboard_bridge = DashboardBridge(self.browser, self)
            self._dashboard_channel.registerObject("armaDashboard", self._dashboard_bridge)
        if not was_active:
            self.setWebChannel(self._dashboard_channel)

    def _disable_dashboard_bridge(self) -> None:
        self._dashboard_active = False
        self.setWebChannel(None)

    def acceptNavigationRequest(self, url, navigation_type, is_main_frame):
        scheme = url.scheme().lower()
        host = url.host().lower()
        if scheme == "arma":
            if not is_main_frame or host not in INTERNAL_PAGE_HOSTS:
                return False
            self._enable_dashboard_bridge()
            # Only the existing dashboard is allowed to fetch remote wallpaper assets.
            self.settings().setAttribute(
                QWebEngineSettings.LocalContentCanAccessRemoteUrls,
                host == "dashboard",
            )
            return super().acceptNavigationRequest(url, navigation_type, is_main_frame)
        if is_main_frame and self._dashboard_active:
            self._disable_dashboard_bridge()
            self.settings().setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, False)
        return super().acceptNavigationRequest(url, navigation_type, is_main_frame)

    def createWindow(self, window_type):
        index = self.browser.new_tab("about:blank", make_active=True)
        if 0 <= index < len(self.browser.views):
            return self.browser.views[index].page()
        return None


class _StatusMessageOverlay(QFrame):
    """Non-interactive status toast positioned over the active web page."""

    def __init__(self, parent: QWidget, *, dark: bool = False):
        super().__init__(parent)
        self.setObjectName("browserStatusOverlay")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setMaximumWidth(460)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(13, 8, 15, 8)
        self.label = QLabel(self)
        self.label.setObjectName("browserStatusOverlayText")
        self.label.setWordWrap(True)
        self.label.setMinimumWidth(0)
        layout.addWidget(self.label)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)
        parent.installEventFilter(self)
        self.set_theme(dark)

    def set_theme(self, dark: bool) -> None:
        if dark:
            self.setStyleSheet(
                "QFrame#browserStatusOverlay { background: rgba(24,31,43,242); "
                "color: #edf4ff; border: 1px solid rgba(133,164,212,190); "
                "border-radius: 11px; } "
                "QLabel#browserStatusOverlayText { background: transparent; "
                "color: #edf4ff; font-size: 12px; font-weight: 550; }"
            )
        else:
            self.setStyleSheet(
                "QFrame#browserStatusOverlay { background: rgba(250,252,255,246); "
                "color: #25364c; border: 1px solid rgba(159,177,202,205); "
                "border-radius: 11px; } "
                "QLabel#browserStatusOverlayText { background: transparent; "
                "color: #25364c; font-size: 12px; font-weight: 550; }"
            )

    def showMessage(self, message: str, timeout: int = 0) -> None:
        text = str(message or "").strip()
        if not text:
            self.clearMessage()
            return
        parent = self.parentWidget()
        max_width = 460
        self.label.setText(text)
        if parent is not None:
            max_width = max(190, min(460, parent.width() - 28))
            self.setMaximumWidth(max_width)
            self.label.setMaximumWidth(max(150, max_width - 30))
        self.adjustSize()
        if parent is not None:
            width = min(max_width, max(190, self.sizeHint().width()))
            self.resize(width, min(100, self.sizeHint().height()))
            self._position()
        self.show()
        self.raise_()
        self._timer.stop()
        if int(timeout) > 0:
            self._timer.start(int(timeout))

    def clearMessage(self) -> None:
        self._timer.stop()
        self.hide()

    def _position(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        x = min(15, max(0, parent.width() - self.width() - 8))
        y = max(8, parent.height() - self.height() - 14)
        self.move(x, y)

    def eventFilter(self, watched, event) -> bool:
        if watched is self.parentWidget() and event.type() in (
            QEvent.Type.Resize, QEvent.Type.Move, QEvent.Type.Show,
        ):
            if self.isVisible():
                QTimer.singleShot(0, self._position)
        return super().eventFilter(watched, event)


def _show_status_message(window, message: str, timeout: int = 0) -> None:
    """Route legacy status-bar calls to the overlay; retain fallback for unit-test doubles."""
    display = getattr(window, "_show_status_overlay", None)
    if callable(display):
        display(message, timeout)
        return
    status_bar_getter = getattr(window, "statusBar", None)
    if callable(status_bar_getter):
        status_bar = status_bar_getter()
        show_message = getattr(status_bar, "showMessage", None)
        if callable(show_message):
            show_message(message, timeout)


class BrowserWindow(QMainWindow):
    def __init__(self, tor_mode: bool = False, restored_session: Optional[dict] = None):
        super().__init__()
        self._window_handle_connected = None
        self._native_refresh_pending = False
        self._native_style_hwnd = 0
        self._edge_to_edge_frame_state = None
        self._snap_frame_sync_timer = QTimer(self)
        self._snap_frame_sync_timer.setSingleShot(True)
        self._snap_frame_sync_timer.setInterval(75)
        self._snap_frame_sync_timer.timeout.connect(self._sync_window_frame)
        self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint)
        # Per-pixel translucent top-level windows can leave Chromium/WebEngine
        # surfaces stale or transparent during native moves and monitor-DPI changes.
        # Keep non-Windows compositing unchanged, but use an opaque native surface on Windows.
        self.setAttribute(Qt.WA_TranslucentBackground, sys.platform != "win32")
        proxy_routing.load_exclude()
        self.tor_mode = bool(tor_mode)
        # Tor must configure its proxy before WebEngine profiles exist. In ordinary
        # mode the comparatively heavy proxy widget is created only when requested.
        self.proxy_panel = Window(self, None) if self.tor_mode else None
        self._pending_network_restart = None
        self._restored_session = restored_session if isinstance(restored_session, dict) else {}
        if self.tor_mode:
            proxy_widget = self.proxy_panel.proxyWidget
            try:
                if not proxy_widget.proxy.start():
                    raise RuntimeError("Could not start the local Tor proxy")
                proxy_routing.set_tor_routing(True)
                manage_proxy(None, "127.0.0.1", proxy_widget.proxy.port, "set")
            except Exception:
                proxy_routing.set_tor_routing(False)
                proxy_widget.proxy.stop()
                raise
        self.settings = Settings()
        self.settings.load_profile_settings()
        self.selected_profile = "Guest"
        requested_profile = self._restored_session.get("profile")
        if isinstance(requested_profile, str) and requested_profile in self.settings.profiles_list:
            self.selected_profile = requested_profile
        if self.settings.profiles_list and self.selected_profile not in self.settings.profiles_list:
            self.selected_profile = self.settings.profiles_list[0]
        self.settings.load(self.selected_profile)
        raw_tabs = self._restored_session.get("tabs", [])
        self._restored_tabs = [
            url[:8192]
            for url in raw_tabs[:50]
            if isinstance(url, str)
            and len(url) <= 8192
            and QUrl(url).isValid()
            and QUrl(url).scheme().lower() in {"http", "https", "arma", "about", "file"}
        ] if isinstance(raw_tabs, list) else []
        self._restored_active_index = self._restored_session.get("active_index", 0)
        if not isinstance(self._restored_active_index, int):
            self._restored_active_index = 0

        self._closed_tab_urls: Dict[tuple[str, bool], List[str]] = {}
        self._private_dashboard_notes: Dict[str, str] = {}
        self._private_dashboard_quick_notes: Dict[str, List[str]] = {}
        self._browser_shortcuts: Dict[QAction, list[QKeySequence]] = {}
        self._ui_shortcut_actions: set[QAction] = set()
        self._gaming_mode_active = False
        self._closing = False

        # History JSON can grow over time; defer disk parsing until the first
        # browser frame has had a chance to appear.
        self.history: Optional[History] = None

        self.storage_path = os.path.join(os.getcwd(), "profile_data")
        if not self.settings.private_mode:
            os.makedirs(self.storage_path, exist_ok=True)

        self._profiles: Dict[tuple[str, bool], QWebEngineProfile] = {}
        self._dashboard_handlers: Dict[int, DashboardSchemeHandler] = {}
        self._profile_default_user_agents: Dict[int, str] = {}
        self.profile = self._get_profile(self.selected_profile)
        self._apply_profile_settings(self.profile)
        self._download_managers = {}
        self._connected_download_managers: set[int] = set()
        self._setup_feature_managers()

        self.navbar = NavigationBar(self.settings.profiles_list, settings=self.settings)
        if self.bookmarks_bar is not None:
            # Keep bookmarks one click away without reserving a dedicated header row.
            self.navbar.insertWidget(self.navbar.profile_btn, self.bookmarks_bar)
        self.navbar.history = self.history.history if self.history else {}
        self.navbar.profile_selected.connect(self.on_profile_selected)
        self.navbar.new_tab_requested.connect(lambda: self.new_tab(self._new_tab_address()))

        self.tabbar = CustomTabBar()
        self.tabbar.setObjectName("browserTabBar")
        self.tabbar.new_tab_requested.connect(lambda: self.new_tab(self._new_tab_address()))
        self.tabbar.tab_changed.connect(self._on_tab_changed)
        # connect to our custom close flow
        self.tabbar.tab_closed.connect(self.request_close_tab)
        self.tabbar.tab_preview_requested.connect(self._show_tab_preview)
        self.tabbar.tab_context_requested.connect(self._show_tab_context_menu)
        self.tabbar.tab_reordered.connect(self._move_tab)

        self.views: List[QWebEngineView] = []
        self._page_load_overlays: Dict[QWebEngineView, _PageLoadOverlay] = {}
        self._status_overlays: Dict[object, _StatusMessageOverlay] = {}
        self._placeholders: Dict[QWebEngineView, QWidget] = {}
        self._snapshots: Dict[QWebEngineView, QPixmap] = {}
        self._recorded_history_urls: Dict[QWebEngineView, str] = {}
        self.current_index: int = -1
        self.view_container = QWidget()
        self.view_container.setObjectName("browserContentCard")
        self.view_container.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.view_container.setAutoFillBackground(False)
        # Hide the old bottom status strip; notifications now float over the page.
        self.statusBar().hide()
        self.view_layout = QVBoxLayout(self.view_container)
        # This is a layout host, not a visible card. Let the page meet the browser
        # shell directly so the viewport has one clean rounded edge, not two boxes.
        self.view_layout.setContentsMargins(0, 0, 0, 0)

        self._preview_label = QLabel(self)
        self._preview_label.setWindowFlags(Qt.ToolTip)
        self._preview_label.setStyleSheet("border:1px solid #222; background-color: white;")
        self._preview_label.setScaledContents(True)
        self._preview_label.hide()
        self._preview_animation = QPropertyAnimation(self._preview_label, b"windowOpacity")
        self._preview_animation.setDuration(180)

        root = QWidget()
        root.setObjectName("browserWindowRoot")
        layout = QVBoxLayout(root)
        layout.setContentsMargins(8, 8, 8, 8)
        self._root_layout = layout
        layout.setSpacing(0)
        shell = QFrame(root)
        shell.setObjectName("browserShell")
        self._shell = shell
        shell_layout = QVBoxLayout(shell)
        shell_layout.setContentsMargins(1, 1, 1, 1)
        shell_layout.setSpacing(0)
        self._shell_layout = shell_layout
        self.title_bar = CustomTitleBar(self)
        shell_layout.addWidget(self.title_bar)
        shell_layout.addWidget(self.navbar)

        # Keep tabs and the website viewport together in the left workspace.
        # The proxy is a sibling of this workspace, not a dock around the
        # outside of the custom browser shell.
        self.browser_workspace = QWidget(shell)
        self.browser_workspace.setObjectName("browserWorkspace")
        browser_workspace_layout = QVBoxLayout(self.browser_workspace)
        browser_workspace_layout.setContentsMargins(0, 0, 0, 0)
        browser_workspace_layout.setSpacing(0)
        browser_workspace_layout.addWidget(self.tabbar)

        self.content_row = QWidget(self.browser_workspace)
        content_layout = QHBoxLayout(self.content_row)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        self.downloads_panel = DownloadsPanel(self.download_manager, self.content_row)
        self.downloads_panel.close_requested.connect(self._close_downloads_panel)
        self.downloads_panel.mode_toggle_requested.connect(self._toggle_downloads_panel_mode)
        self.downloads_panel.open_manager_requested.connect(self.show_downloads)
        self.downloads_panel.state_changed.connect(self._on_downloads_panel_state_changed)
        self.downloads_panel.hide()
        self._downloads_panel_mode = "overlay"
        self._downloads_mode_transitioning = False
        self.downloads_overlay_dismiss = _DownloadsOverlayDismissArea(self.content_row)
        self.downloads_overlay_dismiss.setObjectName("downloadsOverlayDismissArea")
        self.downloads_overlay_dismiss.setStyleSheet(
            "QFrame#downloadsOverlayDismissArea { background: transparent; border: none; }"
        )
        self.downloads_overlay_dismiss.dismissed.connect(self._close_downloads_panel)
        self.downloads_overlay_dismiss.hide()
        self.downloads_splitter = QSplitter(Qt.Horizontal, self.content_row)
        self.downloads_splitter.setObjectName("downloadsSplitter")
        self.downloads_splitter.setHandleWidth(10)
        self.downloads_splitter.setChildrenCollapsible(True)
        self.downloads_splitter.setStretchFactor(0, 0)
        self.downloads_splitter.setStretchFactor(1, 1)
        # Splitter indices exist only after the child widgets have been inserted.
        self.downloads_splitter.addWidget(self.downloads_panel)
        self.downloads_splitter.addWidget(self.view_container)
        self.downloads_splitter.setCollapsible(0, True)
        self.downloads_splitter.setCollapsible(1, False)
        self.downloads_splitter.handle(1).setCursor(Qt.SplitHCursor)
        self.downloads_splitter.splitterMoved.connect(self._on_downloads_splitter_moved)
        self._downloads_panel_width = DownloadsPanel.PANEL_WIDTH
        self._downloads_splitter_animating = False
        self._downloads_splitter_animation = None
        content_layout.addWidget(self.downloads_splitter, 1)
        browser_workspace_layout.addWidget(self.content_row, 1)

        self.browser_proxy_splitter = QSplitter(Qt.Orientation.Horizontal, shell)
        self.browser_proxy_splitter.setObjectName("browserProxySplitter")
        self.browser_proxy_splitter.setChildrenCollapsible(False)
        self.browser_proxy_splitter.setHandleWidth(7)
        self.browser_proxy_splitter.setStretchFactor(0, 1)
        self.browser_proxy_splitter.setStretchFactor(1, 0)
        self.browser_proxy_splitter.addWidget(self.browser_workspace)

        self.dock = _ProxyPanelHost(self.browser_proxy_splitter)
        self.dock.setMinimumWidth(320)
        self.dock.setMaximumWidth(420)
        self._proxy_placeholder = None
        if self.proxy_panel is not None:
            self.dock.setWidget(self.proxy_panel)
        else:
            self._proxy_placeholder = QWidget(self.dock)
            self._proxy_placeholder.setObjectName("deferredProxyPlaceholder")
            self.dock.setWidget(self._proxy_placeholder)
        self.browser_proxy_splitter.addWidget(self.dock)
        self.browser_proxy_splitter.setSizes([
            max(1, self.settings.window_width - 340), 330
        ])
        self.dock.visibilityChanged.connect(self._on_proxy_visibility_changed)
        self.dock.setVisible(bool(self.settings.proxy_panel_visible))
        shell_layout.addWidget(self.browser_proxy_splitter, 1)
        layout.addWidget(shell, 1)
        self.setCentralWidget(root)
        QTimer.singleShot(0, self._collapse_downloads_splitter)
        self._setup_download_toast(root)
        self._bind_download_manager()

        self.resize(self.settings.window_width, self.settings.window_height)
        self.setWindowTitle("ARMA Browser")
        self.title_bar.title.setText(self.windowTitle())
        self.apply_theme()
        diagonal_down = Qt.SizeFDiagCursor
        diagonal_up = Qt.SizeBDiagCursor
        self._resize_handles = {
            "top": ResizeHandle(self, Qt.TopEdge, Qt.SizeVerCursor),
            "bottom": ResizeHandle(self, Qt.BottomEdge, Qt.SizeVerCursor),
            "left": ResizeHandle(self, Qt.LeftEdge, Qt.SizeHorCursor),
            "right": ResizeHandle(self, Qt.RightEdge, Qt.SizeHorCursor),
            "top_left": ResizeHandle(self, Qt.TopEdge | Qt.LeftEdge, diagonal_down),
            "top_right": ResizeHandle(self, Qt.TopEdge | Qt.RightEdge, diagonal_up),
            "bottom_left": ResizeHandle(self, Qt.BottomEdge | Qt.LeftEdge, diagonal_up),
            "bottom_right": ResizeHandle(self, Qt.BottomEdge | Qt.RightEdge, diagonal_down),
        }
        self._update_resize_handles()
        self._sync_window_frame()

        try:
            self.navbar.url_submitted.connect(self.navigate)
            self.navbar.home_clicked.connect(self.open_homepage)
            if hasattr(self.navbar, "back_btn"):
                self.navbar.back_btn.triggered.connect(lambda: self._do_on_current(lambda v: v.back()))
            if hasattr(self.navbar, "forward_btn"):
                self.navbar.forward_btn.triggered.connect(lambda: self._do_on_current(lambda v: v.forward()))
            if hasattr(self.navbar, "reload_btn"):
                self.navbar.reload_btn.triggered.connect(lambda: self._do_on_current(lambda v: v.reload()))
            if hasattr(self.navbar, "settings_btn"):
                self.navbar.settings_btn.triggered.connect(self.open_settings)
            if hasattr(self.navbar, "bookmark_requested"):
                self.navbar.bookmark_requested.connect(self._add_current_bookmark)
            if hasattr(self.navbar, "show_bookmarks_requested"):
                self.navbar.show_bookmarks_requested.connect(self.show_bookmarks)
            if hasattr(self.navbar, "show_history_requested"):
                self.navbar.show_history_requested.connect(self.show_history)
            if hasattr(self.navbar, "show_downloads_requested"):
                self.navbar.show_downloads_requested.connect(self.show_downloads)
            if hasattr(self.navbar, "downloads_panel_requested"):
                self.navbar.downloads_panel_requested.connect(self.toggle_downloads_panel)
            if hasattr(self.navbar, "open_external_requested"):
                self.navbar.open_external_requested.connect(self.open_current_page_externally)
            if hasattr(self.navbar, "reload_bypass_cache_requested"):
                self.navbar.reload_bypass_cache_requested.connect(
                    self.reload_current_page_bypassing_cache
                )
        except (AttributeError, RuntimeError):
            logger.exception("Could not connect one or more navigation actions")

        if self._restored_tabs:
            QTimer.singleShot(0, self._restore_startup_tabs)
        else:
            QTimer.singleShot(0, lambda: self.new_tab(self._startup_address()))
        if self.tor_mode:
            QTimer.singleShot(100, self.proxy_panel.proxyWidget._toggle)
        self._last_progress_ts = 0
        
        if self.settings.proxy_panel_visible:
            self._ensure_proxy_panel()
            self.browser_proxy_splitter.setSizes([
                max(1, self.width() - 350), 330
            ])
        self.navbar.proxy_panel_requested.connect(self.show_proxy)
        self.navbar.gaming_mode_toggled.connect(self._set_gaming_mode)
        self.navbar.site_connection_toggled.connect(self._set_current_site_direct)
        self.navbar.set_proxy_panel_state(self.dock.isVisible())
        self.navbar.set_downloads_panel_state(self.downloads_panel.is_open)
        self._update_proxy_menu_action(bool(self.settings.proxy_panel_visible))
        self._install_browser_shortcuts()
        QTimer.singleShot(120, self._initialize_deferred_history)

    def _initialize_deferred_history(self) -> None:
        """Load profile history after startup rendering, then refresh lightweight consumers."""
        if self._closing or self.history is not None:
            return
        if self.settings.private_mode or not self.settings.save_history:
            return
        self._refresh_history()
        self._sync_dashboard_tabs()

    def _restore_startup_tabs(self) -> None:
        for url in self._restored_tabs:
            self.new_tab(url, make_active=False)
        if self.views:
            index = max(0, min(self._restored_active_index, len(self.views) - 1))
            self.tabbar.set_active(index)

    def _request_network_mode(self, tor_mode: bool) -> None:
        if bool(tor_mode) == self.tor_mode:
            return
        destination = "Tor" if tor_mode else "normal direct browsing"
        answer = QMessageBox.question(
            self,
            "Restart ARMA Browser",
            f"ARMA Browser must restart to switch to {destination}. Open tabs will be restored. Continue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        urls = [
            view.url().toString()
            for view in self.views
            if view.url().isValid() and view.url().toString().strip()
        ]
        self._pending_network_restart = {
            "tor_mode": bool(tor_mode),
            "session": {
                "profile": self.selected_profile,
                "tabs": urls,
                "active_index": max(0, self.current_index),
            },
        }
        self.close()

    def _spawn_network_mode_restart(self, restart) -> bool:
        session_path = None
        try:
            descriptor, session_path = tempfile.mkstemp(
                prefix="arma-network-switch-", suffix=".json"
            )
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(restart["session"], stream, ensure_ascii=False)
                stream.flush()
                os.fsync(stream.fileno())

            original_args = [
                argument for argument in sys.argv[1:]
                if argument != "--tor-mode"
                and not argument.startswith(("--resume-session=", "--wait-for-parent="))
            ]
            if getattr(sys, "frozen", False):
                program = sys.executable
                arguments = original_args
            else:
                program = sys.executable
                arguments = [os.path.abspath(sys.argv[0]), *original_args]
            if restart["tor_mode"]:
                arguments.append("--tor-mode")
            arguments.extend((
                f"--resume-session={session_path}",
                f"--wait-for-parent={os.getpid()}",
            ))
            started, _process_id = QProcess.startDetached(program, arguments, os.getcwd())
            if started:
                return True
        except (OSError, TypeError, ValueError):
            logger.exception("Could not start the requested browser network mode")
        if session_path:
            try:
                os.remove(session_path)
            except OSError:
                logger.warning("Could not remove the unused session handoff file")
        return False

    def _ensure_proxy_panel(self):
        """Create the proxy controls on first use, not on every ordinary browser launch."""
        if self.proxy_panel is not None:
            return self.proxy_panel
        panel = Window(self, None)
        panel.profile = self.profile
        self.proxy_panel = panel
        placeholder = getattr(self, "_proxy_placeholder", None)
        self.dock.setWidget(panel)
        self._proxy_placeholder = None
        if placeholder is not None:
            placeholder.deleteLater()
        dark_mode = bool(getattr(getattr(self, "settings", None), "dark_mode", False))
        panel.apply_theme("dark" if dark_mode else "light")
        return panel

    def show_proxy(self):
        # QWidget.isHidden reflects the explicit panel toggle even while the
        # whole browser window is being shown or minimized.
        visible = self.dock.isHidden()
        if visible:
            self._ensure_proxy_panel()
            self.dock.setMinimumWidth(320)
            self.dock.setVisible(True)
            total_width = max(1, self.browser_proxy_splitter.width())
            pane_width = min(380, max(320, int(total_width * 0.32)))
            self.browser_proxy_splitter.setSizes([max(1, total_width - pane_width), pane_width])
        else:
            self.dock.setVisible(False)
        if hasattr(self, "navbar"):
            self.navbar.set_proxy_panel_state(self.dock.isVisible())
            self.dock.raise_()
        else:
            self.dock.setVisible(False)

    def toggle_downloads_panel(self) -> None:
        """Toggle the compact left downloads drawer; the toolbar icon mirrors it."""
        if getattr(self, "_downloads_mode_transitioning", False) or getattr(self, "_downloads_splitter_animating", False):
            return
        opening = not bool(self.downloads_panel.is_open)
        self._animate_downloads_panel(opening)

    def _on_downloads_panel_state_changed(self, opened: bool) -> None:
        navbar = getattr(self, "navbar", None)
        if navbar is not None:
            navbar.set_downloads_panel_state(opened)

    def toggle_theme(self) -> None:
        """Compatibility helper; the visible theme control lives in Settings."""
        previous = bool(self.settings.dark_mode)
        self.settings.dark_mode = not previous
        try:
            self.settings.save(self.selected_profile)
        except (OSError, ValueError, TypeError):
            self.settings.dark_mode = previous
            logger.exception("Could not save browser theme")
            _show_status_message(self, "Could not save browser theme.", 3500)
            return
        self.apply_theme()
        _show_status_message(self, "Dark theme enabled." if self.settings.dark_mode else "Light theme enabled.", 1800)

    def moveEvent(self, event):
        super().moveEvent(event)
        self._schedule_snap_frame_sync()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.WindowStateChange and hasattr(self, "title_bar"):
            self.title_bar.sync_maximize_button()
            self._update_resize_handles()
            self._sync_window_frame()
            # Qt can change native window styles during maximize/fullscreen transitions.
            self._queue_window_frame_refresh()

    def _is_edge_to_edge_geometry(self) -> bool:
        edge_to_edge = self.isMaximized() or self.isFullScreen()
        if sys.platform != "win32" or edge_to_edge:
            return bool(edge_to_edge)
        screen = self.screen()
        handle = self.windowHandle()
        if handle is not None and handle.screen() is not None:
            screen = handle.screen()
        return bool(
            screen is not None
            and _is_snap_aligned_geometry(
                self.frameGeometry(), screen.availableGeometry()
            )
        )

    def _apply_shell_corner_mask(self, edge_to_edge: bool | None = None) -> None:
        """Use native/widget antialiasing instead of a staircase-shaped QRegion mask."""
        shell = getattr(self, "_shell", None)
        if shell is None:
            return
        if edge_to_edge is None:
            edge_to_edge = self._is_edge_to_edge_geometry()
        # QRegion masks rasterize curved paths to hard pixel steps and clip native
        # child surfaces poorly. The stylesheet paints the shell curve; DWM handles
        # the outer Windows frame, while page corners use small antialiased overlays.
        shell.clearMask()
        for view in tuple(getattr(self, "views", ())):
            if isinstance(view, _RoundedWebView):
                view.set_rounded_corners(not edge_to_edge)

    def _sync_window_frame(self) -> None:
        if not hasattr(self, "_root_layout") or not hasattr(self, "_shell"):
            return
        edge_to_edge = self._is_edge_to_edge_geometry()
        if getattr(self, "_edge_to_edge_frame_state", None) == edge_to_edge:
            self._apply_shell_corner_mask(edge_to_edge)
            return
        self._edge_to_edge_frame_state = edge_to_edge
        margin = 0 if edge_to_edge else 8
        shell_margin = 0 if edge_to_edge else 1
        self._root_layout.setContentsMargins(margin, margin, margin, margin)
        shell_layout = getattr(self, "_shell_layout", None)
        if shell_layout is not None:
            shell_layout.setContentsMargins(shell_margin, shell_margin, shell_margin, shell_margin)
        self._shell.setProperty("edgeToEdge", edge_to_edge)
        self._shell.style().unpolish(self._shell)
        self._shell.style().polish(self._shell)
        self._shell.update()
        self._apply_shell_corner_mask(edge_to_edge)
        self._apply_native_window_corner_preference(edge_to_edge)

    def _schedule_snap_frame_sync(self) -> None:
        timer = getattr(self, "_snap_frame_sync_timer", None)
        if timer is not None and not self.isMaximized() and not self.isFullScreen():
            timer.start()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_shell_corner_mask()
        self._schedule_snap_frame_sync()
        self._update_resize_handles()
        self._position_download_toast()
        if getattr(self, "_downloads_panel_mode", "split") == "overlay":
            if getattr(self.downloads_panel, "is_open", False):
                dismiss_area = getattr(self, "downloads_overlay_dismiss", None)
                if dismiss_area is not None and dismiss_area.isVisible():
                    dismiss_area.setGeometry(self.content_row.rect())
                    dismiss_area.raise_()
                self.downloads_panel.setGeometry(
                    self.downloads_panel.x(), 0, self.downloads_panel.width(),
                    max(1, self.content_row.height())
                )
                self.downloads_panel.raise_()

    def _update_resize_handles(self) -> None:
        handles = getattr(self, "_resize_handles", None)
        if not handles:
            return
        width, height = self.width(), self.height()
        edge, corner = 8, 14
        geometries = {
            "top": QRect(corner, 0, max(0, width - 2 * corner), edge),
            "bottom": QRect(corner, max(0, height - edge), max(0, width - 2 * corner), edge),
            "left": QRect(0, corner, edge, max(0, height - 2 * corner)),
            "right": QRect(max(0, width - edge), corner, edge, max(0, height - 2 * corner)),
            "top_left": QRect(0, 0, corner, corner),
            "top_right": QRect(max(0, width - corner), 0, corner, corner),
            "bottom_left": QRect(0, max(0, height - corner), corner, corner),
            "bottom_right": QRect(
                max(0, width - corner), max(0, height - corner), corner, corner
            ),
        }
        hidden = self.isMaximized() or self.isFullScreen()
        for name, handle in handles.items():
            handle.setGeometry(geometries[name])
            handle.setVisible(not hidden)
        if not hidden:
            # Keep the resize targets above the web viewport and rounded shell.
            for handle in handles.values():
                handle.raise_()

    def _update_proxy_menu_action(self, visible: bool) -> None:
        self.navbar.proxy_panel_action.setText("Hide proxy panel" if visible else "Show proxy panel")

    def _on_proxy_visibility_changed(self, visible: bool) -> None:
        if visible and self.proxy_panel is None:
            self._ensure_proxy_panel()
        navbar = getattr(self, "navbar", None)
        if navbar is not None:
            navbar.set_proxy_panel_state(visible)
        self._update_proxy_menu_action(visible)
        if self._closing or bool(self.settings.proxy_panel_visible) == bool(visible):
            return
        self.settings.proxy_panel_visible = bool(visible)
        try:
            self.settings.save(self.selected_profile)
        except (OSError, ValueError, TypeError):
            logger.exception("Could not save proxy panel visibility")

    def _sync_site_connection_action(self, url: str) -> None:
        host = QUrl(url).host()
        try:
            host = proxy_routing.normalize_host(host) if host else ""
        except (ValueError, UnicodeError):
            host = ""
        direct = bool(host and host in proxy_routing.get_exclude())
        self.navbar.set_site_connection_state(host, direct)

    def _set_current_site_direct(self, direct: bool) -> None:
        view = self.current_view()
        if view is None:
            return
        host = view.url().host()
        try:
            host = proxy_routing.normalize_host(host)
            if direct:
                proxy_routing.add_to_exclude_hosts(host)
            else:
                proxy_routing.remove_exclude(host)
            proxy_routing.save_exclude()
        except (OSError, ValueError, UnicodeError) as error:
            logger.exception("Could not update direct route exception for %s", host)
            _show_status_message(self, f"Could not update site connection: {error}", 5000)
            self._sync_site_connection_action(view.url().toString())
            return
        self._sync_site_connection_action(view.url().toString())
        view.page().triggerAction(QWebEnginePage.WebAction.ReloadAndBypassCache)
        if self.tor_mode:
            message = (
                f"Retrying {host} with a direct connection"
                if direct else f"Restoring the configured Tor route for {host}"
            )
        else:
            message = (
                f"Direct-route preference saved for {host}; it applies when Tor routing is enabled."
            )
        _show_status_message(self, message, 3500)

    def _install_browser_shortcuts(self) -> None:
        """Install Chrome-style browser shortcuts that Gaming mode can pause."""
        for action, sequences in (
            (self.navbar.new_tab_action, ["Ctrl+T"]),
            (self.navbar.bookmark_action, ["Ctrl+D"]),
            (self.navbar.show_history_action, ["Ctrl+H"]),
            (self.navbar.show_downloads_action, ["Ctrl+J"]),
            (self.navbar.settings_btn, ["Ctrl+,"]),
            (self.navbar.back_btn, ["Alt+Left"]),
            (self.navbar.forward_btn, ["Alt+Right"]),
            (self.navbar.reload_btn, ["Ctrl+R", "F5"]),
            (self.navbar.reload_bypass_cache_action, ["Ctrl+Shift+R", "Ctrl+F5"]),
            (self.navbar.home_btn, ["Alt+Home"]),
        ):
            self._register_browser_shortcut(action, sequences, ui_action=True)

        self._add_shortcut("Close tab", ["Ctrl+W"], self._close_current_tab)
        self._add_shortcut("Reopen closed tab", ["Ctrl+Shift+T"], self._reopen_closed_tab)
        self._add_shortcut("Next tab", ["Ctrl+Tab", "Ctrl+PageDown"], lambda: self._cycle_tabs(1))
        self._add_shortcut(
            "Previous tab", ["Ctrl+Shift+Tab", "Ctrl+PageUp"], lambda: self._cycle_tabs(-1)
        )
        self._add_shortcut("Focus address bar", ["Ctrl+L", "Alt+D"], self.navbar._focus_url_bar)
        self._add_shortcut("Toggle fullscreen", ["F11"], self.toggle_fullscreen)
        for number in range(1, 9):
            self._add_shortcut(
                f"Switch to tab {number}",
                [f"Ctrl+{number}"],
                lambda tab_number=number: self._switch_to_tab(tab_number),
            )
        self._add_shortcut("Switch to last tab", ["Ctrl+9"], lambda: self._switch_to_tab(9))

    def _register_browser_shortcut(
        self, action: QAction, sequences: list[str], *, ui_action: bool = False,
        callback=None,
    ) -> None:
        key_sequences = [QKeySequence(sequence) for sequence in sequences]
        action.setShortcuts(key_sequences)
        action.setShortcutContext(Qt.WindowShortcut)
        if callback is not None:
            action.triggered.connect(lambda _checked=False: callback())
        self.addAction(action)
        self._browser_shortcuts[action] = key_sequences
        if ui_action:
            self._ui_shortcut_actions.add(action)

    def _add_shortcut(self, label: str, sequences: list[str], callback) -> QAction:
        action = QAction(label, self)
        self._register_browser_shortcut(action, sequences, callback=callback)
        return action

    def _set_gaming_mode(self, enabled: bool) -> None:
        self._gaming_mode_active = bool(enabled)
        for action, sequences in self._browser_shortcuts.items():
            action.setShortcuts([] if enabled else sequences)
            if action not in self._ui_shortcut_actions:
                action.setEnabled(not enabled)

        self.navbar.menu_button.setProperty("gamingMode", bool(enabled))
        self.navbar.menu_button.setToolTip(
            "Gaming mode is on — browser shortcuts are paused" if enabled else "Browser menu"
        )
        self.navbar.menu_button.style().unpolish(self.navbar.menu_button)
        self.navbar.menu_button.style().polish(self.navbar.menu_button)
        _show_status_message(self, 
            "Gaming mode on · browser shortcuts paused" if enabled else "Gaming mode off",
            2500,
        )

    def _close_current_tab(self) -> None:
        if self.current_index >= 0:
            self.request_close_tab(self.current_index)

    def _show_tab_context_menu(self, index: int, global_pos: QPoint) -> None:
        if index < 0 or index >= len(self.views):
            return
        view = self.views[index]
        menu = QMenu(self)
        new_tab_action = menu.addAction("New tab")
        reload_action = menu.addAction("Reload tab")
        duplicate_action = menu.addAction("Duplicate tab")
        copy_action = menu.addAction("Copy page address")
        page = view.page()
        mute_action = menu.addAction("Unmute tab" if page.isAudioMuted() else "Mute tab")
        menu.addSeparator()
        close_action = menu.addAction("Close tab")
        close_others_action = menu.addAction("Close other tabs")
        close_right_action = menu.addAction("Close tabs to the right")
        close_right_action.setEnabled(index < len(self.views) - 1)
        menu.addSeparator()
        reopen_action = menu.addAction("Reopen closed tab")
        reopen_action.setEnabled(bool(self._closed_tabs_for_current_session()))
        selected = menu.exec(global_pos)

        if selected is new_tab_action:
            self.new_tab()
        elif selected is reload_action:
            view.reload()
        elif selected is duplicate_action:
            self.new_tab(view.url().toString())
        elif selected is copy_action:
            QApplication.clipboard().setText(view.url().toString())
            _show_status_message(self, "Page address copied.", 2000)
        elif selected is mute_action:
            page.setAudioMuted(not page.isAudioMuted())
            _show_status_message(self, 
                "Tab audio unmuted." if not page.isAudioMuted() else "Tab audio muted.",
                2000,
            )
        elif selected is close_action and view in self.views:
            self.request_close_tab(self.views.index(view))
        elif selected is close_others_action:
            self._close_other_tabs(view)
        elif selected is close_right_action:
            self._close_tabs_to_right(view)
        elif selected is reopen_action:
            self._reopen_closed_tab()

    def _close_other_tabs(self, keep_view: QWebEngineView) -> None:
        for view in reversed(self.views.copy()):
            if view is not keep_view and view in self.views:
                self.request_close_tab(self.views.index(view))
        if keep_view in self.views:
            self.tabbar.set_active(self.views.index(keep_view))

    def _close_tabs_to_right(self, anchor_view: QWebEngineView) -> None:
        if anchor_view not in self.views:
            return
        anchor_index = self.views.index(anchor_view)
        targets = self.views[anchor_index + 1:].copy()
        for view in reversed(targets):
            if view in self.views:
                self.request_close_tab(self.views.index(view))

    def _reopen_closed_tab(self) -> None:
        closed_tabs = self._closed_tabs_for_current_session()
        if closed_tabs:
            self.new_tab(closed_tabs.pop())

    def _closed_tabs_for_current_session(self) -> List[str]:
        key = (self.selected_profile, bool(self.settings.private_mode))
        return self._closed_tab_urls.setdefault(key, [])

    def _cycle_tabs(self, offset: int) -> None:
        if self.views:
            self.tabbar.set_active((self.current_index + offset) % len(self.views))

    def _switch_to_tab(self, number: int) -> None:
        if self.views:
            index = len(self.views) - 1 if number == 9 else number - 1
            if index < len(self.views):
                self.tabbar.set_active(index)

    def show_history(self) -> None:
        self.navigate("arma://history/")

    def _refresh_history(self):
        if self.settings.private_mode or not self.settings.save_history:
            self.history = None
        else:
            self.history = History(self.selected_profile)
        if hasattr(self, "navbar"):
            self.navbar.history = self.history.history if self.history else {}

    def _get_profile(self, profile_name: str) -> QWebEngineProfile:
        private_mode = bool(self.settings.private_mode)
        key = (profile_name, private_mode)
        profile = self._profiles.get(key)
        if profile is None:
            if private_mode:
                # The unnamed profile is off-the-record and keeps storage in memory.
                profile = QWebEngineProfile(self)
            else:
                profile = QWebEngineProfile(profile_name, self)
            self._profiles[key] = profile
            handler = DashboardSchemeHandler(self, self)
            profile.installUrlSchemeHandler(DASHBOARD_SCHEME, handler)
            self._dashboard_handlers[id(profile)] = handler
        return profile

    def _apply_profile_settings(self, profile: QWebEngineProfile):
        private_mode = bool(self.settings.private_mode)
        persistent_cookies = (
            not private_mode and bool(self.settings.save_cookies)
        )
        policy = (
            QWebEngineProfile.ForcePersistentCookies
            if persistent_cookies
            else QWebEngineProfile.NoPersistentCookies
        )
        profile.setPersistentCookiesPolicy(policy)

        profile_key = id(profile)
        default_user_agent = self._profile_default_user_agents.setdefault(
            profile_key, profile.httpUserAgent()
        )
        if self.settings.site_compatibility_mode:
            compatible_user_agent = re.sub(
                r"\s+QtWebEngine/[^\s]+", "", default_user_agent, flags=re.IGNORECASE
            )
            profile.setHttpUserAgent(compatible_user_agent)
        else:
            profile.setHttpUserAgent(default_user_agent)

        if not private_mode:
            profile_dir = os.path.join(self.storage_path, self.selected_profile)
            os.makedirs(profile_dir, exist_ok=True)
            profile.setCachePath(os.path.join(profile_dir, "cache"))
            profile.setPersistentStoragePath(os.path.join(profile_dir, "storage"))
            download_dir = os.path.abspath(os.path.expanduser(self.settings.download_folder))
            os.makedirs(download_dir, exist_ok=True)
            profile.setDownloadPath(download_dir)

        settings = profile.settings()
        settings.setAttribute(QWebEngineSettings.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.LocalStorageEnabled, True)
        settings.setAttribute(QWebEngineSettings.FullScreenSupportEnabled, True)
        settings.setAttribute(QWebEngineSettings.ScrollAnimatorEnabled, True)

    def _setup_feature_managers(self):
        self.bookmarks_manager = None
        try:
            self.dashboard_manager = DashboardManager(self.selected_profile)
        except Exception:
            logger.exception("Could not initialize dashboard settings for profile %s", self.selected_profile)
            self.dashboard_manager = None
        if BookmarksManager is not None:
            try:
                self.bookmarks_manager = BookmarksManager(self.selected_profile)
            except Exception:
                logger.exception("Could not initialize bookmarks for profile %s", self.selected_profile)

        self.download_manager = None
        if DownloadManager is not None:
            try:
                manager_key = (self.selected_profile, bool(self.settings.private_mode))
                self.download_manager = self._download_managers.get(manager_key)
                if self.download_manager is None:
                    self.download_manager = DownloadManager(
                        self.selected_profile,
                        download_dir=self.settings.download_folder,
                    )
                    self._download_managers[manager_key] = self.download_manager
                self.download_manager.attach_profile(self.profile)
                self.download_manager.set_download_directory(self.settings.download_folder)
            except Exception:
                logger.exception("Could not initialize downloads for profile %s", self.selected_profile)
                self.download_manager = None

        self._bind_download_manager()

        if not hasattr(self, "bookmarks_bar"):
            self.bookmarks_bar = (
                BookmarksBar()
                if BookmarksBar is not None and self.bookmarks_manager is not None
                else None
            )
            if self.bookmarks_bar is not None:
                self.bookmarks_bar.url_activated.connect(self.navigate)
                self.bookmarks_bar.manage_requested.connect(self.show_bookmarks)
                self.bookmarks_bar.bookmark_context_requested.connect(
                    self._show_bookmark_context_menu
                )
        self._refresh_bookmarks()

    def _refresh_bookmarks(self):
        if self.bookmarks_bar is None or self.bookmarks_manager is None:
            return
        try:
            self.bookmarks_bar.set_bookmarks(self.bookmarks_manager.list_bookmarks())
        except Exception:
            logger.exception("Could not refresh bookmarks for profile %s", self.selected_profile)
            _show_status_message(self, "Could not refresh bookmarks.", 3000)
        self._sync_dashboard_tabs()

    def _update_bookmarks_bar_visibility(self, value=None) -> None:
        """Keep the bookmark menu available from the browser toolbar on every page."""
        bar = getattr(self, "bookmarks_bar", None)
        if bar is not None:
            bar.setVisible(True)

    def _show_bookmark_context_menu(self, bookmark: dict, global_pos: QPoint) -> None:
        """Show actions for a bookmark selected from the toolbar menu."""
        if self.bookmarks_manager is None:
            return
        menu = QMenu(self)
        open_current = menu.addAction("Open")
        open_new = menu.addAction("Open in new tab")
        copy_url = menu.addAction("Copy address")
        menu.addSeparator()
        edit_action = menu.addAction("Edit…")
        remove_action = menu.addAction("Remove bookmark")
        selected = menu.exec(global_pos)
        if selected is open_current:
            self.navigate(bookmark["url"])
        elif selected is open_new:
            self.new_tab(bookmark["url"])
        elif selected is copy_url:
            QApplication.clipboard().setText(bookmark["url"])
            _show_status_message(self, "Bookmark address copied.", 2000)
        elif selected is edit_action:
            self._edit_bookmark(bookmark)
        elif selected is remove_action:
            self._remove_bookmark(bookmark)

    def _edit_bookmark(self, bookmark: dict) -> None:
        title, accepted = QInputDialog.getText(
            self, "Edit bookmark", "Name:", QLineEdit.Normal, bookmark["title"]
        )
        if not accepted:
            return
        url, accepted = QInputDialog.getText(
            self, "Edit bookmark", "Address:", QLineEdit.Normal, bookmark["url"]
        )
        if not accepted:
            return
        try:
            self.bookmarks_manager.update_bookmark(bookmark["id"], title, url)
            self._refresh_bookmarks()
            current = self.current_view()
            if current is not None:
                self.navbar.set_bookmark_state(
                    self.bookmarks_manager.is_bookmarked(current.url().toString())
                )
        except (OSError, ValueError, TypeError) as error:
            _show_status_message(self, f"Could not update bookmark: {error}", 5000)

    def _remove_bookmark(self, bookmark: dict) -> None:
        try:
            if not self.bookmarks_manager.remove_bookmark(bookmark["id"]):
                _show_status_message(self, "This bookmark no longer exists.", 3000)
            self._refresh_bookmarks()
            current = self.current_view()
            if current is not None:
                self.navbar.set_bookmark_state(
                    self.bookmarks_manager.is_bookmarked(current.url().toString())
                )
        except (OSError, ValueError, TypeError) as error:
            _show_status_message(self, f"Could not remove bookmark: {error}", 5000)

    def _add_current_bookmark(self, *args):
        if self.bookmarks_manager is None:
            _show_status_message(self, "Bookmarks are unavailable.", 3000)
            return
        view = self.current_view()
        if view is None:
            return
        url = view.url().toString()
        title = view.title().strip() or url
        try:
            bookmark = self.bookmarks_manager.get_bookmark_for_url(url)
            if bookmark is not None:
                self.bookmarks_manager.remove_bookmark(bookmark["id"])
            else:
                self.bookmarks_manager.add_bookmark(title, url)
            self._refresh_bookmarks()
            self.navbar.set_bookmark_state(self.bookmarks_manager.is_bookmarked(url))
        except Exception:
            logger.exception("Could not toggle bookmark for %s", url)
            _show_status_message(self, "Could not update bookmark.", 3000)

    def show_bookmarks(self, *args):
        if BookmarksDialog is None or self.bookmarks_manager is None:
            _show_status_message(self, "Bookmarks are unavailable.", 3000)
            return
        try:
            dialog = BookmarksDialog(self.bookmarks_manager, self)
            dialog.url_activated.connect(self.navigate)
            dialog.exec()
            self._refresh_bookmarks()
        except Exception:
            logger.exception("Could not open bookmarks")
            _show_status_message(self, "Could not open bookmarks.", 3000)

    def show_downloads(self, *args):
        self.navigate("arma://downloads/")

    def _bind_download_manager(self) -> None:
        panel = getattr(self, "downloads_panel", None)
        if panel is not None:
            panel.set_manager(self.download_manager)
        manager = self.download_manager
        if manager is None or id(manager) in self._connected_download_managers:
            return
        try:
            manager.download_started.connect(self._on_download_started)
            self._connected_download_managers.add(id(manager))
        except (AttributeError, RuntimeError):
            logger.exception("Could not connect download notifications")

    def _on_download_started(self, download_id: str, source_page) -> None:
        if self._closing:
            return
        # Keep the lightweight progress drawer for new downloads. The header's
        # Downloads button opens the full manager at arma://downloads/.
        self._animate_downloads_panel(True)
        manager = self.download_manager
        record = next(
            (item for item in manager.get_downloads() if item.get("id") == download_id),
            {},
        ) if manager is not None else {}
        self._show_download_toast(str(record.get("file_name") or "Your file is being downloaded"))
        QTimer.singleShot(0, lambda page=source_page: self._close_download_source_tab(page))

    def _close_download_source_tab(self, page) -> None:
        if page is None or self._closing:
            return
        for index, view in enumerate(tuple(self.views)):
            try:
                if view.page() is page:
                    self.request_close_tab(index)
                    return
            except RuntimeError:
                continue

    def _close_downloads_panel(self) -> None:
        self._animate_downloads_panel(False)
        if not self.views:
            self.new_tab(DASHBOARD_URL)

    def _collapse_downloads_splitter(self) -> None:
        """Give the full content width back to the active website."""
        if not hasattr(self, "downloads_splitter"):
            return
        total = max(1, self.downloads_splitter.width() - self.downloads_splitter.handleWidth())
        self.downloads_splitter.setSizes([0, total])

    def _stop_downloads_panel_animation(self) -> None:
        animation = self._downloads_splitter_animation
        if animation is not None:
            animation.stop()
            animation.deleteLater()
            self._downloads_splitter_animation = None
        self._downloads_splitter_animating = False

    def _downloads_split_target_width(self, available: int) -> int:
        """Keep the panel useful while preserving as much page width as possible."""
        available = max(1, int(available))
        preferred = min(
            self.downloads_panel.maximumWidth(),
            max(245, int(self._downloads_panel_width)),
        )
        page_reserve = min(280, max(140, available // 3))
        return max(1, min(preferred, available - 1, available - page_reserve))

    def _animate_downloads_split_width(self, start_width: int, end_width: int, on_finished) -> None:
        """Animate splitter width without recreating or navigating the active page."""
        splitter = self.downloads_splitter
        available = max(2, splitter.width() - splitter.handleWidth())
        start = max(0, min(int(start_width), available - 1))
        end = max(0, min(int(end_width), available - 1))
        self._stop_downloads_panel_animation()
        self._downloads_splitter_animating = True

        animation = QVariantAnimation(self)
        animation.setDuration(240)
        animation.setEasingCurve(QEasingCurve.OutCubic)
        animation.setStartValue(start)
        animation.setEndValue(end)

        def apply_width(value) -> None:
            width = max(0, min(int(value), available - 1))
            splitter.setSizes([width, max(1, available - width)])

        def finish() -> None:
            apply_width(end)
            self._downloads_splitter_animation = None
            self._downloads_splitter_animating = False
            animation.deleteLater()
            on_finished()

        animation.valueChanged.connect(apply_width)
        animation.finished.connect(finish)
        self._downloads_splitter_animation = animation
        animation.start()

    def _animate_downloads_panel_geometry(self, start_rect: QRect, end_rect: QRect, on_finished) -> None:
        panel = self.downloads_panel
        self._stop_downloads_panel_animation()
        self._downloads_splitter_animating = True
        animation = QPropertyAnimation(panel, b"geometry", self)
        animation.setDuration(240)
        animation.setEasingCurve(QEasingCurve.OutCubic)
        animation.setStartValue(start_rect)
        animation.setEndValue(end_rect)

        def finish() -> None:
            panel.setGeometry(end_rect)
            self._downloads_splitter_animation = None
            self._downloads_splitter_animating = False
            animation.deleteLater()
            on_finished()

        animation.finished.connect(finish)
        self._downloads_splitter_animation = animation
        animation.start()

    def _show_downloads_overlay_dismiss_area(self) -> None:
        area = getattr(self, "downloads_overlay_dismiss", None)
        if area is None:
            return
        area.setGeometry(self.content_row.rect())
        area.show()
        area.raise_()

    def _hide_downloads_overlay_dismiss_area(self) -> None:
        area = getattr(self, "downloads_overlay_dismiss", None)
        if area is not None:
            area.hide()

    def _finish_downloads_mode_transition(self) -> None:
        self._downloads_mode_transitioning = False
        self.downloads_panel.mode_button.setEnabled(True)
        self.downloads_panel.close_button.setEnabled(True)

    def _finish_mode_switch_to_split(self, width: int) -> None:
        panel = self.downloads_panel
        panel.setMinimumWidth(245)
        panel.open()
        panel.show()
        self._downloads_panel_width = max(245, int(width))
        self._finish_downloads_mode_transition()

    def _finish_mode_switch_to_overlay(self, width: int) -> None:
        """Float the same panel above the full-width page after the split shrinks away."""
        panel = self.downloads_panel
        splitter = self.downloads_splitter
        total = max(1, splitter.width() - splitter.handleWidth())
        splitter.setSizes([0, total])

        panel.hide()
        panel.setMinimumWidth(245)
        panel.setParent(self.content_row)
        self._downloads_panel_mode = "overlay"
        panel.set_docked(False)
        row_height = max(1, self.content_row.height())
        panel.setGeometry(QRect(-width, 0, width, row_height))
        self._show_downloads_overlay_dismiss_area()
        panel.open()
        panel.raise_()
        self._animate_downloads_panel_geometry(
            panel.geometry(),
            QRect(0, 0, width, row_height),
            self._finish_mode_switch_overlay_animation,
        )

    def _finish_mode_switch_overlay_animation(self) -> None:
        self.downloads_panel.raise_()
        self._finish_downloads_mode_transition()

    def _switch_downloads_panel_mode(self, next_mode: str) -> None:
        """Switch drawer layout in-place; never close, reload, or replace a browser tab."""
        if next_mode not in {"overlay", "split"} or next_mode == self._downloads_panel_mode:
            return
        if self._downloads_mode_transitioning:
            return

        panel = self.downloads_panel
        splitter = self.downloads_splitter
        self._stop_downloads_panel_animation()
        self._downloads_mode_transitioning = True
        panel.mode_button.setEnabled(False)
        panel.close_button.setEnabled(False)
        panel.set_docked(next_mode == "split")

        if next_mode == "split":
            # Reinsert the existing drawer next to the existing view container. The
            # QWebEngineView and its page object are never touched by this transition.
            self._hide_downloads_overlay_dismiss_area()
            panel.hide()
            panel.setMinimumWidth(0)
            if panel.parent() is not splitter:
                panel.setParent(splitter)
                splitter.insertWidget(0, panel)
            self._downloads_panel_mode = "split"
            available = max(2, splitter.width() - splitter.handleWidth())
            splitter.setSizes([0, available])
            panel.open()
            target = self._downloads_split_target_width(available)
            self._animate_downloads_split_width(
                0, target, lambda target_width=target: self._finish_mode_switch_to_split(target_width)
            )
            return

        sizes = splitter.sizes()
        current_width = sizes[0] if sizes else panel.width()
        available = max(2, splitter.width() - splitter.handleWidth())
        overlay_width = min(
            panel.maximumWidth(),
            max(280, int(self._downloads_panel_width)),
            max(280, self.content_row.width() - 96),
        )
        panel.setMinimumWidth(0)
        self._animate_downloads_split_width(
            min(max(0, current_width), available - 1),
            0,
            lambda width=overlay_width: self._finish_mode_switch_to_overlay(width),
        )

    def _toggle_downloads_panel_mode(self) -> None:
        # Ignore rapid repeat clicks while an opening/closing or mode transition
        # animation owns the panel geometry and splitter sizes.
        if self._downloads_mode_transitioning or self._downloads_splitter_animating:
            return
        next_mode = "split" if self._downloads_panel_mode == "overlay" else "overlay"
        if self.downloads_panel.is_open:
            self._switch_downloads_panel_mode(next_mode)
        else:
            self._downloads_panel_mode = next_mode
            self.downloads_panel.set_docked(next_mode == "split")
        _show_status_message(self, 
            "Downloads will now stay beside the page." if next_mode == "split"
            else "Downloads will now overlay the page.", 2500
        )

    def _animate_downloads_overlay(self, opening: bool) -> None:
        panel = self.downloads_panel
        row = self.content_row
        row_height = max(1, row.height())
        panel_width = min(
            panel.maximumWidth(),
            max(280, int(self._downloads_panel_width)),
            max(280, row.width() - 96),
        )

        if opening:
            panel.setMinimumWidth(0)
            # Collapse while both splitter children still exist, then float the panel.
            # The web page is neither captured nor blurred; only the panel's own glass
            # material is softened.
            self._collapse_downloads_splitter()
            panel.setParent(row)
            panel.setGeometry(QRect(-panel_width, 0, panel_width, row_height))
            self._show_downloads_overlay_dismiss_area()
            panel.open()
            panel.raise_()
            self._animate_downloads_panel_geometry(
                panel.geometry(),
                QRect(0, 0, panel_width, row_height),
                lambda width=panel_width: self._finish_downloads_panel_animation(True, width),
            )
        else:
            panel.close_panel()
            self._animate_downloads_panel_geometry(
                panel.geometry(),
                QRect(-max(1, panel.width()), 0, max(1, panel.width()), row_height),
                lambda width=panel_width: self._finish_downloads_panel_animation(False, width),
            )

    def _animate_downloads_panel(self, opening: bool) -> None:
        panel = self.downloads_panel
        if self._downloads_panel_mode == "overlay":
            if opening and panel.is_open:
                return
            if not opening and not panel.is_open:
                return
            self._animate_downloads_overlay(opening)
            return

        splitter = self.downloads_splitter
        if opening and panel.is_open:
            return
        if not opening and not panel.is_open and splitter.sizes()[0] == 0:
            return

        available = max(2, splitter.width() - splitter.handleWidth())
        if opening:
            panel.setMinimumWidth(0)
            if panel.parent() is not splitter:
                panel.setParent(splitter)
                splitter.insertWidget(0, panel)
            panel.open()
            splitter.setSizes([0, available])
            target_width = self._downloads_split_target_width(available)
            self._animate_downloads_split_width(
                0, target_width,
                lambda width=target_width: self._finish_downloads_panel_animation(True, width),
            )
        else:
            panel.close_panel()
            panel.setMinimumWidth(0)
            sizes = splitter.sizes()
            start_width = sizes[0] if sizes else panel.width()
            self._animate_downloads_split_width(
                start_width, 0, lambda: self._finish_downloads_panel_animation(False, 0)
            )

    def _finish_downloads_panel_animation(self, opened: bool, width: int) -> None:
        panel = self.downloads_panel
        if opened:
            panel.setMinimumWidth(245)
            panel.open()
            panel.show()
            self._downloads_panel_width = max(245, int(width))
            if self._downloads_panel_mode == "overlay":
                panel.setGeometry(QRect(0, 0, width, max(1, self.content_row.height())))
                panel.raise_()
        else:
            panel.hide()
            if self._downloads_panel_mode == "overlay":
                self._hide_downloads_overlay_dismiss_area()
                panel.setParent(self.downloads_splitter)
                self.downloads_splitter.insertWidget(0, panel)
                panel.setMinimumWidth(0)
            total = max(1, self.downloads_splitter.width() - self.downloads_splitter.handleWidth())
            self.downloads_splitter.setSizes([0, total])
            panel.setMinimumWidth(245)
        self._downloads_splitter_animation = None
        self._downloads_splitter_animating = False

    def _on_downloads_splitter_moved(self, _position: int, _index: int) -> None:
        if self._downloads_splitter_animating:
            return
        sizes = self.downloads_splitter.sizes()
        if not sizes:
            return
        if sizes[0] > 0:
            self._downloads_panel_width = min(self.downloads_panel.maximumWidth(), sizes[0])
            self.downloads_panel.open()
        else:
            self.downloads_panel.close_panel()
            self.downloads_panel.hide()
            if not self.views:
                QTimer.singleShot(0, self._close_empty_browser)

    def _close_empty_browser(self) -> None:
        if not self.views:
            self.new_tab(DASHBOARD_URL)

    def _setup_download_toast(self, parent: QWidget) -> None:
        self.download_toast = QFrame(parent)
        self.download_toast.setObjectName("downloadToast")
        self.download_toast.setFixedWidth(350)
        toast_layout = QHBoxLayout(self.download_toast)
        toast_layout.setContentsMargins(14, 11, 10, 11)
        toast_layout.setSpacing(10)
        toast_text = QVBoxLayout()
        toast_text.setSpacing(3)
        self.download_toast_title = QLabel("Download started", self.download_toast)
        self.download_toast_title.setObjectName("downloadToastTitle")
        self.download_toast_file = QLabel("", self.download_toast)
        self.download_toast_file.setObjectName("downloadToastFile")
        self.download_toast_file.setWordWrap(True)
        toast_text.addWidget(self.download_toast_title)
        toast_text.addWidget(self.download_toast_file)
        toast_layout.addLayout(toast_text, 1)
        view_button = QPushButton("View", self.download_toast)
        view_button.setObjectName("downloadToastButton")
        view_button.clicked.connect(self.show_downloads)
        toast_layout.addWidget(view_button)
        self.download_toast_effect = QGraphicsOpacityEffect(self.download_toast)
        self.download_toast_effect.setOpacity(0.0)
        self.download_toast.setGraphicsEffect(self.download_toast_effect)
        self.download_toast_animation = QPropertyAnimation(self.download_toast_effect, b"opacity", self)
        self.download_toast_animation.setDuration(180)
        self.download_toast_timer = QTimer(self)
        self.download_toast_timer.setSingleShot(True)
        self.download_toast_timer.timeout.connect(self._hide_download_toast)
        self.download_toast_animation.finished.connect(self._finish_download_toast_animation)
        self.download_toast.hide()

    def _position_download_toast(self) -> None:
        toast = getattr(self, "download_toast", None)
        root = self.centralWidget()
        if toast is None or root is None:
            return
        toast.move(max(12, root.width() - toast.width() - 18), 50)

    def _show_download_toast(self, file_name: str) -> None:
        self.download_toast_file.setText(file_name)
        self._position_download_toast()
        self.download_toast.show()
        self.download_toast.raise_()
        self.download_toast_animation.stop()
        self.download_toast_animation.setStartValue(self.download_toast_effect.opacity())
        self.download_toast_animation.setEndValue(1.0)
        self.download_toast_animation.start()
        self.download_toast_timer.start(4500)

    def _hide_download_toast(self) -> None:
        if not hasattr(self, "download_toast_animation"):
            return
        self.download_toast_animation.stop()
        self.download_toast_animation.setStartValue(self.download_toast_effect.opacity())
        self.download_toast_animation.setEndValue(0.0)
        self.download_toast_animation.start()

    def _finish_download_toast_animation(self) -> None:
        if self.download_toast_effect.opacity() <= 0.01:
            self.download_toast.hide()

    def _capture_snapshot(self, view: QWebEngineView):
        if view not in self.views:
            return
        try:
            pix = view.grab()
            if pix and not pix.isNull():
                self._snapshots[view] = pix
        except RuntimeError:
            logger.debug("Skipped snapshot for a view being destroyed", exc_info=True)

    def _make_placeholder(self, url_text: str = "") -> QWidget:
        """Build a full-size, theme-aware first-paint screen for a new tab."""
        dark = bool(getattr(self.settings, "dark_mode", True))
        background = "#101722" if dark else "#edf2f8"
        ink = "#f3f6fb" if dark else "#1e293b"
        muted = "#98a6bb" if dark else "#65758b"
        accent = "#8db8ff" if dark else "#3979d6"

        screen = QWidget(self.view_container)
        screen.setObjectName("pageLoadingScreen")
        screen.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        screen.setStyleSheet(f"""
            QWidget#pageLoadingScreen {{ background: {background}; color: {ink}; }}
            QLabel#loadingBrand {{
                color: {accent}; font-size: 14px; font-weight: 700;
                letter-spacing: 2px; padding: 8px 0;
            }}
            QLabel#loadingTitle {{ color: {ink}; font-size: 23px; font-weight: 600; }}
            QLabel#loadingDetail {{ color: {muted}; font-size: 12px; }}
            QProgressBar#loadingProgress {{
                background: {'#263244' if dark else '#dce5f1'};
                border: none; border-radius: 3px; min-height: 4px; max-height: 4px;
            }}
            QProgressBar#loadingProgress::chunk {{
                background: {accent}; border-radius: 3px;
            }}
            QPushButton#loadingRetry {{
                color: {ink}; background: {'#1d2939' if dark else '#ffffff'};
                border: 1px solid {'#344256' if dark else '#ced8e6'};
                border-radius: 11px; padding: 8px 18px; font-size: 12px;
            }}
            QPushButton#loadingRetry:hover {{
                border-color: {accent}; background: {'#26364d' if dark else '#f7faff'};
            }}
        """)

        layout = QVBoxLayout(screen)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(11)
        layout.addStretch(1)

        brand = QLabel("ARMA")
        brand.setObjectName("loadingBrand")
        brand.setAlignment(Qt.AlignCenter)
        layout.addWidget(brand)

        title = QLabel("Getting things ready")
        title.setObjectName("loadingTitle")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        detail_text = "Preparing your start page" if self._is_dashboard_address(url_text) else "Connecting to the website…"
        detail = QLabel(detail_text)
        detail.setObjectName("loadingDetail")
        detail.setAlignment(Qt.AlignCenter)
        detail.setWordWrap(True)
        layout.addWidget(detail)

        progress = QProgressBar()
        progress.setObjectName("loadingProgress")
        progress.setRange(0, 0)
        progress.setTextVisible(False)
        progress.setFixedWidth(190)
        progress.setFixedHeight(4)
        progress.setAlignment(Qt.AlignCenter)
        layout.addWidget(progress, 0, Qt.AlignHCenter)

        retry = QPushButton("Try again")
        retry.setObjectName("loadingRetry")
        retry.setCursor(Qt.PointingHandCursor)
        retry.setVisible(False)
        layout.addWidget(retry, 0, Qt.AlignHCenter)

        layout.addStretch(1)
        screen.loading_title_label = title
        screen.loading_detail_label = detail
        screen.loading_progress = progress
        screen.retry_button = retry
        screen._load_error = False
        return screen

    def _startup_address(self) -> str:
        return DASHBOARD_URL if self.settings.startup_page == "dashboard" else self.settings.homepage

    def _new_tab_address(self) -> str:
        return DASHBOARD_URL if self.settings.new_tab_page == "dashboard" else self.settings.homepage

    def open_homepage(self) -> None:
        self.navigate(self.settings.homepage)

    @staticmethod
    def _internal_host(value: str | QUrl | None) -> str | None:
        if value is None:
            return None
        url = value if isinstance(value, QUrl) else QUrl(str(value))
        if url.scheme().lower() != "arma":
            return None
        host = url.host().lower()
        return host if host in INTERNAL_PAGE_HOSTS else None

    @staticmethod
    def _is_internal_address(value: str | QUrl | None) -> bool:
        return BrowserWindow._internal_host(value) is not None

    @staticmethod
    def _is_dashboard_address(value: str | QUrl | None) -> bool:
        return BrowserWindow._internal_host(value) == "dashboard"

    def _dashboard_state(self) -> dict:
        manager = getattr(self, "dashboard_manager", None)
        state = manager.export() if manager is not None else {}
        state.update({
            "dark_mode": bool(self.settings.dark_mode),
            "default_search_engine": self.settings.default_search_engine,
            "bookmarks": [],
            "recent": [],
            "closed": [],
        })
        if self.settings.private_mode:
            state["notes"] = self._private_dashboard_notes.get(self.selected_profile, "")
            state["quick_notes"] = self._private_dashboard_quick_notes.get(self.selected_profile, [])
        try:
            if self.bookmarks_manager is not None:
                state["bookmarks"] = self.bookmarks_manager.list_bookmarks()[:24]
        except (AttributeError, OSError, RuntimeError):
            logger.exception("Could not load dashboard bookmarks")
        if self.history is not None and self.settings.save_history and not self.settings.private_mode:
            try:
                recent = (
                    (
                        f"{visits[-1].get('date', '')} {visits[-1].get('time', '')}"
                        if isinstance(visits, list) and visits and isinstance(visits[-1], dict)
                        else "",
                        {"title": link, "url": link},
                    )
                    for link, visits in self.history.history.items()
                    if isinstance(link, str) and link.startswith(("http://", "https://"))
                )
                state["recent"] = [
                    item for _, item in heapq.nlargest(6, recent, key=lambda item: item[0])
                ]
            except (AttributeError, TypeError):
                logger.exception("Could not prepare dashboard history")
        state["closed"] = [
            {"title": url, "url": url}
            for url in reversed(self._closed_tabs_for_current_session()[-6:])
            if url.startswith(("http://", "https://"))
        ]
        return state

    @staticmethod
    @lru_cache(maxsize=1)
    def _dashboard_template() -> str:
        asset_dir = Path(__file__).resolve().parent / "dashboard"
        page_html = (asset_dir / "index.html").read_text(encoding="utf-8")
        css = (asset_dir / "dashboard.css").read_text(encoding="utf-8")
        script = (asset_dir / "dashboard.js").read_text(encoding="utf-8")

        page_html = page_html.replace(
            '<link rel="stylesheet" href="dashboard.css">', f"<style>{css}</style>"
        )
        page_html = page_html.replace(
            '<script src="dashboard.js"></script>', f"<script>{script}</script>"
        )
        return page_html

    def _dashboard_document(self) -> bytes:
        page_html = BrowserWindow._dashboard_template()
        state_json = json.dumps(self._dashboard_state(), ensure_ascii=False, separators=(",", ":"))
        state_json = state_json.replace("</", "<\\/")
        page_html = page_html.replace("{{DASHBOARD_STATE}}", state_json)
        return page_html.encode("utf-8")

    def _load_internal_page(self, view: QWebEngineView, address: str | QUrl) -> None:
        """Load only an app-owned ARMA page and attach its restricted local bridge."""
        target = address if isinstance(address, QUrl) else QUrl(str(address))
        host = self._internal_host(target)
        if host is None:
            raise ValueError("Only supported ARMA internal pages can be loaded here.")
        if host == "dashboard" and self.dashboard_manager is None:
            _show_status_message(self, "Dashboard preferences are unavailable.", 4000)
            return
        page = view.page()
        page._enable_dashboard_bridge()
        page.settings().setAttribute(
            QWebEngineSettings.LocalContentCanAccessRemoteUrls, host == "dashboard"
        )
        normalized_url = QUrl(f"arma://{host}/")
        view.setUrl(normalized_url)

    def _load_dashboard(self, view: QWebEngineView) -> None:
        self._load_internal_page(view, DASHBOARD_URL)

    def _internal_page_document(self, host: str) -> bytes:
        if host not in INTERNAL_PAGE_HOSTS or host == "dashboard":
            raise ValueError("Unsupported ARMA internal page.")
        return render_internal_page(self, host).encode("utf-8")

    def _sync_dashboard_page(self, page: QWebEnginePage) -> None:
        if not getattr(page, "_dashboard_active", False):
            return
        try:
            current_url = page.url()
        except RuntimeError:
            return
        if self._internal_host(current_url) != "dashboard":
            return
        state_json = json.dumps(self._dashboard_state(), ensure_ascii=False, separators=(",", ":"))
        state_json = state_json.replace("</", "<\\/")
        script = (
            "if (location.protocol === 'arma:' && location.host === 'dashboard' && "
            f"window.updateDashboardState) window.updateDashboardState({state_json});"
        )
        page.runJavaScript(script)

    def _handle_internal_page_action(
        self, page: BrowserPage, view: QWebEngineView, host: str, action: str, payload: dict
    ) -> None:
        """Handle an allowlisted internal-page intent after validating its payload."""
        incremental_setting = action == "set_browser_setting"
        setting_name = ""
        try:
            if action == "navigate_internal":
                target_host = payload.get("host")
                if not isinstance(target_host, str) or target_host.lower() not in INTERNAL_PAGE_HOSTS:
                    raise ValueError("That internal page is not available.")
                self._load_internal_page(view, f"arma://{target_host.lower()}/")
                return

            if action == "browse_download_folder":
                current = str(self.settings.download_folder or os.path.expanduser("~"))
                directory = QFileDialog.getExistingDirectory(
                    self, "Choose download folder", os.path.abspath(os.path.expanduser(current))
                )
                if directory:
                    page.runJavaScript("window.setDownloadFolder && window.setDownloadFolder(" + json.dumps(directory) + ");")
                return

            if incremental_setting:
                setting_name = payload.get("name")
                setting_value = payload.get("value")
                allowed_setting_names = {
                    "homepage", "startup_page", "new_tab_page", "default_search_engine",
                    "download_folder", "dark_mode", "private_mode", "save_history",
                    "save_cookies", "hardware_acceleration", "webgpu_enabled",
                    "site_compatibility_mode", "proxy_panel_visible",
                }
                if not isinstance(setting_name, str) or setting_name not in allowed_setting_names:
                    raise ValueError("That browser setting is not supported.")
                payload = {
                    "homepage": self.settings.homepage,
                    "startup_page": self.settings.startup_page,
                    "new_tab_page": self.settings.new_tab_page,
                    "default_search_engine": self.settings.default_search_engine,
                    "download_folder": self.settings.download_folder,
                    "dark_mode": bool(self.settings.dark_mode),
                    "private_mode": bool(self.settings.private_mode),
                    "save_history": bool(self.settings.save_history),
                    "save_cookies": bool(self.settings.save_cookies),
                    "hardware_acceleration": bool(self.settings.hardware_acceleration),
                    "webgpu_enabled": bool(self.settings.webgpu_enabled),
                    "site_compatibility_mode": bool(self.settings.site_compatibility_mode),
                    "proxy_panel_visible": bool(self.settings.proxy_panel_visible),
                }
                payload[setting_name] = setting_value
                action = "save_browser_settings"

            if action == "save_browser_settings":
                homepage = payload.get("homepage")
                if not isinstance(homepage, str) or not homepage.strip() or len(homepage) > 8192:
                    raise ValueError("Enter a valid homepage address.")
                homepage = homepage.strip()
                homepage_url = QUrl(homepage)
                if homepage_url.scheme().lower() == "arma":
                    if self._internal_host(homepage_url) is None:
                        raise ValueError("Only supported ARMA internal pages can be used as the homepage.")
                    homepage = f"arma://{homepage_url.host().lower()}/"
                elif not (
                    homepage_url.isValid()
                    and homepage_url.scheme().lower() in {"http", "https"}
                    and bool(homepage_url.host())
                    and not homepage_url.userInfo()
                ):
                    raise ValueError("The homepage must be a website URL or ARMA internal page.")

                startup_page = payload.get("startup_page")
                new_tab_page = payload.get("new_tab_page")
                if startup_page not in {"dashboard", "homepage"} or new_tab_page not in {"dashboard", "homepage"}:
                    raise ValueError("Startup and new-tab pages must be selected from the available options.")
                engine = payload.get("default_search_engine")
                allowed_engines = {
                    "https://www.google.com/search?q=",
                    "https://duckduckgo.com/?q=",
                    "https://www.bing.com/search?q=",
                }
                current_engine = str(self.settings.default_search_engine or "")
                if not isinstance(engine, str) or len(engine) > 2048:
                    raise ValueError("Choose a valid search engine.")
                if engine not in allowed_engines and engine != current_engine:
                    raise ValueError("That search engine is not supported in this settings view.")
                folder = payload.get("download_folder")
                if not isinstance(folder, str) or not folder.strip() or len(folder) > 4096:
                    raise ValueError("Choose a valid download folder.")
                folder = os.path.abspath(os.path.expanduser(folder.strip()))
                boolean_fields = (
                    "dark_mode", "private_mode", "save_history", "save_cookies",
                    "hardware_acceleration", "webgpu_enabled",
                    "site_compatibility_mode", "proxy_panel_visible",
                )
                for name in boolean_fields:
                    if type(payload.get(name)) is not bool:
                        raise ValueError(f"Invalid value for {name.replace('_', ' ')}.")

                old_private = bool(self.settings.private_mode)
                old_hardware = bool(self.settings.hardware_acceleration)
                settings_field_names = (
                    "homepage", "startup_page", "new_tab_page", "default_search_engine",
                    "download_folder", *boolean_fields,
                )
                old_values = {name: getattr(self.settings, name) for name in settings_field_names}
                candidate = copy.copy(self.settings)
                candidate.homepage = homepage
                candidate.startup_page = startup_page
                candidate.new_tab_page = new_tab_page
                candidate.default_search_engine = engine
                candidate.download_folder = folder
                for name in boolean_fields:
                    setattr(candidate, name, payload[name])
                candidate.save(self.selected_profile)
                for name in settings_field_names:
                    setattr(self.settings, name, getattr(candidate, name))
                changed_fields = {
                    name for name in settings_field_names
                    if old_values[name] != getattr(candidate, name)
                }

                if "hardware_acceleration" in changed_fields:
                    Settings.configure_hardware_acceleration(bool(self.settings.hardware_acceleration))
                if "webgpu_enabled" in changed_fields:
                    Settings.configure_webgpu(bool(self.settings.webgpu_enabled))
                if old_private != bool(self.settings.private_mode):
                    # Private mode changes the QWebEngine profile and its owned managers.
                    # A profile switch is the only preference edit that requires rebuilding them.
                    self.change_profile(self.selected_profile)
                else:
                    if changed_fields & {"save_cookies", "site_compatibility_mode"}:
                        self._apply_profile_settings(self.profile)
                    if "save_history" in changed_fields:
                        self._refresh_history()
                    if "download_folder" in changed_fields and self.download_manager is not None:
                        try:
                            self.download_manager.set_download_directory(folder)
                        except (AttributeError, OSError, TypeError, ValueError):
                            logger.exception("Could not update the active download directory")

                if "proxy_panel_visible" in changed_fields:
                    self.dock.setVisible(bool(self.settings.proxy_panel_visible))
                if "dark_mode" in changed_fields:
                    self.apply_theme()
                elif changed_fields & {"save_history", "private_mode"}:
                    self._sync_dashboard_tabs()
                if changed_fields & {"hardware_acceleration", "webgpu_enabled"}:
                    changed_graphics = changed_fields & {"hardware_acceleration", "webgpu_enabled"}
                    if changed_graphics == {"hardware_acceleration", "webgpu_enabled"}:
                        message = "Saved. Restart ARMA Browser to apply graphics settings."
                    elif "webgpu_enabled" in changed_graphics:
                        message = (
                            "Saved. Restart ARMA Browser to disable WebGPU context creation."
                            if not self.settings.webgpu_enabled else
                            "Saved. Restart ARMA Browser to enable WebGPU."
                        )
                    else:
                        message = "Saved. Restart ARMA Browser to fully apply hardware acceleration."
                    _show_status_message(self, message, 6500)
                else:
                    message = "Setting saved." if incremental_setting else "Browser settings saved."
                    _show_status_message(self, message, 2200)
                if incremental_setting:
                    page.runJavaScript(
                        "window.armaSettingSaved && window.armaSettingSaved("
                        + json.dumps(setting_name) + ", "
                        + json.dumps(message) + ", false);"
                    )
                    if view in self.views and (setting_name == "private_mode" and old_private != bool(self.settings.private_mode)):
                        self._load_internal_page(view, "arma://settings/")
                elif view in self.views:
                    self._load_internal_page(view, "arma://settings/")
                return

            if host == "history":
                history = self.history
                if history is None or self.settings.private_mode or not self.settings.save_history:
                    raise ValueError("History is disabled for this profile.")
                if action == "history_open":
                    target = payload.get("url")
                    if not isinstance(target, str) or len(target) > 8192:
                        raise ValueError("That history address is invalid.")
                    target_url = QUrl(target)
                    if target_url.scheme().lower() not in {"http", "https"} or not target_url.host():
                        raise ValueError("Only recorded website addresses can be opened from history.")
                    if view is self.current_view():
                        self.navigate(target)
                    else:
                        view.setUrl(target_url)
                    return
                elif action == "history_delete_url":
                    target = payload.get("url")
                    if not isinstance(target, str) or len(target) > 8192:
                        raise ValueError("That history address is invalid.")
                    history.delete(link=target)
                elif action == "history_delete_visit":
                    target = payload.get("url")
                    date = payload.get("date")
                    visit_time = payload.get("time")
                    index = payload.get("index")
                    if (
                        not isinstance(target, str) or len(target) > 8192
                        or not isinstance(date, str) or len(date) > 32
                        or not isinstance(visit_time, str) or len(visit_time) > 32
                        or type(index) is not int or index < 0
                    ):
                        raise ValueError("That history entry is invalid.")
                    history.delete_visit(target, date, visit_time, index)
                elif action == "history_clear":
                    history.clear()
                else:
                    return
                self.navbar.history = history.history
                _show_status_message(self, "History updated.", 2000)
                self._load_internal_page(view, "arma://history/")
                return

            if host == "downloads":
                manager = self.download_manager
                if manager is None:
                    raise ValueError("The download manager is unavailable.")
                if action == "downloads_refresh":
                    self._load_internal_page(view, "arma://downloads/")
                    return
                records = manager.get_downloads()
                download_id = payload.get("id")
                if action == "downloads_clear_finished":
                    manager.clear_finished()
                else:
                    if not isinstance(download_id, str) or len(download_id) > 256:
                        raise ValueError("That download entry is invalid.")
                    record = next((item for item in records if str(item.get("id")) == download_id), None)
                    if record is None:
                        raise ValueError("That download entry no longer exists.")
                    state = str(record.get("state", "")).lower()
                    if action == "downloads_cancel":
                        if state not in {"requested", "downloading"} or not manager.cancel(download_id):
                            raise ValueError("This download can no longer be cancelled.")
                    elif action == "downloads_pause":
                        if state not in {"requested", "downloading"} or not manager.pause(download_id):
                            raise ValueError("This download cannot be paused.")
                    elif action == "downloads_resume":
                        if state not in {"requested", "downloading"} or not manager.resume(download_id):
                            raise ValueError("This download cannot be resumed.")
                    elif action == "downloads_open":
                        if state != "completed" or not manager.open_file(download_id):
                            raise ValueError("The completed file could not be opened.")
                    elif action == "downloads_folder":
                        if state != "completed" or not manager.open_folder(download_id):
                            raise ValueError("The download folder could not be opened.")
                    elif action == "downloads_remove":
                        if state not in {"completed", "cancelled", "failed"} or not manager.remove_download(download_id):
                            raise ValueError("This download entry cannot be removed yet.")
                    elif action == "downloads_delete_file":
                        if state != "completed" or not manager.delete_download_file(download_id):
                            raise ValueError("The file could not be deleted. Only files inside the configured download folder can be deleted.")
                    else:
                        return
                _show_status_message(self, "Download list updated.", 2000)
                self._load_internal_page(view, "arma://downloads/")
                return
        except (OSError, ValueError, TypeError, RuntimeError) as error:
            logger.info("Internal page action %s was rejected: %s", action, error)
            _show_status_message(self, str(error), 5500)
            if incremental_setting and setting_name:
                page.runJavaScript(
                    "window.armaSettingSaved && window.armaSettingSaved("
                    + json.dumps(setting_name) + ", "
                    + json.dumps(str(error)) + ", true);"
                )
            else:
                page.runJavaScript("window.armaToast && window.armaToast(" + json.dumps(str(error)) + ");")

    def _handle_dashboard_action(self, page: BrowserPage, action_url: QUrl) -> None:
        if not getattr(page, "_dashboard_active", False):
            return
        try:
            page_url = page.url()
        except RuntimeError:
            return
        if page_url.scheme().lower() != "arma" or page_url.host().lower() not in INTERNAL_PAGE_HOSTS:
            return
        host = page_url.host().lower()
        query = QUrlQuery(action_url)
        action = query.queryItemValue("action")
        raw_payload = query.queryItemValue("payload")
        if len(raw_payload) > 80_000:
            return
        try:
            payload = json.loads(raw_payload) if raw_payload else {}
        except (json.JSONDecodeError, TypeError):
            return
        if not isinstance(payload, dict):
            return
        view = next((candidate for candidate in self.views if candidate.page() is page), None)
        if view is None:
            return
        if host != "dashboard":
            self._handle_internal_page_action(page, view, host, action, payload)
            return
        if self.dashboard_manager is None:
            return
        try:
            if action in {"open", "open_new", "search", "reopen"}:
                if action == "reopen":
                    target = payload.get("url")
                    closed_tabs = self._closed_tabs_for_current_session()
                    if isinstance(target, str) and target in closed_tabs:
                        closed_tabs.remove(target)
                        self.new_tab(target)
                        self._sync_dashboard_tabs()
                    return
                if action == "search":
                    query_text = payload.get("query")
                    engine = payload.get("engine", "default")
                    allowed_engines = {
                        "default", "https://www.google.com/search?q=",
                        "https://duckduckgo.com/?q=", "https://www.bing.com/search?q=",
                    }
                    if not isinstance(query_text, str) or not query_text.strip():
                        return
                    if engine not in allowed_engines:
                        engine = "default"
                    search_engine = self.settings.default_search_engine if engine == "default" else engine
                    address = resolve_address_input(query_text, search_engine)
                else:
                    target = payload.get("url")
                    if not isinstance(target, str):
                        return
                    address = resolve_address_input(target, self.settings.default_search_engine)
                if action == "open_new":
                    self.new_tab(address)
                else:
                    if view is self.current_view():
                        self.navigate(address)
                    else:
                        view.setUrl(QUrl(address))
                return

            manager = self.dashboard_manager
            if action == "save_shortcuts":
                manager.set_shortcuts(payload.get("shortcuts"))
            elif action == "save_notes":
                notes = payload.get("notes", "")
                if not isinstance(notes, str):
                    raise ValueError("Notes must be text.")
                quick_notes = payload.get("quick_notes", [])
                if (
                    not isinstance(quick_notes, list)
                    or len(quick_notes) > 10
                    or any(not isinstance(note, str) for note in quick_notes)
                ):
                    raise ValueError("You can save up to 10 text notes.")
                quick_notes = [note[:5000] for note in quick_notes]
                if self.settings.private_mode:
                    self._private_dashboard_notes[self.selected_profile] = notes[:10_000]
                    self._private_dashboard_quick_notes[self.selected_profile] = quick_notes
                else:
                    manager.update({"notes": notes[:10_000], "quick_notes": quick_notes})
            elif action == "update_preferences":
                allowed = {
                    "overlay", "blur", "glass", "accent", "clock_24h",
                    "show_seconds", "animations", "density", "widgets", "widget_order",
                    "widget_sizes", "focus_minutes", "break_minutes",
                }
                manager.update({key: value for key, value in payload.items() if key in allowed})
            elif action == "set_wallpaper":
                manager.set_wallpaper(payload.get("wallpaper", ""))
            elif action == "cycle_wallpaper":
                manager.cycle_wallpaper()
            elif action == "import_wallpaper":
                source, _ = QFileDialog.getOpenFileName(
                    self, "Choose dashboard wallpaper", os.path.expanduser("~"),
                    "Images (*.jpg *.jpeg *.png *.webp)",
                )
                if source:
                    manager.import_wallpaper(source)
            elif action == "reset_preferences":
                manager.reset()
            else:
                return
            self._sync_dashboard_page(page)
        except (OSError, ValueError, TypeError) as error:
            logger.info("Dashboard action %s was rejected: %s", action, error)
            page.runJavaScript(
                "window.showDashboardToast && window.showDashboardToast(" +
                json.dumps(str(error)) + ");"
            )

    def _sync_dashboard_tabs(self) -> None:
        for view in tuple(getattr(self, "views", ())):
            if getattr(view.page(), "_dashboard_active", False):
                self._sync_dashboard_page(view.page())

    def new_tab(self, url: Optional[str] = None, make_active: bool = True) -> int:
        """Create one aligned tab, placeholder, view, and page before loading."""
        raw_url = url.toString() if isinstance(url, QUrl) else (url if url is not None else self._new_tab_address())
        internal_host = self._internal_host(raw_url)
        is_dashboard = internal_host == "dashboard"
        if internal_host is not None:
            resolved_url = f"arma://{internal_host}/"
        else:
            try:
                resolved_url = resolve_address_input(raw_url, self.settings.default_search_engine)
            except URLInputError as exc:
                logger.warning("Rejected tab URL %r: %s", raw_url, exc)
                _show_status_message(self, str(exc), 5000)
                resolved_url = "about:blank"
        url_q = QUrl(resolved_url)

        view = _RoundedWebView(self.view_container)
        view.set_corner_color("#22272e" if self.settings.dark_mode else "#e9edf3")
        view.set_rounded_corners(not self._is_edge_to_edge_geometry())
        view.setVisible(False)
        self._page_load_overlays[view] = _PageLoadOverlay(view)
        # WebEngine owns a separate compositor surface; transparency and animated
        # graphics effects can make that surface blink during its first paint.
        page = BrowserPage(self, self.profile, view)
        view.setPage(page)
        self._connect_page(view, page)

        placeholder = self._make_placeholder(url_q.toString())
        placeholder.retry_button.clicked.connect(view.reload)
        self.views.append(view)
        self._placeholders[view] = placeholder
        self.view_layout.addWidget(placeholder)
        self.view_layout.addWidget(view)

        index = len(self.views) - 1
        self.tabbar.add_tab("New Tab", make_active=False)
        if make_active or self.current_index < 0:
            self.tabbar.set_active(index)
        else:
            self._set_tab_visibility()

        if internal_host is not None:
            self._load_internal_page(view, url_q)
        else:
            view.setUrl(url_q)
        return index

    def _connect_page(self, view: QWebEngineView, page: QWebEnginePage) -> None:
        page.titleChanged.connect(
            lambda title, v=view, p=page: self._on_title_changed(title, v)
            if self._page_is_current(v, p) else None
        )
        page.iconChanged.connect(
            lambda icon, v=view, p=page: self._on_icon_changed(icon, v)
            if self._page_is_current(v, p) else None
        )
        page.urlChanged.connect(
            lambda url, v=view, p=page: self._on_view_url_changed(url, v)
            if self._page_is_current(v, p) else None
        )
        page.loadStarted.connect(
            lambda v=view, p=page: self._on_load_started(v)
            if self._page_is_current(v, p) else None
        )
        page.loadingChanged.connect(
            lambda info, v=view, p=page: self._on_loading_changed(info, v, p)
            if self._page_is_current(v, p) else None
        )
        page.loadProgress.connect(
            lambda progress, v=view, p=page: self._on_load_progress(progress, v)
            if self._page_is_current(v, p) else None
        )
        page.loadFinished.connect(
            lambda ok, v=view, p=page: self._on_load_finished_with_swap(ok, v, p)
            if self._page_is_current(v, p) else None
        )
        page.fullScreenRequested.connect(
            lambda request, v=view, p=page: self._handle_page_fullscreen(request, v, p)
        )
        page.windowCloseRequested.connect(
            lambda v=view, p=page: self.request_close_tab(self.views.index(v))
            if self._page_is_current(v, p) else None
        )

    def _page_is_current(self, view: QWebEngineView, page: QWebEnginePage) -> bool:
        return view in self.views and view.page() is page

    def request_close_tab(self, index: int):
        """Remove a tab and all of its widgets as one GUI-thread transition."""
        if index < 0 or index >= len(self.views):
            return

        closing_view = self.views.pop(index)
        closed_url = closing_view.url().toString().strip()
        if closed_url and closed_url != "about:blank":
            closed_tabs = self._closed_tabs_for_current_session()
            closed_tabs.append(closed_url)
            del closed_tabs[:-10]
        was_active = index == self.current_index
        self.tabbar.remove_tab(index, activate=False)
        placeholder = self._placeholders.pop(closing_view, None)
        if placeholder is not None:
            self.view_layout.removeWidget(placeholder)
            placeholder.hide()
            placeholder.deleteLater()

        self.view_layout.removeWidget(closing_view)
        getattr(self, "_page_load_overlays", {}).pop(closing_view, None)
        closing_view.stop()
        closing_view.hide()
        closing_view.deleteLater()
        self._snapshots.pop(closing_view, None)
        self._recorded_history_urls.pop(closing_view, None)

        if not self.views:
            self.current_index = -1
            self.new_tab(DASHBOARD_URL)
            return

        if was_active:
            next_index = min(index, len(self.views) - 1)
        elif index < self.current_index:
            next_index = self.current_index - 1
        else:
            next_index = self.current_index
        self.current_index = -1
        self.tabbar.set_active(next_index)
        self._activate(next_index)
        self._sync_dashboard_tabs()

    def close_tab(self, index: int):
        """
        Backwards-compatible external call — redirect to request_close_tab
        """
        self.request_close_tab(index)

    def _activate(self, index: int):
        if index < 0 or index >= len(self.views):
            return
        prev_index = self.current_index
        if prev_index is not None and prev_index != -1 and prev_index != index:
            self._capture_snapshot(self.views[prev_index])

        self.current_index = index
        self._set_tab_visibility()
        view = self.views[index]
        if view.page().isLoading() and self._placeholders.get(view) is None:
            self._show_page_load_overlay(view)
        else:
            overlay = self._page_load_overlays.get(view)
            if overlay is not None:
                overlay.hide()
        self._update_bookmarks_bar_visibility(view.url())
        self.navbar.url_bar.setText(view.url().toString())
        self._sync_site_connection_action(view.url().toString())
        if self.bookmarks_manager is not None:
            self.navbar.set_bookmark_state(self.bookmarks_manager.is_bookmarked(view.url().toString()))
        self._update_navigation_actions(view)
        title_bar = getattr(self, "title_bar", None)
        set_page_title = getattr(title_bar, "set_page_title", None)
        page_title = view.title()
        if callable(set_page_title):
            set_page_title(page_title or view.url().host() or "New tab")
        set_window_title = getattr(self, "setWindowTitle", None)
        if callable(set_window_title):
            set_window_title(f"{page_title} — ARMA Browser" if page_title else "ARMA Browser")
        self.tabbar.set_active(index)

    def _set_tab_visibility(self):
        for index, view in enumerate(self.views):
            placeholder = self._placeholders.get(view)
            is_active = index == self.current_index
            if placeholder is not None:
                placeholder.setVisible(is_active)
                view.setVisible(is_active and view.graphicsEffect() is not None)
            else:
                view.setVisible(is_active)

    def _on_tab_changed(self, index: int):
        if index >= 0 and index != self.current_index:
            self._activate(index)

    def _move_tab(self, from_index: int, to_index: int) -> None:
        """Keep the view order aligned with the visual tab order during drag."""
        if (
            from_index < 0 or to_index < 0
            or from_index >= len(self.views) or to_index >= len(self.views)
            or from_index == to_index
        ):
            return
        active_view = self.current_view()
        moved_view = self.views.pop(from_index)
        self.views.insert(to_index, moved_view)
        if active_view in self.views:
            self.current_index = self.views.index(active_view)

    def _on_icon_changed(self, icon: QIcon, view: QWebEngineView) -> None:
        if view in self.views:
            self.tabbar.set_icon(self.views.index(view), icon)

    def _on_title_changed(self, title: str, view: QWebEngineView):
        if view not in self.views:
            return
        self.tabbar.set_title(self.views.index(view), title)
        if view is self.current_view():
            window_title = f"{title} — ARMA Browser" if title else "ARMA Browser"
            set_window_title = getattr(self, "setWindowTitle", None)
            if callable(set_window_title):
                set_window_title(window_title)
            title_bar = getattr(self, "title_bar", None)
            set_page_title = getattr(title_bar, "set_page_title", None)
            if callable(set_page_title):
                set_page_title(title or view.url().host() or "New tab")

    def _on_view_url_changed(self, url: QUrl, view: QWebEngineView):
        if view is self.current_view():
            self._update_bookmarks_bar_visibility(url)
            if not view.title():
                title_bar = getattr(self, "title_bar", None)
                set_page_title = getattr(title_bar, "set_page_title", None)
                if callable(set_page_title):
                    set_page_title(url.host() or "New tab")
            self.navbar.url_bar.setText(url.toString())
            self._sync_site_connection_action(url.toString())
            if self.bookmarks_manager is not None:
                self.navbar.set_bookmark_state(self.bookmarks_manager.is_bookmarked(url.toString()))
            self._update_navigation_actions(view)

    def _on_load_started(self, view: QWebEngineView):
        if view not in self.views:
            return
        self.tabbar.set_loading(self.views.index(view), True)
        placeholder = self._placeholders.get(view)
        if placeholder is not None:
            placeholder._load_error = False
            placeholder.loading_title_label.setText("Getting things ready")
            placeholder.loading_detail_label.setText(
                "Preparing your start page"
                if self._is_dashboard_address(view.url())
                else "Connecting to the website…"
            )
            placeholder.loading_progress.show()
            placeholder.retry_button.hide()
        if view is self.current_view():
            if self._placeholders.get(view) is None:
                self._show_page_load_overlay(view)
            else:
                overlay = self._page_load_overlays.get(view)
                if overlay is not None:
                    overlay.hide()

    def _on_loading_changed(self, info, view: QWebEngineView, page: QWebEnginePage):
        """Report real main-frame network failures without treating cancelled loads as errors."""
        try:
            if info.status() != QWebEngineLoadingInfo.LoadStatus.LoadFailedStatus:
                return
            if view is not self.current_view():
                return
            failed_url = info.url().toString()
            current_url = view.url().toString()
            # Chromium reports ERR_ABORTED for ordinary back/forward/reload supersession.
            if info.errorCode() == -3:
                return
            message = (info.errorString() or "").strip()
            if not message:
                message = "The website could not be reached. Check the connection and try again."
            tabbar = getattr(self, "tabbar", None)
            if view in self.views and tabbar is not None:
                tabbar.set_loading(self.views.index(view), False)
            overlay = getattr(self, "_page_load_overlays", {}).get(view)
            if overlay is not None:
                overlay.hide()
            placeholder = self._placeholders.get(view)
            if placeholder is None and view in self.views:
                # A page can fail after an earlier successful load removed its placeholder.
                # Put the same retryable surface in front of that view for subsequent failures.
                placeholder = self._make_placeholder(failed_url or current_url)
                placeholder.retry_button.clicked.connect(view.reload)
                self._placeholders[view] = placeholder
                self.view_layout.insertWidget(max(0, self.view_layout.indexOf(view)), placeholder)
                view.hide()
            if placeholder is not None:
                placeholder._load_error = True
                placeholder.loading_title_label.setText("This page didn’t load")
                placeholder.loading_detail_label.setText(message)
                placeholder.loading_progress.hide()
                placeholder.retry_button.show()
            _show_status_message(self, f"Could not load page: {message}", 6000)
        except (AttributeError, RuntimeError):
            logger.debug("Could not inspect a WebEngine loading failure", exc_info=True)

    def _page_load_overlay_for(self, view: QWebEngineView):
        return getattr(self, "_page_load_overlays", {}).get(view)

    def _show_page_load_overlay(self, view: QWebEngineView, progress: int | None = None) -> None:
        if view not in getattr(self, "views", ()) or view is not self.current_view():
            return
        # The full-page first-load placeholder already presents progress of its own.
        if getattr(self, "_placeholders", {}).get(view) is not None:
            return
        overlay = self._page_load_overlay_for(view)
        if overlay is not None:
            overlay.show_loading(progress)

    def _hide_page_load_overlay_if_current(self, view: QWebEngineView) -> None:
        if (
            view in getattr(self, "views", ())
            and view is self.current_view()
            and not view.page().isLoading()
        ):
            overlay = self._page_load_overlay_for(view)
            if overlay is not None:
                overlay.hide()

    def _on_load_progress(self, progress: int, view):
        if view is not self.current_view():
            return

        now = time.monotonic()
        if now - getattr(self, "_last_progress_ts", 0.0) < 0.05:  # 50ms
            return
        self._last_progress_ts = now
        self._show_page_load_overlay(view, progress)


    def _on_load_finished_with_swap(self, ok: bool, view: QWebEngineView, page: QWebEnginePage):
        if not self._page_is_current(view, page):
            return
        if view in self.views:
            self.tabbar.set_loading(self.views.index(view), False)

        if ok and self._is_dashboard_address(view.url()):
            page.runJavaScript(
                "document.documentElement.classList.add('dashboard-ready');"
            )
        if view is self.current_view() and self._placeholders.get(view) is None:
            self._show_page_load_overlay(view, 100)
            # Keep the completed percentage briefly, then hide it without shifting
            # the page viewport or reserving an empty progress row.
            QTimer.singleShot(220, lambda v=view: self._hide_page_load_overlay_if_current(v))
            # loadFinished(False) also occurs for cancelled or superseded navigations.
            # A real main-frame network failure is reported by _on_loading_changed.

        if ok and self.history is not None:
            url_text = view.url().toString()
            if url_text.startswith(("http://", "https://")) and self._recorded_history_urls.get(view) != url_text:
                try:
                    self.history.add(url_text)
                    self._recorded_history_urls[view] = url_text
                except OSError:
                    logger.exception("Could not save browsing history for %s", url_text)
        self._sync_dashboard_tabs()

        self._update_navigation_actions(view)
        QTimer.singleShot(100, lambda v=view: self._capture_snapshot(v))
        placeholder = self._placeholders.get(view)
        if placeholder is None:
            view.setVisible(view is self.current_view())
            return
        if not ok and page.isLoading() and not getattr(placeholder, "_load_error", False):
            # A superseded navigation can finish with ok=False while its replacement
            # is already loading. Keep the placeholder until the active request settles.
            return
        if not ok and getattr(placeholder, "_load_error", False):
            # Keep the useful, retryable loading surface instead of fading to a blank page.
            placeholder.setVisible(view is self.current_view())
            view.hide()
            return

        # Switch immediately once the page has a first usable frame. Applying
        # QGraphicsOpacityEffect to QWebEngineView forces the Chromium compositor
        # through an extra surface transition and can blank the whole page briefly.
        view.setGraphicsEffect(None)
        view.setVisible(view is self.current_view())
        self._placeholders.pop(view, None)
        self.view_layout.removeWidget(placeholder)
        placeholder.deleteLater()
        self._set_tab_visibility()


    def _update_navigation_actions(self, view: QWebEngineView) -> None:
        if view is not self.current_view():
            return
        history = view.history()
        self.navbar.back_btn.setEnabled(history.canGoBack())
        self.navbar.forward_btn.setEnabled(history.canGoForward())

    def _handle_page_fullscreen(self, request, view: QWebEngineView, page: QWebEnginePage):
        if not self._page_is_current(view, page):
            request.reject()
            return
        self.handle_fullscreen(request)

    def _show_tab_preview(self, index: int):
        if index < 0 or index >= len(self.views) or index == self.current_index:
            return

        view = self.views[index]
        pix = self._snapshots.get(view)
        if pix is None:
            try:
                pix = view.grab()
            except RuntimeError:
                logger.debug("Skipped preview for a view being destroyed", exc_info=True)
                pix = None

        if pix is None or pix.isNull():
            pix = QPixmap(TAB_WIDTH * 2, 120)
            pix.fill(Qt.gray)

        scaled = pix.scaled(320, 220, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self._preview_label.setPixmap(scaled)
        self._preview_label.adjustSize()

        try:
            tab_widget = self.tabbar.tabs[index]
            global_pos = tab_widget.mapToGlobal(tab_widget.rect().bottomLeft())
            x = global_pos.x()
            y = global_pos.y() + 8

            screen_rect = self.screen().availableGeometry()
            if x + self._preview_label.width() > screen_rect.right():
                x = screen_rect.right() - self._preview_label.width() - 8
            if y + self._preview_label.height() > screen_rect.bottom():
                y = global_pos.y() - self._preview_label.height() - 8
            if x < screen_rect.left():
                x = screen_rect.left() + 8
            if y < screen_rect.top():
                y = screen_rect.top() + 8

            self._preview_label.move(x, y)
        except RuntimeError:
            center = self.mapToGlobal(self.rect().center())
            self._preview_label.move(center + QPoint(-160, 40))

        self._preview_label.setWindowOpacity(0.0)
        self._preview_label.show()
        self._preview_animation.stop()
        self._preview_animation.setStartValue(0.0)
        self._preview_animation.setEndValue(1.0)
        self._preview_animation.start()
        QTimer.singleShot(1500, lambda: self._fade_out_preview())

    def _fade_out_preview(self):
        self._preview_animation.stop()
        self._preview_animation.setStartValue(1.0)
        self._preview_animation.setEndValue(0.0)
        self._preview_animation.start()
        QTimer.singleShot(200, self._preview_label.hide)

    def _do_on_current(self, func):
        v = self.current_view()
        if v:
            try:
                func(v)
            except RuntimeError:
                logger.exception("Navigation action failed because its page was destroyed")

    def current_view(self) -> Optional[QWebEngineView]:
        if 0 <= self.current_index < len(self.views):
            return self.views[self.current_index]
        return None

    def change_profile(self, profile_name: str):
        self.selected_profile = profile_name
        self._refresh_history()
        self.profile = self._get_profile(profile_name)
        self._apply_profile_settings(self.profile)
        if self.proxy_panel is not None:
            self.proxy_panel.profile = self.profile
        self._setup_feature_managers()

        for view in list(self.views):
            old_page = view.page()
            current_url = view.url()
            internal_address = self._internal_host(current_url)
            new_page = BrowserPage(self, self.profile, view)
            view.setPage(new_page)
            self._connect_page(view, new_page)
            if old_page is not None:
                try:
                    old_page.deleteLater()
                except RuntimeError:
                    logger.debug("Old profile page was already destroyed", exc_info=True)
            if internal_address is not None:
                self._load_internal_page(view, current_url)
            else:
                view.setUrl(current_url if current_url.isValid() else QUrl("about:blank"))
            self._recorded_history_urls.pop(view, None)

        self.navbar.history = self.history.history if self.history else {}
        self.navbar.change_profile_orders(self.selected_profile)
        self.navbar.clear_url_bar()
        if self.current_view() is not None:
            self.navbar.url_bar.setText(self.current_view().url().toString())
            self._update_navigation_actions(self.current_view())

    def on_profile_selected(self, profile_name: str):
        try:
            self.settings.save(self.selected_profile)
        except (OSError, ValueError):
            logger.exception("Could not save settings for profile %s", self.selected_profile)
        self.selected_profile = profile_name
        new_settings = Settings(file_path=self.settings.file_path, profiles_list=self.settings.profiles_list)
        new_settings.load(profile_name)
        self.settings = new_settings
        self.navbar.settings = new_settings
        self.change_profile(profile_name)
        self.dock.setVisible(bool(self.settings.proxy_panel_visible))
        self.apply_theme()
        self.new_tab()


    def _show_status_overlay(self, message: str, timeout: int = 0) -> None:
        view = self.current_view()
        parent = view if view is not None else getattr(self, "view_container", None)
        if parent is None:
            return
        overlays = getattr(self, "_status_overlays", None)
        if overlays is None:
            overlays = {}
            self._status_overlays = overlays
        overlay = overlays.get(parent)
        if overlay is None:
            overlay = _StatusMessageOverlay(
                parent, dark=bool(getattr(getattr(self, "settings", None), "dark_mode", False))
            )
            overlays[parent] = overlay
        overlay.set_theme(bool(getattr(getattr(self, "settings", None), "dark_mode", False)))
        overlay.showMessage(message, timeout)

    def open_current_page_externally(self) -> None:
        """Open the current web address in the operating system's default browser."""
        view = self.current_view()
        if view is None:
            return
        url = view.url()
        if not url.isValid() or url.scheme().lower() not in {"http", "https"}:
            _show_status_message(self, "Only web pages can be opened externally.", 3000)
            return
        if QDesktopServices.openUrl(url):
            _show_status_message(self, "Opened in the default browser.", 2500)
        else:
            _show_status_message(self, "Could not open the default browser.", 4000)

    def reload_current_page_bypassing_cache(self) -> None:
        """Retry the active page without reusing resources from the HTTP cache."""
        view = self.current_view()
        if view is None:
            return
        url = view.url()
        if not url.isValid() or url.scheme().lower() not in {"http", "https"}:
            _show_status_message(self, 
                "Only web pages can be reloaded without cache.", 3000
            )
            return
        view.page().triggerAction(QWebEnginePage.WebAction.ReloadAndBypassCache)
        _show_status_message(self, "Reloading without the local cache…", 2500)

    def navigate(self, url: str):
        if isinstance(url, QUrl):
            url = url.toString()
        if not isinstance(url, str):
            _show_status_message(self, "The selected address is invalid.", 5000)
            return
        internal_host = BrowserWindow._internal_host(url)
        if internal_host is not None:
            view = self.current_view()
            if view is not None:
                self._load_internal_page(view, f"arma://{internal_host}/")
                self.navbar.url_bar.setText(f"arma://{internal_host}/")
            return
        try:
            resolved_url = resolve_address_input(url, self.settings.default_search_engine)
        except URLInputError as exc:
            _show_status_message(self, str(exc), 5000)
            logger.info("Rejected address bar input %r: %s", url, exc)
            return
        view = self.current_view()
        if view:
            view.setUrl(QUrl(resolved_url))
            self.navbar.url_bar.setText(resolved_url)

    def update_url_bar(self, qurl: QUrl):
        self.navbar.url_bar.setText(qurl.toString())

    def open_settings(self):
        self.navigate("arma://settings/")

    def apply_theme(self):
        try:
            theme = dark_theme if getattr(self.settings, "dark_mode", False) else light_theme
            self.setStyleSheet(theme)
            if hasattr(self.navbar, "apply_theme"):
                self.navbar.apply_theme()
            dark = bool(getattr(self.settings, "dark_mode", False))
            corner_color = "#22272e" if dark else "#e9edf3"
            for view in tuple(getattr(self, "views", ())):
                if isinstance(view, _RoundedWebView):
                    view.set_corner_color(corner_color)
            if hasattr(self, "tabbar"):
                self.tabbar.apply_icon_theme(dark)
            if hasattr(self, "title_bar"):
                self.title_bar.apply_icon_theme(dark)
            if getattr(self, "bookmarks_bar", None) is not None:
                self.bookmarks_bar.apply_icon_theme(dark)
            if getattr(self, "proxy_panel", None) is not None:
                self.proxy_panel.apply_theme("dark" if dark else "light")
            self._sync_dashboard_tabs()
            theme_name = "dark" if dark else "light"
            theme_script = (
                "window.armaSetTheme && window.armaSetTheme("
                + json.dumps(theme_name) + ");"
            )
            for internal_view in tuple(getattr(self, "views", ())):
                if self._internal_host(internal_view.url()) in {"settings", "history", "downloads"}:
                    internal_view.page().runJavaScript(theme_script)
        except RuntimeError:
            logger.exception("Could not apply the current browser theme")
    
    def _apply_native_window_corner_preference(self, edge_to_edge: bool) -> None:
        """Ask DWM for genuinely rounded outer corners in windowed mode."""
        if sys.platform != "win32":
            return
        try:
            hwnd = int(self.winId())
            if not hwnd:
                return
            dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)
            set_attribute = dwmapi.DwmSetWindowAttribute
            set_attribute.argtypes = (
                wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD
            )
            set_attribute.restype = ctypes.c_long
            preference = ctypes.c_int(
                _WIN_DWMWCP_DONOTROUND if edge_to_edge else _WIN_DWMWCP_ROUND
            )
            result = int(set_attribute(
                wintypes.HWND(hwnd),
                _WIN_DWMWA_WINDOW_CORNER_PREFERENCE,
                ctypes.byref(preference),
                ctypes.sizeof(preference),
            ))
            if result < 0:
                logger.debug("DWM did not accept the requested corner preference (HRESULT 0x%08X).", result & 0xFFFFFFFF)
        except (AttributeError, OSError, TypeError, ValueError):
            logger.debug("Could not request native rounded window corners.", exc_info=True)

    def _apply_native_window_styles(self) -> None:
        """Restore Windows resize/maximize styles without adding a visible title bar."""
        # Do not add a resize frame while genuinely fullscreen. The state-change
        # refresh reapplies resize styles after returning to a windowed state.
        if sys.platform != "win32" or self.isFullScreen():
            return
        try:
            hwnd = int(self.winId())
            if not hwnd:
                return
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            get_style = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
            set_style = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
            get_style.argtypes = (wintypes.HWND, ctypes.c_int)
            get_style.restype = ctypes.c_ssize_t
            set_style.argtypes = (wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t)
            set_style.restype = ctypes.c_ssize_t
            current = int(get_style(wintypes.HWND(hwnd), _WIN_GWL_STYLE))
            desired = _with_resizable_frameless_windows_style(current)
            if current != desired:
                set_style(wintypes.HWND(hwnd), _WIN_GWL_STYLE, desired)
                set_window_pos = user32.SetWindowPos
                set_window_pos.argtypes = (
                    wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                    ctypes.c_int, ctypes.c_int, wintypes.UINT,
                )
                set_window_pos.restype = wintypes.BOOL
                flags = (
                    _WIN_SWP_NOMOVE | _WIN_SWP_NOSIZE | _WIN_SWP_NOZORDER
                    | _WIN_SWP_NOACTIVATE | _WIN_SWP_FRAMECHANGED
                )
                if not set_window_pos(wintypes.HWND(hwnd), wintypes.HWND(0), 0, 0, 0, 0, flags):
                    raise ctypes.WinError(ctypes.get_last_error())
            self._native_style_hwnd = hwnd
            self._apply_native_window_corner_preference(self._is_edge_to_edge_geometry())
        except (AttributeError, OSError, TypeError, ValueError):
            logger.debug("Could not restore native frameless-window styles.", exc_info=True)

    def _connect_window_handle_signals(self) -> None:
        handle = self.windowHandle()
        if handle is None or handle is self._window_handle_connected:
            return
        self._window_handle_connected = handle
        try:
            handle.screenChanged.connect(self._on_window_screen_changed)
        except (AttributeError, RuntimeError):
            logger.debug("Could not connect the active-screen signal.", exc_info=True)

    def _queue_window_frame_refresh(self) -> None:
        if getattr(self, "_native_refresh_pending", False):
            return
        self._native_refresh_pending = True
        QTimer.singleShot(0, self._refresh_window_platform_state)

    def _refresh_window_platform_state(self) -> None:
        self._native_refresh_pending = False
        if getattr(self, "_closing", False):
            return
        self._connect_window_handle_signals()
        self._apply_native_window_styles()
        self._sync_window_frame()
        self._update_resize_handles()
        if hasattr(self, "title_bar"):
            self.title_bar.sync_maximize_button()

    def _on_window_screen_changed(self, screen) -> None:
        """Recalculate custom frame geometry when the window moves across monitors."""
        self._sync_window_frame()
        self._update_resize_handles()
        self._queue_window_frame_refresh()
        QTimer.singleShot(0, lambda target=screen: self._recover_offscreen_geometry(target))

    def _recover_offscreen_geometry(self, screen=None) -> None:
        """Recover a normal window when its last monitor is disconnected."""
        if self.isMaximized() or self.isFullScreen() or getattr(self, "_closing", False):
            return
        app = QApplication.instance()
        screens = app.screens() if app is not None else []
        current = self.frameGeometry()
        if any(current.intersects(candidate.availableGeometry()) for candidate in screens):
            return
        target = screen or (self.windowHandle().screen() if self.windowHandle() else None)
        target = target or (app.primaryScreen() if app is not None else None)
        if target is None:
            return
        available = target.availableGeometry()
        width = min(max(self.minimumWidth(), self.width()), available.width())
        height = min(max(self.minimumHeight(), self.height()), available.height())
        x = available.x() + max(0, (available.width() - width) // 2)
        y = available.y() + max(0, (available.height() - height) // 2)
        self.setGeometry(x, y, width, height)
        self._sync_window_frame()
        self._update_resize_handles()

    def event(self, event):
        result = super().event(event)
        refresh_types = {QEvent.Type.WinIdChange}
        for name in ("ScreenChangeInternal", "DevicePixelRatioChange"):
            value = getattr(QEvent.Type, name, None)
            if value is not None:
                refresh_types.add(value)
        if event.type() in refresh_types:
            self._queue_window_frame_refresh()
        return result

    def showEvent(self, event):
        super().showEvent(event)
        self._queue_window_frame_refresh()

    def nativeEvent(self, eventType, message):
        """Hit-test native resize edges while keeping custom buttons as Qt client controls."""
        if sys.platform == "win32":
            try:
                native = ctypes.cast(int(message), ctypes.POINTER(wintypes.MSG)).contents
                if native.message == _WIN_WM_NCHITTEST:
                    packed = int(native.lParam)
                    screen_point = wintypes.POINT(
                        ctypes.c_short(packed & 0xFFFF).value,
                        ctypes.c_short((packed >> 16) & 0xFFFF).value,
                    )
                    hwnd = wintypes.HWND(int(self.winId()))
                    user32 = ctypes.WinDLL("user32", use_last_error=True)
                    client_point = wintypes.POINT(screen_point.x, screen_point.y)
                    user32.ScreenToClient.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.POINT))
                    user32.ScreenToClient.restype = wintypes.BOOL
                    user32.ScreenToClient(hwnd, ctypes.byref(client_point))
                    ratio = max(1.0, float(self.devicePixelRatioF()))
                    local_point = QPoint(
                        int(round(client_point.x / ratio)),
                        int(round(client_point.y / ratio)),
                    )

                    title_bar = getattr(self, "title_bar", None)
                    if title_bar is not None:
                        maximize = getattr(title_bar, "maximize_button", None)
                        if maximize is not None:
                            rect = QRect(maximize.mapTo(self, QPoint(0, 0)), maximize.size())
                            if rect.contains(local_point):
                                # HTMAXBUTTON hands the click to Windows' native non-client
                                # button handling, bypassing the QToolButton signal. Keep this
                                # rectangle in the client area so Qt can maximize/restore it.
                                return True, _WIN_HTCLIENT
                        buttons = tuple(
                            getattr(title_bar, name, None)
                            for name in ("minimize_button", "maximize_button", "close_button")
                        )
                        if any(
                            button is not None and QRect(
                                button.mapTo(self, QPoint(0, 0)), button.size()
                            ).contains(local_point)
                            for button in buttons
                        ):
                            return False, 0

                    rect = wintypes.RECT()
                    user32.GetWindowRect.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.RECT))
                    user32.GetWindowRect.restype = wintypes.BOOL
                    if (
                        not self.isMaximized()
                        and not self.isFullScreen()
                        and user32.GetWindowRect(hwnd, ctypes.byref(rect))
                    ):
                        dpi = 96
                        get_dpi = getattr(user32, "GetDpiForWindow", None)
                        if get_dpi is not None:
                            get_dpi.argtypes = (wintypes.HWND,)
                            get_dpi.restype = wintypes.UINT
                            dpi = max(96, int(get_dpi(hwnd)))
                        metrics = getattr(user32, "GetSystemMetricsForDpi", None)
                        if metrics is not None:
                            metrics.argtypes = (ctypes.c_int, wintypes.UINT)
                            metrics.restype = ctypes.c_int
                            edge = max(6, min(16, metrics(32, dpi) + metrics(92, dpi)))
                        else:
                            get_metric = user32.GetSystemMetrics
                            get_metric.argtypes = (ctypes.c_int,)
                            get_metric.restype = ctypes.c_int
                            edge = max(6, min(16, get_metric(32) + get_metric(92)))
                        left = screen_point.x - rect.left < edge
                        right = rect.right - screen_point.x <= edge
                        top = screen_point.y - rect.top < edge
                        bottom = rect.bottom - screen_point.y <= edge
                        if top and left:
                            return True, _WIN_HTTOPLEFT
                        if top and right:
                            return True, _WIN_HTTOPRIGHT
                        if bottom and left:
                            return True, _WIN_HTBOTTOMLEFT
                        if bottom and right:
                            return True, _WIN_HTBOTTOMRIGHT
                        if left:
                            return True, _WIN_HTLEFT
                        if right:
                            return True, _WIN_HTRIGHT
                        if top:
                            return True, _WIN_HTTOP
                        if bottom:
                            return True, _WIN_HTBOTTOM

                    if title_bar is not None:
                        title_rect = QRect(title_bar.mapTo(self, QPoint(0, 0)), title_bar.size())
                        if title_rect.contains(local_point):
                            return True, _WIN_HTCAPTION
            except (AttributeError, TypeError, ValueError, OSError):
                logger.debug("Native hit testing failed; using Qt fallback.", exc_info=True)
        return super().nativeEvent(eventType, message)

    def prepare_shutdown(self):
        """Idempotently stop browser pages, downloads and embedded Tor resources."""
        if getattr(self, "_shutdown_resources_prepared", False):
            return
        self._shutdown_resources_prepared = True
        self._closing = True
        for download_manager in self._download_managers.values():
            try:
                download_manager.shutdown()
            except Exception:
                logger.exception("Could not stop a browser download manager")
        views = list(self.views)
        self.views.clear()
        self._page_load_overlays.clear()
        self._placeholders.clear()
        for view in views:
            try:
                view.stop()
                self.view_layout.removeWidget(view)
                view.deleteLater()
            except (RuntimeError, AttributeError):
                logger.debug("A browser page was already destroyed during shutdown.", exc_info=True)
        try:
            if self.proxy_panel is not None:
                self.proxy_panel.prepare_shutdown()
        except (AttributeError, OSError, RuntimeError):
            logger.exception("Error while shutting down embedded Tor/Proxy services")
        try:
            for tab in self.tabbar.tabs:
                tab._hover_timer.stop()
        except (AttributeError, RuntimeError):
            logger.debug("Tab hover timer cleanup was skipped.", exc_info=True)

    def closeEvent(self, event):
        active_downloads = []
        for manager in self._download_managers.values():
            try:
                active_downloads.extend(
                    item for item in manager.get_downloads()
                    if item.get("state") in {"requested", "downloading"}
                )
            except (AttributeError, RuntimeError):
                logger.exception("Could not inspect active downloads before closing")
        if active_downloads:
            prompt = QMessageBox(self)
            prompt.setIcon(QMessageBox.Warning)
            prompt.setWindowTitle("Downloads in progress")
            prompt.setText(
                f"{len(active_downloads)} download(s) are still in progress."
            )
            prompt.setInformativeText(
                "Closing ARMA Browser will cancel them. Do you want to close the browser?"
            )
            prompt.setStandardButtons(QMessageBox.Close | QMessageBox.Cancel)
            prompt.setDefaultButton(QMessageBox.Cancel)
            if prompt.exec() != QMessageBox.Close:
                self._pending_network_restart = None
                event.ignore()
                return
        restart = self._pending_network_restart
        if restart and not self._spawn_network_mode_restart(restart):
            self._pending_network_restart = None
            QMessageBox.warning(
                self,
                "Network mode not changed",
                "ARMA Browser could not restart safely. The current session is still open.",
            )
            event.ignore()
            return
        self._pending_network_restart = None
        self.prepare_shutdown()
        event.accept()

    def reload_engine(self):
        for view in tuple(self.views):
            view.reload()
    

    def handle_fullscreen(self, request: QWebEngineFullScreenRequest):
        if request.toggleOn():
            self._enter_fullscreen()
        else:
            self._leave_fullscreen()
        request.accept()

    def toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self._leave_fullscreen()
        else:
            self._enter_fullscreen()

    def _enter_fullscreen(self) -> None:
        if self.isFullScreen():
            return
        self._fullscreen_return_maximized = self.isMaximized()
        self._fullscreen_chrome_visibility = {
            widget: widget.isVisible()
            for widget in (
                self.title_bar, self.navbar, self.bookmarks_bar, self.tabbar,
                self.dock,
            )
            if widget is not None
        }
        for widget in self._fullscreen_chrome_visibility:
            widget.hide()
        self.showFullScreen()
        self._sync_window_frame()

    def _leave_fullscreen(self) -> None:
        if not self.isFullScreen():
            return
        if getattr(self, "_fullscreen_return_maximized", False):
            self.showMaximized()
        else:
            self.showNormal()
        for widget, was_visible in getattr(self, "_fullscreen_chrome_visibility", {}).items():
            widget.setVisible(was_visible)
        self._fullscreen_chrome_visibility = None
        self._sync_window_frame()
