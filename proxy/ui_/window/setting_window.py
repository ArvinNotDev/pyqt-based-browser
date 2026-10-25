from PySide6.QtWidgets import (
    QApplication, QFrame, QScrollArea, QSizePolicy, QLabel, QWidget,
    QButtonGroup, QRadioButton, QVBoxLayout, QHBoxLayout, QPushButton,
    QCheckBox, QTextEdit, QLineEdit, QStackedWidget, QListWidget, QMessageBox,
)
from PySide6.QtCore import Qt, QThreadPool, QSize
import qtawesome as qta

from pyzbar.pyzbar import decode
import re
import logging
from functools import partial

logger = logging.getLogger(__name__)

from proxy.config import CONFIG
from proxy.ui_.worker.worker import Worker
from proxy.ui_.window.qrcode_widget import QrCodeFloatingWindow
from proxy.config import IS_WINDOWS
from proxy.ui_.emojis import WRONG, CORRECT, LIGHT, DARK

class SettingWindow(QWidget):
    """Tor settings with searchable categories and persistent routing-rule navigation."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._parent = parent
        self._dark_mode = getattr(parent, "_display_mode", "dark")
        self._active_category = "bridges"
        self._category_pages = {}
        self._category_buttons = {}
        self._category_search_terms = {
            "bridges": "bridge bridges obfs4 snowflake meek webtunnel transport qr code import sni imitation",
            "ports": "port ports socks socksport proxy dns control listener tcp",
            "blocked hosts": "blocked block host deny blacklist site website domain",
            "excluded hosts": "excluded exclude host bypass direct allow whitelist domain",
            "advanced": "advanced maxcircuitdirtiness newnym new identity circuit period timeout",
        }
        self._category_group_labels = {}

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 9, 10, 10)
        main_layout.setSpacing(9)

        self._category_menu_open = False
        search_row = QHBoxLayout()
        search_row.setContentsMargins(0, 0, 0, 0)
        search_row.setSpacing(6)
        self.menu_toggle = QPushButton(qta.icon("fa6s.bars"), "")
        self.menu_toggle.setObjectName("proxySettingsMenuToggle")
        self.menu_toggle.setFixedSize(36, 36)
        self.menu_toggle.setToolTip("Show setting categories")
        self.menu_toggle.setAccessibleName("Show setting categories")
        self.menu_toggle.setCheckable(True)
        self.menu_toggle.clicked.connect(self.toggle_category_menu)
        search_row.addWidget(self.menu_toggle)

        self.search_input = QLineEdit(self)
        self.search_input.setObjectName("proxySettingsSearch")
        self.search_input.setPlaceholderText("Search settings…  e.g. bridge, port, NEWNYM")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setMinimumHeight(36)
        self.search_input.setAccessibleName("Search Tor settings")
        self.search_input.textChanged.connect(self._filter_categories)
        search_row.addWidget(self.search_input, 1)
        main_layout.addLayout(search_row)

        content = QHBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(9)
        main_layout.addLayout(content, 1)

        self.sidebar = QFrame(self)
        self.sidebar.setObjectName("proxySettingsSidebar")
        self.sidebar.setFixedWidth(164)
        self.sidebar.hide()
        self.sidebar_layout = QVBoxLayout(self.sidebar)
        self.sidebar_layout.setContentsMargins(7, 9, 7, 9)
        self.sidebar_layout.setSpacing(4)
        self.settings_nav_group = QButtonGroup(self)
        self.settings_nav_group.setExclusive(True)
        self.settings_nav_buttons = []
        self._category_buttons = {}

        def add_group(title, categories):
            group_label = QLabel(title.upper(), self.sidebar)
            group_label.setObjectName("proxySettingsGroupTitle")
            self.sidebar_layout.addWidget(group_label)
            self._category_group_labels[title] = (group_label, tuple(entry[0] for entry in categories))
            for key, visible_label, icon_name in categories:
                button = QPushButton(visible_label, self.sidebar)
                button.setObjectName("proxySettingCategory")
                button.setIcon(qta.icon(icon_name))
                button.setIconSize(QSize(15, 15))
                button.setCheckable(True)
                button.setMinimumHeight(34)
                button.setToolTip(visible_label)
                button.setAccessibleName(visible_label)
                button.clicked.connect(lambda _checked=False, category=key: self.show_category(category))
                self.settings_nav_group.addButton(button)
                self.settings_nav_buttons.append(button)
                self._category_buttons[key] = button
                self.sidebar_layout.addWidget(button)

        add_group("Connection", (
            ("bridges", "Bridges", "fa6s.link"),
            ("ports", "Ports", "fa6s.network-wired"),
        ))
        add_group("Routing rules", (
            ("blocked hosts", "Blocked hosts", "fa6s.shield-halved"),
            ("excluded hosts", "Excluded hosts", "fa6s.route"),
        ))
        add_group("More", (
            ("advanced", "Advanced", "fa6s.sliders"),
        ))
        self.sidebar_layout.addStretch(1)
        self.no_results_label = QLabel("No matching category", self.sidebar)
        self.no_results_label.setWordWrap(True)
        self.no_results_label.setObjectName("proxySettingsNoResults")
        self.no_results_label.hide()
        self.sidebar_layout.addWidget(self.no_results_label)

        self.page_setting = QStackedWidget(self)
        self.page_setting.setObjectName("proxySettingsPages")
        content.addWidget(self.page_setting, 1)

        self.first_page = QWidget()
        self.first_page.setObjectName("proxySettingsContent")
        self.first_page_layout = QVBoxLayout(self.first_page)
        self.first_page_layout.setContentsMargins(12, 10, 12, 12)
        self.first_page_layout.setSpacing(10)
        self.first_page_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        bridges_scroll = QScrollArea(self.page_setting)
        bridges_scroll.setWidgetResizable(True)
        bridges_scroll.setFrameShape(QFrame.Shape.NoFrame)
        bridges_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        bridges_scroll.setWidget(self.first_page)
        self.page_setting.addWidget(bridges_scroll)
        self._category_pages["bridges"] = bridges_scroll

        self.initialize_first_page()
        self.initialize_second_page()
        self._blocked_placeholder = self._make_category_placeholder(
            "blocked hosts", "Blocked websites cannot be reached from this browser."
        )
        self._excluded_placeholder = self._make_category_placeholder(
            "excluded hosts", "Excluded websites bypass the Tor route."
        )
        self.initialize_advanced_page()
        self.show_category("bridges")
        self.apply_theme(self._dark_mode)

    def _make_category_placeholder(self, key, description):
        page = QFrame(self.page_setting)
        page.setObjectName("proxySettingsContent")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(14, 16, 14, 14)
        title = QLabel(key.title(), page)
        title.setObjectName("proxyRulesTitle")
        detail = QLabel(description, page)
        detail.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(detail)
        layout.addStretch(1)
        self.page_setting.addWidget(page)
        self._category_pages[key] = page
        return page

    def attach_host_pages(self, blocked_page, excluded_page):
        """Place host managers inside Settings so the category rail stays visible."""
        for key, widget in (("blocked hosts", blocked_page), ("excluded hosts", excluded_page)):
            old_page = self._category_pages.get(key)
            old_index = self.page_setting.indexOf(old_page) if old_page is not None else -1
            if old_page is not None and old_index >= 0:
                self.page_setting.removeWidget(old_page)
                old_page.deleteLater()
            widget.setObjectName("proxyHostRulesPage")
            if old_index < 0:
                old_index = self.page_setting.count()
            self.page_setting.insertWidget(old_index, widget)
            self._category_pages[key] = widget
        self.apply_theme(self._dark_mode)
        self.show_category(self._active_category)

    def _position_category_menu(self):
        row_bottom = self.search_input.geometry().bottom() + 7
        self.sidebar.setGeometry(
            10,
            max(45, row_bottom),
            min(190, max(140, self.width() - 20)),
            max(120, self.height() - row_bottom - 12),
        )

    def toggle_category_menu(self, opened=None):
        should_open = not self.sidebar.isVisible() if opened is None else bool(opened)
        self._category_menu_open = should_open
        if should_open:
            self._position_category_menu()
            self.sidebar.show()
            self.sidebar.raise_()
        else:
            self.sidebar.hide()
        self.menu_toggle.blockSignals(True)
        self.menu_toggle.setChecked(should_open)
        self.menu_toggle.setIcon(qta.icon(
            "fa6s.xmark" if should_open else "fa6s.bars",
            color="#ffffff" if should_open and self._dark_mode == "dark" else
                  ("#253041" if self._dark_mode == "light" else "#e8edf3"),
        ))
        self.menu_toggle.setToolTip("Hide setting categories" if should_open else "Show setting categories")
        self.menu_toggle.setAccessibleName(self.menu_toggle.toolTip())
        self.menu_toggle.blockSignals(False)

    def show_category(self, key, close_menu=True):
        if key not in self._category_pages:
            return
        self._active_category = key
        self.page_setting.setCurrentWidget(self._category_pages[key])
        for category, button in self._category_buttons.items():
            button.setChecked(category == key)
        self._update_category_icons()
        if close_menu:
            self.toggle_category_menu(False)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._category_menu_open:
            self._position_category_menu()
            self.sidebar.raise_()

    def _set_settings_page(self, index):
        if not 0 <= index < self.page_setting.count():
            return
        page = self.page_setting.widget(index)
        key = next((name for name, widget in self._category_pages.items() if widget is page), None)
        if key is not None:
            self.show_category(key)

    def _filter_categories(self, value):
        query = str(value or "").strip().casefold()
        matched = []
        for key, button in self._category_buttons.items():
            searchable = f"{key} {self._category_search_terms.get(key, '')}".casefold()
            visible = not query or query in searchable
            button.setVisible(visible)
            if visible:
                matched.append(key)
        for _title, (label, keys) in self._category_group_labels.items():
            label.setVisible(not query or any(key in matched for key in keys))
        self.no_results_label.setVisible(bool(query) and not matched)
        if query and matched and self._active_category not in matched:
            self.show_category(matched[0], close_menu=False)
        elif query and len(matched) == 1:
            self.show_category(matched[0], close_menu=False)
        if query:
            self.toggle_category_menu(True)

    def apply_theme(self, mode="dark"):
        dark = mode == "dark"
        self._dark_mode = mode
        border = "#3b4552" if dark else "#d7dee7"
        panel = "#202630" if dark else "#ffffff"
        surface = "#171c23" if dark else "#f8fafc"
        text = "#e8edf3" if dark else "#253041"
        muted = "#9aaabd" if dark else "#667386"
        accent = "#287db5"
        hover = "rgba(71,163,242,0.15)" if dark else "rgba(24,118,191,0.11)"
        self.setStyleSheet(f"""
            QWidget {{ color: {text}; }}
            QWidget#proxySettingsSidebar {{ background: {panel}; border: 1px solid {border}; border-radius: 10px; }}
            QPushButton#proxySettingsMenuToggle {{ min-height: 36px; min-width: 36px; padding: 0; border-radius: 9px; }}
            QPushButton#proxySettingsMenuToggle:checked {{ background: {accent}; color: #ffffff; border-color: {accent}; }}
            QWidget#proxySettingsContent {{ background: {panel}; border: 1px solid {border}; border-radius: 10px; }}
            QWidget#proxyHostRulesPage {{ background: {panel}; border: 1px solid {border}; border-radius: 10px; }}
            QLabel#proxySettingsGroupTitle {{ color: {muted}; background: transparent; font-size: 9px; font-weight: 800; padding: 7px 5px 3px; }}
            QLabel#proxySettingsNoResults {{ color: {muted}; font-size: 11px; padding: 5px; }}
            QLabel#proxyRulesTitle {{ color: {text}; font-size: 15px; font-weight: 800; padding: 6px 2px; }}
            QLabel#proxySettingsHint {{ color: {muted}; font-size: 11px; }}
            QLineEdit#proxySettingsSearch {{ background: {surface}; color: {text}; border: 1px solid {border}; border-radius: 10px; padding: 7px 11px; selection-background-color: {accent}; selection-color: #ffffff; }}
            QLineEdit#proxySettingsSearch:focus {{ border-color: {accent}; }}
            QPushButton#proxySettingCategory {{ min-height: 34px; text-align: left; padding: 0 5px; background: transparent; color: {text}; border: 1px solid transparent; border-radius: 8px; font-size: 10px; font-weight: 650; }}
            QPushButton#proxySettingCategory:hover {{ background: {hover}; border-color: {border}; }}
            QPushButton#proxySettingCategory:checked {{ background: {accent}; color: #ffffff; border-color: {accent}; font-weight: 750; }}
            QLabel {{ background: transparent; }}
            QLineEdit, QTextEdit, QListWidget {{ background: {surface}; color: {text}; border: 1px solid {border}; border-radius: 8px; padding: 7px; selection-background-color: {accent}; selection-color: #ffffff; }}
            QCheckBox {{ color: {text}; spacing: 7px; }}
            QPushButton {{ min-height: 32px; padding: 0 10px; background: transparent; color: {text}; border: 1px solid {border}; border-radius: 8px; font-weight: 600; }}
            QPushButton:hover {{ background: {hover}; border-color: {accent}; }}
            QPushButton#proxyHostAddButton {{ background: {accent}; color: #ffffff; border-color: {accent}; }}
            QPushButton#proxyHostAddButton:hover {{ background: {accent}; color: #ffffff; }}
            QScrollBar:vertical {{ background: transparent; width: 9px; margin: 2px; }}
            QScrollBar::handle:vertical {{ background: {"#4b5b70" if dark else "#bdc8d8"}; min-height: 24px; border-radius: 4px; }}
            QScrollBar::handle:vertical:hover {{ background: {"#6a809c" if dark else "#94a8c4"}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
            QScrollBar:horizontal {{ background: transparent; height: 9px; margin: 2px; }}
            QScrollBar::handle:horizontal {{ background: {"#4b5b70" if dark else "#bdc8d8"}; min-width: 24px; border-radius: 4px; }}
            QScrollBar::handle:horizontal:hover {{ background: {"#6a809c" if dark else "#94a8c4"}; }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: transparent; }}
        """)
        self._update_category_icons()
        if hasattr(self, "menu_toggle"):
            opened = bool(getattr(self, "_category_menu_open", False))
            self.menu_toggle.setIcon(qta.icon(
                "fa6s.xmark" if opened else "fa6s.bars",
                color="#ffffff" if opened and dark else ("#253041" if not dark else "#e8edf3"),
            ))
        if hasattr(self, "btn_qrcode"):
            self.btn_qrcode.setIcon(qta.icon("fa6s.qrcode", color="#eff1f4" if dark else "#202832"))

    def _update_category_icons(self):
        icon_names = {
            "bridges": "fa6s.link",
            "ports": "fa6s.network-wired",
            "blocked hosts": "fa6s.shield-halved",
            "excluded hosts": "fa6s.route",
            "advanced": "fa6s.sliders",
        }
        for key, button in self._category_buttons.items():
            color = "#ffffff" if button.isChecked() else ("#e8edf3" if self._dark_mode == "dark" else "#253041")
            button.setIcon(qta.icon(icon_names[key], color=color))

    def initialize_first_page(self):
        mode_layout = QHBoxLayout()
        self.first_page_layout.addLayout(mode_layout)


      
        # bridge checkbox
        btn_bridge = QCheckBox("bridge", self)
        btn_bridge.setChecked(bool(CONFIG["bridge"]))
        btn_bridge.stateChanged.connect(self.bridge_state_changed)
        self.first_page_layout.addWidget(btn_bridge)

        self.inp_bridges = QTextEdit(self, placeholderText="Paste bridge records (obfs4, Snowflake or WebTunnel)…")
        self.inp_bridges.setMinimumHeight(90)
        self.inp_bridges.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.inp_bridges.setText(CONFIG["bridges"] or "")
        self.inp_bridges.setEnabled(bool(CONFIG["bridge"]))
        self.inp_bridges.textChanged.connect(self.set_bridges)
        self.first_page_layout.addWidget(self.inp_bridges)

        self.btn_qrcode = QPushButton("Import bridges from QR code")
        self.btn_qrcode.clicked.connect(self.show_qrcode)
        self.first_page_layout.addWidget(self.btn_qrcode)

        self.qrcode_widget = QrCodeFloatingWindow(self)
        self.threadpool = QThreadPool(self)


    def initialize_advanced_page(self):
        self.advanced_page = QWidget()
        self.advanced_page.setObjectName("proxySettingsContent")
        self.advanced_page_layout = QVBoxLayout(self.advanced_page)
        self.advanced_page_layout.setContentsMargins(12, 12, 12, 12)
        self.advanced_page_layout.setSpacing(12)
        self.advanced_page_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        title = QLabel("Advanced Tor settings", self.advanced_page)
        title.setObjectName("proxyRulesTitle")
        subtitle = QLabel("Connection rotation and circuit lifetime behavior.", self.advanced_page)
        subtitle.setWordWrap(True)
        self.advanced_page_layout.addWidget(title)
        self.advanced_page_layout.addWidget(subtitle)

        max_circuit_row = QHBoxLayout()
        max_circuit_row.addWidget(QLabel("MaxCircuitDirtiness"))
        try:
            initial_value = getattr(self._parent.proxyWidget.tor, "MaxCircuitDirtiness")
            if initial_value is None:
                initial_value = CONFIG["MaxCircuitDirtiness"] or 600
        except Exception:
            initial_value = CONFIG["MaxCircuitDirtiness"] or 600
        self.inp_MaxCircuitDirtiness = QLineEdit(str(initial_value))
        self.inp_MaxCircuitDirtiness.setObjectName("maxCircuitDirtinessInput")
        self.inp_MaxCircuitDirtiness.setToolTip("Maximum lifetime of a Tor circuit, in seconds.")
        self.inp_MaxCircuitDirtiness.textChanged.connect(self.MaxCircuitDirtiness_changed)
        max_circuit_row.addWidget(self.inp_MaxCircuitDirtiness, 1)
        self.lbl_MaxCircuitDirtiness = QLabel(CORRECT)
        max_circuit_row.addWidget(self.lbl_MaxCircuitDirtiness)
        self.advanced_page_layout.addLayout(max_circuit_row)

        newnym_row = QHBoxLayout()
        newnym_row.addWidget(QLabel("Request new identity every"))
        try:
            newnym_start = self._parent.proxyWidget.timer.interval()
        except Exception:
            newnym_start = CONFIG["newnym_interval"] or 60000
        self.newnym_inp = QLineEdit(str(newnym_start))
        self.newnym_inp.setObjectName("newIdentityIntervalInput")
        self.newnym_inp.setToolTip("Interval in milliseconds between automatic NEWNYM requests.")
        self.newnym_inp.textChanged.connect(self.newnym_inp_changed)
        newnym_row.addWidget(self.newnym_inp, 1)
        newnym_row.addWidget(QLabel("ms"))
        self.newnym_lbl_stat = QLabel(f"({int(newnym_start) // 1000} sec) " + CORRECT)
        newnym_row.addWidget(self.newnym_lbl_stat)
        self.advanced_page_layout.addLayout(newnym_row)

        note = QLabel("These values are applied to Tor when the connection is started.", self.advanced_page)
        note.setWordWrap(True)
        note.setObjectName("proxySettingsHint")
        self.advanced_page_layout.addWidget(note)

        advanced_scroll = QScrollArea(self.page_setting)
        advanced_scroll.setWidgetResizable(True)
        advanced_scroll.setFrameShape(QFrame.Shape.NoFrame)
        advanced_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        advanced_scroll.setWidget(self.advanced_page)
        self.page_setting.addWidget(advanced_scroll)
        self._category_pages["advanced"] = advanced_scroll

    def initialize_second_page(self):
        self.second_page = QWidget()
        self.second_page.setObjectName("proxySettingsContent")
        self.second_page_layout = QVBoxLayout(self.second_page)
        self.second_page_layout.setContentsMargins(12, 10, 12, 12)
        self.second_page_layout.setSpacing(10)
        self.second_page_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        ports_scroll = QScrollArea(self.page_setting)
        ports_scroll.setWidgetResizable(True)
        ports_scroll.setFrameShape(QFrame.Shape.NoFrame)
        ports_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        ports_scroll.setWidget(self.second_page)
        self.page_setting.addWidget(ports_scroll)
        self._category_pages["ports"] = ports_scroll

        ports = ["tor_port", "proxy_port", "dns_port", "control_port"]
        for port in ports:
            lyt = QHBoxLayout()
            lbl = QLabel(port)
            inp_port = QLineEdit()

            # populate input with existing value if present (avoid "None" string)
            current_val = CONFIG[port]
            inp_port.setText(str(current_val) if current_val is not None else "")

            enabled_initial = bool(CONFIG[port + "_checked"]) if CONFIG[port + "_checked"] is not None else False
            inp_port.setEnabled(enabled_initial)

            lbl_status = QLabel(CORRECT if enabled_initial and self._is_valid_port(current_val) else WRONG)
            check_port = QCheckBox()
            check_port.setChecked(enabled_initial)

            # connect text changed -> validator (partial binds the widgets)
            inp_port.textChanged.connect(partial(self.inp_port_changed, inp_port, lbl_status, port))

            # connect checkbox state change -> enable/disable input and update CONFIG
            # stateChanged provides an int state; partial with keywords keeps signature clean
            check_port.stateChanged.connect(partial(self.check_port_changed, inp_port=inp_port, lbl_status=lbl_status, port=port))

            lyt.addWidget(lbl)
            lyt.addWidget(inp_port)
            lyt.addWidget(lbl_status)
            lyt.addWidget(check_port)

            self.second_page_layout.addLayout(lyt)
        
   
    def inp_port_changed(self, inp_port, lbl_status, port, text=None):
        if text is None:
            value = inp_port.text().strip()
        else:
            value = str(text).strip()

        if value and self._is_valid_port(value):
            lbl_status.setText(CORRECT)
            try:
                CONFIG[port] = int(value)
            except Exception:
                CONFIG[port] = value
            try:
                proxy = getattr(self._parent, "proxyWidget", None)
                if proxy and hasattr(proxy, "set_port"):
                    proxy.set_port(port, int(value))
                elif proxy:
                    setattr(proxy, port, int(value))
            except Exception:
                pass
        else:
            lbl_status.setText(WRONG)
            try:
                CONFIG[port] = None
            except Exception:
                pass


    def check_port_changed(self, state: int, inp_port: QLineEdit = None, lbl_status: QLabel = None, port: str = ""):
        # Qt sends state (int). Convert to boolean
        enabled = bool(state)
        if inp_port is not None:
            inp_port.setEnabled(enabled)

        try:
            CONFIG[port + "_checked"] = bool(enabled)
        except Exception:
            pass

        val_text = inp_port.text().strip() if inp_port is not None else ""
        if enabled and self._is_valid_port(val_text):
            if lbl_status is not None:
                lbl_status.setText(CORRECT) 
        elif enabled:
            if lbl_status is not None:
                lbl_status.setText(WRONG)
        else:
            if lbl_status is not None:
                lbl_status.setText(WRONG)

    # ---------- other helpers ----------
    def go_to_before_page(self):
        self._set_settings_page(max(0, self.page_setting.currentIndex() - 1))

    def go_to_next_page(self):
        self._set_settings_page(min(self.page_setting.count() - 1, self.page_setting.currentIndex() + 1))

    def show_qrcode(self):
        worker = Worker(self.qrcode_widget.run)
        worker.signals.finished.connect(self.show_qrcode_widget)
        worker.signals.error.connect(self.show_qrcode_widget)
        self.threadpool.start(worker)
        self.btn_qrcode.setDisabled(True)

    def show_qrcode_widget(self, *args):
        self.qrcode_widget.setParent(self)
        self.qrcode_widget.move(0, 0)
        self.qrcode_widget.show()
        self.qrcode_widget.timer.start(30)
        self.btn_qrcode.setEnabled(True)
        
    def newnym_inp_changed(self):
        text = self.newnym_inp.text().strip()
        if text and text.isdigit() and 0 < int(text) < 2_147_483_647:
            try:
                interval = int(text)
                # set to parent timer if exists
                try:
                    self._parent.proxyWidget.timer.setInterval(interval)
                except Exception:
                    pass
                self.newnym_lbl_stat.setText(f"({interval//1000} sec)  " + CORRECT )
                CONFIG["newnym_interval"] = interval
            except OverflowError:
                logger.error("newnym interval overflow: %s", text)
                self.newnym_lbl_stat.setText(WRONG)
        else:
            self.newnym_lbl_stat.setText(WRONG)

    def MaxCircuitDirtiness_changed(self):
        text = self.inp_MaxCircuitDirtiness.text().strip()
        if text and text.isdigit():
            val = int(text)
            try:
                self._parent.proxyWidget.tor.MaxCircuitDirtiness = val
            except Exception:
                pass
            CONFIG["MaxCircuitDirtiness"] = val
            self.lbl_MaxCircuitDirtiness.setText(CORRECT)
        else:
            self.lbl_MaxCircuitDirtiness.setText(WRONG)

    def set_bridges(self):
        txt = self.inp_bridges.toPlainText()
        try:
            self._parent.proxyWidget.tor.bridges = txt
        except Exception:
            pass
        CONFIG["bridges"] = txt

    def bridge_state_changed(self, state):
        checked = bool(state)
        try:
            self._parent.proxyWidget.tor.bridge = checked
        except Exception:
            pass
        self.inp_bridges.setEnabled(checked)
        CONFIG["bridge"] = bool(checked)


    # small utility
    @staticmethod
    def _is_valid_port(value):
        try:
            p = int(value)
            return 0 < p <= 65535
        except Exception:
            return False
