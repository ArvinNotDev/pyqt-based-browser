"""Organized browser preferences with animated section navigation."""

from __future__ import annotations

import copy
import os
import sys

from PySide6.QtCore import QEvent, QEasingCurve, Qt, QPropertyAnimation, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
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
    QVBoxLayout,
    QWidget,
    QGraphicsOpacityEffect,
    QSizePolicy,
)

from managers.history_manager import History
from .history_window import HistoryWindow
from .settings import Settings


class SettingsWindow(QDialog):
    def __init__(self, settings: Settings, selected_profile: str, history: History | None, parent=None):
        super().__init__(parent)
        self.setObjectName("settingsDialog")
        self.setWindowTitle("Settings")
        self.resize(820, 590)
        self.setMinimumSize(720, 520)

        self.settings = settings
        self.selected_profile = selected_profile
        self.history = history
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
        self.section_list.setFixedWidth(172)
        self.section_list.setSpacing(3)
        self.section_list.setAccessibleName("Settings sections")
        content.addWidget(self.section_list)

        self.pages = QStackedWidget()
        self.pages.setObjectName("settingsPages")
        self.pages.setMinimumSize(0, 0)
        self.pages.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.pages_scroll = QScrollArea()
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
        self.download_folder_input.setPlaceholderText("./downloads")
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
        self.dark_mode_checkbox = QCheckBox("Use the dark theme")
        self.dark_mode_checkbox.setChecked(self.settings.dark_mode)
        card_layout.setContentsMargins(18, 18, 18, 18)
        card_layout.addWidget(self.dark_mode_checkbox)
        card_layout.addWidget(self._note("The theme applies to the browser controls and its built-in dialogs."))
        card_layout.addStretch(1)

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
        card_layout.addWidget(
            self._note("This setting takes effect after the browser restarts. Gaming mode temporarily pauses browser keyboard shortcuts.")
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
        for shortcut, description in rows:
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
        current = self.download_folder_input.text().strip() or os.getcwd()
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
        candidate = copy.copy(self.settings)
        candidate.homepage = homepage
        candidate.default_search_engine = search_engine
        candidate.download_folder = self.download_folder_input.text().strip() or "./downloads"
        candidate.site_compatibility_mode = self.site_compatibility_checkbox.isChecked()
        candidate.proxy_panel_visible = self.proxy_panel_checkbox.isChecked()
        candidate.dark_mode = self.dark_mode_checkbox.isChecked()
        candidate.save_history = self.save_history_checkbox.isChecked()
        candidate.save_cookies = self.save_cookies_checkbox.isChecked()
        candidate.private_mode = self.private_mode_checkbox.isChecked()
        candidate.hardware_acceleration = self.hw_accel_checkbox.isChecked()

        try:
            candidate.save(self.selected_profile)
        except (OSError, ValueError, TypeError) as exc:
            QMessageBox.critical(self, "Could not save settings", str(exc))
            return

        for name in (
            "homepage", "default_search_engine", "download_folder", "site_compatibility_mode",
            "proxy_panel_visible", "dark_mode",
            "save_history", "save_cookies", "private_mode", "hardware_acceleration",
        ):
            setattr(self.settings, name, getattr(candidate, name))

        if old_hardware_acceleration != candidate.hardware_acceleration:
            Settings.configure_hardware_acceleration(candidate.hardware_acceleration)
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
