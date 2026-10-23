"""Organized browser preferences with animated section navigation."""

from __future__ import annotations

import copy
import os
import re
import sys

from PySide6.QtCore import QEvent, QEasingCurve, Qt, QPropertyAnimation, QVariantAnimation, QTimer, QRectF
from PySide6.QtGui import QColor, QPainter, QLinearGradient
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
    QGraphicsOpacityEffect,
    QSizePolicy,
)

import qtawesome as qta

from managers.history_manager import History
from .history_window import HistoryWindow
from .settings import Settings, default_download_directory
from managers.dashboard_manager import PRESETS, DashboardManager




class ThemeSwitch(QCheckBox):
    """Compact, keyboard-accessible sun/moon switch with pointer dragging."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("themeSwitch")
        self.setText("Dark theme")
        self.setAccessibleName("Dark theme")
        self.setAccessibleDescription("Drag to switch between light and dark appearance.")
        self.setToolTip("Drag or click to change the browser theme")
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setFixedSize(68, 36)

        self._position = 1.0 if self.isChecked() else 0.0
        self._press_x = 0.0
        self._dragging = False
        self._animation = QVariantAnimation(self)
        self._animation.setDuration(170)
        self._animation.setEasingCurve(QEasingCurve.OutCubic)
        self._animation.valueChanged.connect(self._set_position)
        self.toggled.connect(self._animate_to_state)

    def _set_position(self, value) -> None:
        self._position = max(0.0, min(1.0, float(value)))
        self.update()

    def _animate_to_state(self, checked: bool) -> None:
        self._animation.stop()
        self._animation.setStartValue(self._position)
        self._animation.setEndValue(1.0 if checked else 0.0)
        self._animation.start()

    def paintEvent(self, event) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        dark = self.isChecked()
        track = QRectF(1.0, 1.0, self.width() - 2.0, self.height() - 2.0)
        gradient = QLinearGradient(track.topLeft(), track.bottomRight())
        if dark:
            gradient.setColorAt(0.0, QColor("#344b68"))
            gradient.setColorAt(1.0, QColor("#202d40"))
            border = QColor("#536b8a")
        else:
            gradient.setColorAt(0.0, QColor("#e9f0fa"))
            gradient.setColorAt(1.0, QColor("#d6e2f2"))
            border = QColor("#c7d5e8")

        painter.setPen(border)
        painter.setBrush(gradient)
        painter.drawRoundedRect(track, track.height() / 2.0, track.height() / 2.0)

        diameter = 28.0
        travel = self.width() - diameter - 8.0
        thumb_x = 4.0 + self._position * travel
        thumb = QRectF(thumb_x, 4.0, diameter, diameter)

        shadow = QRectF(thumb)
        shadow.translate(0.0, 1.0)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(15, 26, 42, 30))
        painter.drawEllipse(shadow)

        painter.setPen(QColor("#ffffff") if not dark else QColor("#9ec6ff"))
        painter.setBrush(QColor("#ffffff") if not dark else QColor("#79a9eb"))
        painter.drawEllipse(thumb)

        icon_name = "fa5s.moon" if dark else "fa5s.sun"
        icon_color = "#ffffff" if dark else "#c58a16"
        icon_pixmap = qta.icon(icon_name, color=icon_color).pixmap(16, 16)
        painter.drawPixmap(
            int(thumb.center().x() - icon_pixmap.width() / 2),
            int(thumb.center().y() - icon_pixmap.height() / 2),
            icon_pixmap,
        )

        if self.hasFocus():
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QColor("#6195e2") if not dark else QColor("#8db8ff"))
            painter.drawRoundedRect(
                QRectF(0.5, 0.5, self.width() - 1.0, self.height() - 1.0),
                self.height() / 2.0,
                self.height() / 2.0,
            )
        painter.end()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._animation.stop()
            self._press_x = event.position().x()
            self._dragging = False
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() & Qt.LeftButton:
            current_x = event.position().x()
            if abs(current_x - self._press_x) > 3.0:
                self._dragging = True
            if self._dragging:
                diameter = 28.0
                travel = max(1.0, self.width() - diameter - 8.0)
                self._set_position((current_x - diameter / 2.0 - 4.0) / travel)
                event.accept()
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            if self._dragging:
                checked = self._position >= 0.5
            else:
                checked = not self.isChecked()
            self.setChecked(checked)
            self._dragging = False
            event.accept()
            return
        super().mouseReleaseEvent(event)


class SmoothScrollArea(QScrollArea):
    """Animate wheel scrolling while keeping the dialog footer stationary."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._wheel_animation = QVariantAnimation(self)
        self._wheel_animation.setDuration(150)
        self._wheel_animation.setEasingCurve(QEasingCurve.OutCubic)
        self._wheel_animation.valueChanged.connect(self._set_animated_scroll_value)

    def _set_animated_scroll_value(self, value) -> None:
        self.verticalScrollBar().setValue(round(value))

    def wheelEvent(self, event) -> None:
        delta = event.pixelDelta().y()
        if delta:
            scroll_delta = -delta
        else:
            angle = event.angleDelta().y()
            if not angle:
                super().wheelEvent(event)
                return
            scroll_delta = -(angle / 120) * self.verticalScrollBar().singleStep() * 3

        bar = self.verticalScrollBar()
        current_target = (
            self._wheel_animation.endValue()
            if self._wheel_animation.state() == QVariantAnimation.Running
            else bar.value()
        )
        target = max(bar.minimum(), min(bar.maximum(), round(current_target + scroll_delta)))
        self._wheel_animation.stop()
        self._wheel_animation.setStartValue(bar.value())
        self._wheel_animation.setEndValue(target)
        self._wheel_animation.start()
        event.accept()


class SettingsWindow(QDialog):
    def __init__(
        self,
        settings: Settings,
        selected_profile: str,
        history: History | None,
        parent=None,
        dashboard: DashboardManager | None = None,
    ):
        super().__init__(parent)
        self.setObjectName("settingsDialog")
        self.setWindowTitle("Settings")
        self.resize(820, 590)
        self.setMinimumSize(720, 520)

        self.settings = settings
        self.selected_profile = selected_profile
        self.history = history
        self.dashboard = dashboard
        self._wallpaper_source: str | None = None
        self.restart_required = False
        self._animating_effect: QGraphicsOpacityEffect | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 18)
        root.setSpacing(16)

        header = QVBoxLayout()
        header.setSpacing(3)
        title = QLabel("Browser settings")
        title.setObjectName("dialogTitle")
        subtitle = QLabel("Choose how this browser looks, behaves, and protects your data.")
        subtitle.setObjectName("settingsSubtitle")
        header.addWidget(title)
        header.addWidget(subtitle)
        root.addLayout(header)

        content = QHBoxLayout()
        content.setSpacing(18)

        self.section_list = QListWidget()
        self.section_list.setObjectName("settingsNav")
        self.section_list.setFixedWidth(190)
        self.section_list.setSpacing(4)
        self.section_list.setLayoutDirection(Qt.LeftToRight)
        self.section_list.setAccessibleName("Settings sections")
        content.setContentsMargins(0, 0, 0, 0)
        content.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        content.addWidget(self.section_list, 0, Qt.AlignLeft)

        self.pages = QStackedWidget()
        self.pages.setObjectName("settingsPages")
        self.pages.setMinimumSize(0, 0)
        self.pages.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.pages_scroll = SmoothScrollArea()
        self.pages_scroll.setObjectName("settingsScroll")
        self.pages_scroll.setWidgetResizable(False)
        self.pages_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.pages_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.pages_scroll.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.pages_scroll.setFrameShape(QFrame.NoFrame)
        self.pages_scroll.setWidget(self.pages)
        self.pages_scroll.viewport().installEventFilter(self)
        content.addWidget(self.pages_scroll, 1)
        root.addLayout(content, 1)

        self._add_general_page()
        self._add_appearance_page()
        self._add_dashboard_page()
        self._add_privacy_page()
        self._add_performance_page()
        self._add_shortcuts_page()

        footer = QHBoxLayout()
        self.history_btn = QPushButton("View history")
        self.history_btn.clicked.connect(self.open_history)
        footer.addWidget(self.history_btn)
        footer.addStretch()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        footer.addWidget(self.cancel_btn)

        self.save_btn = QPushButton("Save changes")
        self.save_btn.setObjectName("primaryButton")
        self.save_btn.setDefault(True)
        self.save_btn.clicked.connect(self.save_settings)
        footer.addWidget(self.save_btn)
        root.addLayout(footer)

        self._section_animation = QPropertyAnimation(self, b"windowOpacity", self)
        self._section_animation.setDuration(170)
        self._section_animation.setEasingCurve(QEasingCurve.OutCubic)
        self._page_animation = QPropertyAnimation(self, b"windowOpacity", self)
        self._page_animation.setDuration(160)
        self._page_animation.setEasingCurve(QEasingCurve.OutCubic)
        self._page_animation.finished.connect(self._restore_page_opacity)
        self.section_list.currentRowChanged.connect(self._show_section)
        self.section_list.setCurrentRow(0)
        QTimer.singleShot(0, self._update_pages_scroll_size)

    def _make_page(self, title: str, description: str) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        page.setMinimumSize(0, 0)
        page.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        heading = QLabel(title)
        heading.setObjectName("settingsSectionTitle")
        supporting_text = QLabel(description)
        supporting_text.setObjectName("settingsSectionDescription")
        supporting_text.setWordWrap(True)
        layout.addWidget(heading)
        layout.addWidget(supporting_text)

        card = QFrame()
        card.setObjectName("settingsCard")
        layout.addWidget(card)
        layout.addStretch(1)
        page.setGraphicsEffect(QGraphicsOpacityEffect(page))
        self.pages.addWidget(page)
        self.section_list.addItem(QListWidgetItem(title))
        return card, QVBoxLayout(card)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        QTimer.singleShot(0, self._update_pages_scroll_size)

    def eventFilter(self, watched, event) -> bool:
        if watched is self.pages_scroll.viewport() and event.type() == QEvent.Resize:
            QTimer.singleShot(0, self._update_pages_scroll_size)
        return super().eventFilter(watched, event)

    def _update_pages_scroll_size(self) -> None:
        if not hasattr(self, "pages_scroll") or self.pages.count() == 0:
            return
        viewport = self.pages_scroll.viewport().size()
        width = max(1, viewport.width())
        content_height = 0
        for index in range(self.pages.count()):
            page = self.pages.widget(index)
            layout = page.layout()
            if layout is not None:
                layout.activate()
                content_height = max(content_height, layout.minimumSize().height())
            if page.hasHeightForWidth():
                content_height = max(content_height, page.heightForWidth(width))
            else:
                content_height = max(content_height, page.sizeHint().height())
        height = max(viewport.height(), content_height)
        if self.pages.width() != width or self.pages.height() != height:
            self.pages.resize(width, height)

    def _add_general_page(self) -> None:
        _, card_layout = self._make_page(
            "General",
            "Set the pages that open when you browse and choose whether the proxy panel starts open.",
        )
        form = QFormLayout()
        form.setContentsMargins(18, 18, 18, 18)
        form.setHorizontalSpacing(20)
        form.setVerticalSpacing(16)

        self.homepage_input = QLineEdit(self.settings.homepage)
        self.homepage_input.setObjectName("settingsInput")
        self.homepage_input.setPlaceholderText("https://example.com")
        self.homepage_input.setClearButtonEnabled(True)
        form.addRow("Homepage", self.homepage_input)

        self.startup_combo = QComboBox()
        self.startup_combo.addItem("Dashboard", "dashboard")
        self.startup_combo.addItem("Homepage", "homepage")
        self.startup_combo.setCurrentIndex(max(0, self.startup_combo.findData(self.settings.startup_page)))
        form.addRow("When browser opens", self.startup_combo)

        self.new_tab_combo = QComboBox()
        self.new_tab_combo.addItem("Dashboard", "dashboard")
        self.new_tab_combo.addItem("Homepage", "homepage")
        self.new_tab_combo.setCurrentIndex(max(0, self.new_tab_combo.findData(self.settings.new_tab_page)))
        form.addRow("New tab page", self.new_tab_combo)

        self.search_input = QLineEdit(self.settings.default_search_engine)
        self.search_input.setObjectName("settingsInput")
        self.search_input.setPlaceholderText("https://search.example/?q=")
        self.search_input.setClearButtonEnabled(True)
        form.addRow("Search engine URL", self.search_input)

        download_widget = QWidget()
        download_row = QHBoxLayout(download_widget)
        download_row.setContentsMargins(0, 0, 0, 0)
        self.download_folder_input = QLineEdit(self.settings.download_folder)
        self.download_folder_input.setObjectName("settingsInput")
        self.download_folder_input.setClearButtonEnabled(True)
        self.download_folder_input.setPlaceholderText(default_download_directory())
        browse_button = QPushButton("Browse…")
        browse_button.clicked.connect(self._browse_download_folder)
        download_row.addWidget(self.download_folder_input, 1)
        download_row.addWidget(browse_button)
        form.addRow("Download location", download_widget)

        self.site_compatibility_checkbox = QCheckBox(
            "Use a standard Chromium identity for websites"
        )
        self.site_compatibility_checkbox.setChecked(bool(self.settings.site_compatibility_mode))
        self.site_compatibility_checkbox.setToolTip(
            "Hides the QtWebEngine product marker from the browser user agent."
        )
        form.addRow("Website compatibility", self.site_compatibility_checkbox)

        self.proxy_panel_checkbox = QCheckBox("Show proxy panel when the browser opens")
        self.proxy_panel_checkbox.setChecked(bool(self.settings.proxy_panel_visible))
        form.addRow("Proxy panel", self.proxy_panel_checkbox)
        card_layout.addLayout(form)
        card_layout.addWidget(
            self._note(
                "The compatibility option only changes the browser's user-agent label. "
                "It does not add or disable ad-blocking extensions."
            )
        )

    def _add_appearance_page(self) -> None:
        _, card_layout = self._make_page(
            "Appearance",
            "Choose the browser theme. The change is applied as soon as you save.",
        )
        card_layout.setContentsMargins(18, 18, 18, 18)

        theme_row = QHBoxLayout()
        theme_row.setSpacing(16)
        theme_copy = QVBoxLayout()
        theme_copy.setSpacing(4)
        theme_title = QLabel("Appearance mode")
        theme_title.setObjectName("settingsSectionTitle")
        theme_description = QLabel("Light by day, dark when you need less glare.")
        theme_description.setObjectName("settingsSectionDescription")
        theme_description.setWordWrap(True)
        theme_copy.addWidget(theme_title)
        theme_copy.addWidget(theme_description)
        theme_row.addLayout(theme_copy, 1)

        self.dark_mode_checkbox = ThemeSwitch()
        self.dark_mode_checkbox.setChecked(self.settings.dark_mode)
        theme_row.addWidget(self.dark_mode_checkbox, 0, Qt.AlignVCenter)
        card_layout.addLayout(theme_row)
        card_layout.addWidget(
            self._note("The theme applies to browser controls and built-in dialogs.")
        )
        card_layout.addStretch(1)

    def _add_dashboard_page(self) -> None:
        _, card_layout = self._make_page(
            "Dashboard",
            "Personalize the start page for this profile. Shortcut management is available directly on the dashboard.",
        )
        card_layout.setContentsMargins(18, 18, 18, 18)
        data = self.dashboard.data if self.dashboard is not None else {}
        self.dashboard_clock_combo = QComboBox()
        self.dashboard_clock_combo.addItem("24-hour", True)
        self.dashboard_clock_combo.addItem("12-hour", False)
        self.dashboard_clock_combo.setCurrentIndex(
            max(0, self.dashboard_clock_combo.findData(data.get("clock_24h", True)))
        )
        self.dashboard_seconds_checkbox = QCheckBox("Show seconds in the clock")
        self.dashboard_seconds_checkbox.setChecked(bool(data.get("show_seconds", False)))
        self.dashboard_animations_checkbox = QCheckBox("Use subtle dashboard motion")
        self.dashboard_animations_checkbox.setChecked(bool(data.get("animations", True)))
        card_layout.addWidget(QLabel("Clock format"))
        card_layout.addWidget(self.dashboard_clock_combo)
        card_layout.addWidget(self.dashboard_seconds_checkbox)
        card_layout.addWidget(self.dashboard_animations_checkbox)

        self.dashboard_overlay_slider = QSlider(Qt.Horizontal)
        self.dashboard_overlay_slider.setRange(0, 70)
        self.dashboard_overlay_slider.setValue(int(data.get("overlay", 20)))
        self.dashboard_overlay_label = QLabel(f"Wallpaper dimming: {self.dashboard_overlay_slider.value()}%")
        self.dashboard_overlay_slider.valueChanged.connect(
            lambda value: self.dashboard_overlay_label.setText(f"Wallpaper dimming: {value}%")
        )
        card_layout.addWidget(self.dashboard_overlay_label)
        card_layout.addWidget(self.dashboard_overlay_slider)

        self.dashboard_glass_slider = QSlider(Qt.Horizontal)
        self.dashboard_glass_slider.setRange(20, 90)
        self.dashboard_glass_slider.setValue(int(data.get("glass", 58)))
        self.dashboard_glass_label = QLabel(f"Glass intensity: {self.dashboard_glass_slider.value()}%")
        self.dashboard_glass_slider.valueChanged.connect(
            lambda value: self.dashboard_glass_label.setText(f"Glass intensity: {value}%")
        )
        card_layout.addWidget(self.dashboard_glass_label)
        card_layout.addWidget(self.dashboard_glass_slider)

        self.dashboard_blur_slider = QSlider(Qt.Horizontal)
        self.dashboard_blur_slider.setRange(0, 12)
        self.dashboard_blur_slider.setValue(int(data.get("blur", 0)))
        self.dashboard_blur_label = QLabel(f"Wallpaper soft focus: {self.dashboard_blur_slider.value()} px")
        self.dashboard_blur_slider.valueChanged.connect(
            lambda value: self.dashboard_blur_label.setText(f"Wallpaper soft focus: {value} px")
        )
        card_layout.addWidget(self.dashboard_blur_label)
        card_layout.addWidget(self.dashboard_blur_slider)

        self.dashboard_accent_input = QLineEdit(str(data.get("accent", "#8db8ff")))
        self.dashboard_accent_input.setObjectName("settingsInput")
        self.dashboard_accent_input.setMaxLength(7)
        card_layout.addWidget(QLabel("Accent color (hex)"))
        card_layout.addWidget(self.dashboard_accent_input)

        widgets = data.get("widgets", {})
        widget_sizes = data.get("widget_sizes", {})
        self.dashboard_widget_checks = {}
        self.dashboard_widget_size_combos = {}
        card_layout.addWidget(QLabel("Widgets · visibility and size"))
        card_layout.addWidget(self._note(
            "Turn cards on or off here. On the start page, drag a card by its heading to change its position."
        ))
        for key, label in (
            ("bookmarks", "Bookmarks"),
            ("recent", "Recently visited"),
            ("closed", "Recently closed"),
            ("notes", "Quick notes"),
            ("focus", "Focus timer"),
        ):
            row = QWidget()
            row.setObjectName("dashboardWidgetOptionRow")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(12)
            checkbox = QCheckBox(label)
            checkbox.setChecked(bool(widgets.get(key, True)))
            checkbox.setAccessibleName(f"Show {label.lower()} widget")
            size_combo = QComboBox()
            size_combo.setObjectName("dashboardWidgetSize")
            size_combo.addItem("Compact", "compact")
            size_combo.addItem("Standard", "standard")
            size_combo.addItem("Wide", "wide")
            size_combo.setCurrentIndex(max(
                0, size_combo.findData(widget_sizes.get(key, "standard"))
            ))
            size_combo.setToolTip(f"Width of the {label.lower()} widget")
            size_combo.setAccessibleName(f"{label} widget size")
            row_layout.addWidget(checkbox, 1)
            row_layout.addWidget(size_combo, 0)
            self.dashboard_widget_checks[key] = checkbox
            self.dashboard_widget_size_combos[key] = size_combo
            card_layout.addWidget(row)

        wallpaper_row = QHBoxLayout()
        self.dashboard_wallpaper_label = QLabel(self._wallpaper_label(data.get("wallpaper", "aurora")))
        self.dashboard_wallpaper_label.setWordWrap(True)
        wallpaper_button = QPushButton("Choose image…")
        wallpaper_button.clicked.connect(self._browse_dashboard_wallpaper)
        wallpaper_row.addWidget(self.dashboard_wallpaper_label, 1)
        wallpaper_row.addWidget(wallpaper_button)
        card_layout.addLayout(wallpaper_row)
        card_layout.addWidget(self._note("Supported images are copied into this profile's dashboard storage. Add and reorder shortcuts on the start page; drag widget headings to reorder cards and choose each card's size above."))
        card_layout.addStretch(1)

    @staticmethod
    def _wallpaper_label(key: str) -> str:
        if key in PRESETS:
            return f"Current wallpaper: {PRESETS[key]['title']}"
        if isinstance(key, str) and key.startswith("file:"):
            return "Current wallpaper: Imported image"
        return "Current wallpaper: Aurora"

    def _browse_dashboard_wallpaper(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "Choose dashboard wallpaper",
            os.path.expanduser("~"),
            "Images (*.jpg *.jpeg *.png *.webp)",
        )
        if selected:
            self._wallpaper_source = selected
            self.dashboard_wallpaper_label.setText(f"Selected image: {os.path.basename(selected)}")

    def _add_privacy_page(self) -> None:
        _, card_layout = self._make_page(
            "Privacy",
            "Control which browsing data is kept between sessions.",
        )
        card_layout.setContentsMargins(18, 18, 18, 18)
        self.save_history_checkbox = QCheckBox("Save browsing history")
        self.save_history_checkbox.setChecked(self.settings.save_history)
        self.save_cookies_checkbox = QCheckBox("Keep cookies between sessions")
        self.save_cookies_checkbox.setChecked(self.settings.save_cookies)
        self.private_mode_checkbox = QCheckBox("Use private browsing")
        self.private_mode_checkbox.setChecked(self.settings.private_mode)
        card_layout.addWidget(self.save_history_checkbox)
        card_layout.addWidget(self.save_cookies_checkbox)
        card_layout.addWidget(self.private_mode_checkbox)
        card_layout.addWidget(
            self._note("Private browsing keeps site data in memory for this session. It does not restore tabs when the browser restarts.")
        )
        card_layout.addStretch(1)

    def _add_performance_page(self) -> None:
        _, card_layout = self._make_page(
            "Performance",
            "Choose whether Chromium uses hardware acceleration to render pages.",
        )
        card_layout.setContentsMargins(18, 18, 18, 18)
        self.hw_accel_checkbox = QCheckBox("Use hardware acceleration (restart required)")
        self.hw_accel_checkbox.setChecked(self.settings.hardware_acceleration)
        card_layout.addWidget(self.hw_accel_checkbox)
        self.webgpu_checkbox = QCheckBox("Enable WebGPU (restart required)")
        self.webgpu_checkbox.setChecked(self.settings.webgpu_enabled)
        self.webgpu_checkbox.setToolTip(
            "Enable Chromium WebGPU only if your graphics driver can create a WebGPU context."
        )
        card_layout.addWidget(self.webgpu_checkbox)
        card_layout.addWidget(
            self._note("Graphics startup settings take effect after restarting the browser. Disable WebGPU to avoid repeated context-provider errors.")
        )
        card_layout.addStretch(1)

    def _add_shortcuts_page(self) -> None:
        _, card_layout = self._make_page(
            "Keyboard shortcuts",
            "Use these shortcuts to move around quickly. Gaming mode pauses browser shortcuts until you turn it off from the menu.",
        )
        card_layout.setContentsMargins(18, 16, 18, 16)
        rows = (
            ("Ctrl + T", "New tab"),
            ("Ctrl + W", "Close current tab"),
            ("Ctrl + Shift + T", "Reopen last closed tab"),
            ("Ctrl + Tab", "Next tab"),
            ("Ctrl + Shift + Tab", "Previous tab"),
            ("Ctrl + 1 … 8", "Switch to a tab"),
            ("Ctrl + 9", "Switch to the last tab"),
            ("Ctrl + L", "Focus address bar"),
            ("Ctrl + R / F5", "Reload page"),
            ("Alt + ← / →", "Back / forward"),
            ("Alt + Home", "Open homepage"),
            ("Ctrl + D", "Bookmark page"),
            ("Ctrl + H", "Open history"),
            ("Ctrl + J", "Open downloads"),
            ("Ctrl + ,", "Open settings"),
        )
        for shortcut, description in rows + (("F11", "Toggle fullscreen"),):
            row = QHBoxLayout()
            key = QLabel(shortcut)
            key.setObjectName("shortcutKey")
            key.setMinimumWidth(142)
            label = QLabel(description)
            label.setObjectName("shortcutDescription")
            row.addWidget(key)
            row.addWidget(label, 1)
            card_layout.addLayout(row)
        card_layout.addStretch(1)

    @staticmethod
    def _note(text: str) -> QLabel:
        note = QLabel(text)
        note.setObjectName("settingsNote")
        note.setWordWrap(True)
        return note

    def _show_section(self, index: int) -> None:
        if index < 0 or index >= self.pages.count():
            return
        page = self.pages.widget(index)
        effect = page.graphicsEffect()
        self.pages.setCurrentIndex(index)
        QTimer.singleShot(0, self._update_pages_scroll_size)
        if not isinstance(effect, QGraphicsOpacityEffect):
            return
        self._page_animation.stop()
        self._animating_effect = effect
        effect.setOpacity(0.55)
        self._page_animation.setTargetObject(effect)
        self._page_animation.setPropertyName(b"opacity")
        self._page_animation.setStartValue(0.55)
        self._page_animation.setEndValue(1.0)
        self._page_animation.start()

    def _browse_download_folder(self) -> None:
        current = self.download_folder_input.text().strip() or default_download_directory()
        folder = QFileDialog.getExistingDirectory(self, "Choose download folder", current)
        if folder:
            self.download_folder_input.setText(folder)

    def _restore_page_opacity(self) -> None:
        if self._animating_effect is not None:
            self._animating_effect.setOpacity(1.0)
            self._animating_effect = None

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._section_animation.stop()
        self._section_animation.setStartValue(0.0)
        self._section_animation.setEndValue(1.0)
        self.setWindowOpacity(0.0)
        self._section_animation.start()

    def open_history(self) -> None:
        dialog = HistoryWindow(self.selected_profile, History(self.selected_profile), self)
        dialog.exec()

    def save_settings(self) -> None:
        homepage = self.homepage_input.text().strip()
        search_engine = self.search_input.text().strip()
        if not homepage or not search_engine:
            QMessageBox.warning(self, "Invalid settings", "Homepage and search engine cannot be empty.")
            self.section_list.setCurrentRow(0)
            return

        old_hardware_acceleration = self.settings.hardware_acceleration
        old_webgpu_enabled = self.settings.webgpu_enabled
        candidate = copy.copy(self.settings)
        candidate.homepage = homepage
        candidate.startup_page = str(self.startup_combo.currentData())
        candidate.new_tab_page = str(self.new_tab_combo.currentData())
        candidate.default_search_engine = search_engine
        candidate.download_folder = self.download_folder_input.text().strip() or default_download_directory()
        candidate.site_compatibility_mode = self.site_compatibility_checkbox.isChecked()
        candidate.proxy_panel_visible = self.proxy_panel_checkbox.isChecked()
        candidate.dark_mode = self.dark_mode_checkbox.isChecked()
        candidate.save_history = self.save_history_checkbox.isChecked()
        candidate.save_cookies = self.save_cookies_checkbox.isChecked()
        candidate.private_mode = self.private_mode_checkbox.isChecked()
        candidate.hardware_acceleration = self.hw_accel_checkbox.isChecked()
        candidate.webgpu_enabled = self.webgpu_checkbox.isChecked()

        dashboard_values = None
        if self.dashboard is not None:
            accent = self.dashboard_accent_input.text().strip()
            if not re.fullmatch(r"#[0-9a-fA-F]{6}", accent):
                QMessageBox.warning(self, "Invalid accent color", "Enter a hex color such as #8db8ff.")
                self.section_list.setCurrentRow(2)
                return
            dashboard_values = {
                "clock_24h": bool(self.dashboard_clock_combo.currentData()),
                "show_seconds": self.dashboard_seconds_checkbox.isChecked(),
                "animations": self.dashboard_animations_checkbox.isChecked(),
                "overlay": self.dashboard_overlay_slider.value(),
                "glass": self.dashboard_glass_slider.value(),
                "blur": self.dashboard_blur_slider.value(),
                "accent": accent,
                "widgets": {
                    key: checkbox.isChecked()
                    for key, checkbox in self.dashboard_widget_checks.items()
                },
                "widget_sizes": {
                    key: combo.currentData()
                    for key, combo in self.dashboard_widget_size_combos.items()
                },
            }
            if self._wallpaper_source:
                try:
                    dashboard_values["wallpaper"] = self.dashboard.import_wallpaper(
                        self._wallpaper_source, activate=False
                    )
                except (OSError, ValueError) as exc:
                    QMessageBox.warning(self, "Could not use wallpaper", str(exc))
                    self.section_list.setCurrentRow(2)
                    return

        try:
            candidate.save(self.selected_profile)
            if self.dashboard is not None and dashboard_values is not None:
                self.dashboard.update(dashboard_values)
        except (OSError, ValueError, TypeError) as exc:
            QMessageBox.critical(self, "Could not save settings", str(exc))
            return

        for name in (
            "homepage", "startup_page", "new_tab_page", "default_search_engine", "download_folder", "site_compatibility_mode",
            "proxy_panel_visible", "dark_mode",
            "save_history", "save_cookies", "private_mode", "hardware_acceleration", "webgpu_enabled",
        ):
            setattr(self.settings, name, getattr(candidate, name))

        if old_hardware_acceleration != candidate.hardware_acceleration:
            Settings.configure_hardware_acceleration(candidate.hardware_acceleration)
            self.restart_required = True
        if old_webgpu_enabled != candidate.webgpu_enabled:
            Settings.configure_webgpu(candidate.webgpu_enabled)
            self.restart_required = True

        self.accept()
        if self.parent() and hasattr(self.parent(), "apply_theme"):
            self.parent().apply_theme()

        if self.restart_required:
            result = QMessageBox.question(
                self,
                "Restart required",
                "The hardware acceleration preference requires restarting the browser. Restart now?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if result == QMessageBox.Yes:
                self.restart_browser()

    def restart_browser(self) -> None:
        """Restart the current Python application."""
        python = sys.executable
        os.execl(python, python, *sys.argv)
