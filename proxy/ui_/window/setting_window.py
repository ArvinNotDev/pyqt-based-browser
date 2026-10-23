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
    def __init__(self, parent=None):
        super().__init__(parent)
        self._parent = parent
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 8, 10, 10)
        main_layout.setSpacing(8)

        navigation = QHBoxLayout()
        navigation.setSpacing(6)
        self.settings_nav_group = QButtonGroup(self)
        self.settings_nav_group.setExclusive(True)
        self.settings_nav_buttons = []
        for index, (label, icon_name) in enumerate((
            ("Bridges", "fa6s.link"), ("Ports", "fa6s.network-wired")
        )):
            button = QPushButton(label, self)
            button.setObjectName("proxySettingsNavButton")
            button.setIcon(qta.icon(icon_name))
            button.setIconSize(QSize(14, 14))
            button.setCheckable(True)
            button.setMinimumHeight(34)
            button.clicked.connect(lambda _checked=False, page=index: self._set_settings_page(page))
            self.settings_nav_group.addButton(button, index)
            self.settings_nav_buttons.append(button)
            navigation.addWidget(button, 1)
        main_layout.addLayout(navigation)

        self.lbl_page_number = QLabel("Page: 1", self)
        self.lbl_page_number.hide()
        self.page_setting = QStackedWidget(self)
        self.page_setting.setObjectName("proxySettingsPages")
        main_layout.addWidget(self.page_setting, 1)

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

        self.initialize_first_page()
        self.initialize_second_page()
        self.settings_nav_buttons[0].setChecked(True)

        if getattr(self._parent, "_embedded", False):
            rules_row = QHBoxLayout()
            self.btn_block_hosts = QPushButton("Blocked hosts…", self)
            self.btn_block_hosts.setToolTip("Manage hosts blocked from browsing.")
            self.btn_block_hosts.clicked.connect(self._parent._show_block_host)
            self.btn_exclude_hosts = QPushButton("Excluded hosts…", self)
            self.btn_exclude_hosts.setToolTip("Manage hosts that bypass Tor routing.")
            self.btn_exclude_hosts.clicked.connect(self._parent._show_exclude_host)
            rules_row.addWidget(self.btn_block_hosts, 1)
            rules_row.addWidget(self.btn_exclude_hosts, 1)
            main_layout.addLayout(rules_row)
        self.apply_theme(getattr(self._parent, "_display_mode", "dark"))

    def _set_settings_page(self, index):
        if not 0 <= index < self.page_setting.count():
            return
        self.page_setting.setCurrentIndex(index)
        for page_index, button in enumerate(self.settings_nav_buttons):
            button.setChecked(page_index == index)
        self.lbl_page_number.setText(f"Page: {index + 1}")

    def apply_theme(self, mode="dark"):
        dark = mode == "dark"
        border = "#394655" if dark else "#d7e0eb"
        panel = "#202630" if dark else "#f7f9fc"
        text = "#e8edf3" if dark else "#253247"
        accent = "#65aaf6" if dark else "#176fc1"
        hover = "rgba(101,170,246,0.13)" if dark else "rgba(23,111,193,0.08)"
        self.setStyleSheet(f"""
            QWidget {{ color: {text}; background: transparent; }}
            QWidget#proxySettingsContent {{ background: {panel}; }}
            QLabel {{ color: {text}; }}
            QLineEdit, QTextEdit, QListWidget {{ background: {"#171c23" if dark else "#ffffff"}; color: {text}; border: 1px solid {border}; border-radius: 8px; padding: 7px; selection-background-color: {accent}; }}
            QCheckBox {{ spacing: 7px; }}
            QPushButton {{ min-height: 32px; padding: 0 10px; background: transparent; color: {text}; border: 1px solid {border}; border-radius: 8px; font-weight: 600; }}
            QPushButton:hover {{ background: {hover}; border-color: {accent}; }}
            QPushButton#proxySettingsNavButton {{ min-height: 34px; padding: 0 8px; border-color: transparent; }}
            QPushButton#proxySettingsNavButton:checked {{ background: {"#314c70" if dark else "#dce9fc"}; border-color: {"#5276a4" if dark else "#b8d0f3"}; }}
            QPushButton#proxySettingsBackButton {{ min-height: 32px; border: 1px solid {border}; border-radius: 8px; background: transparent; color: {text}; }}
            QPushButton#proxySettingsBackButton:hover {{ border-color: {accent}; background: {hover}; }}
            QScrollBar:vertical {{ background: transparent; width: 9px; margin: 2px; }}
            QScrollBar::handle:vertical {{ background: {"#4b5b70" if dark else "#bdc8d8"}; min-height: 24px; border-radius: 4px; }}
            QScrollBar::handle:vertical:hover {{ background: {"#6a809c" if dark else "#94a8c4"}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
        """)

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

        max_circuit_dirtiness_layout = QHBoxLayout()
        max_circuit_dirtiness_layout.addWidget(QLabel("MaxCircuitDirtiness  "))
        self.first_page_layout.addLayout(max_circuit_dirtiness_layout)

        # read from parent.tor if available, else from CONFIG or fallback
        try:
            start_val = getattr(self._parent.proxyWidget.tor, "MaxCircuitDirtiness")
            if start_val is None:
                start_val = CONFIG["MaxCircuitDirtiness"] or 10
        except Exception:
            start_val = CONFIG["MaxCircuitDirtiness"] or 10

        self.inp_MaxCircuitDirtiness = QLineEdit(str(start_val))
        max_circuit_dirtiness_layout.addWidget(self.inp_MaxCircuitDirtiness)
        self.inp_MaxCircuitDirtiness.textChanged.connect(self.MaxCircuitDirtiness_changed)
        self.lbl_MaxCircuitDirtiness = QLabel(CORRECT)
        max_circuit_dirtiness_layout.addWidget(self.lbl_MaxCircuitDirtiness)

        newnym_layout = QHBoxLayout()
        self.first_page_layout.addLayout(newnym_layout)
        newnym_layout.addWidget(QLabel("SIGNAL NEWNYM sends every"))

        # try to read from parent.timer if exists, else from CONFIG, else default 60000
        try:
            newnym_start = self._parent.proxyWidget.timer.interval()
        except Exception:
            newnym_start = CONFIG["newnym_interval"] or 60000

        self.newnym_inp = QLineEdit(str(newnym_start))
        newnym_layout.addWidget(self.newnym_inp)
        self.newnym_inp.textChanged.connect(self.newnym_inp_changed)
        newnym_layout.addWidget(QLabel("mili sec"))
        self.newnym_lbl_stat = QLabel(f"({int(newnym_start)//1000} sec) "+ CORRECT)
        newnym_layout.addWidget(self.newnym_lbl_stat)
        self.qrcode_widget = QrCodeFloatingWindow(self)

        self.threadpool = QThreadPool()

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
