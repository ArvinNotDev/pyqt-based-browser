from PySide6.QtWidgets import (
    QLabel, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QMessageBox, QFrame,
)
from PySide6.QtCore import (
    Qt, QTimer, QThreadPool, Signal, QPropertyAnimation, QEasingCurve, QRect,
)
import qtawesome as qta
from stem import Signal as TorSignal
from stem.control import Controller
from stem import SocketClosed, OperationFailed
from stem.connection import AuthenticationFailure

from proxy.proxy import get_free_port, is_port_free
from proxy import proxy
from proxy.set_proxy import manage_proxy
from proxy.tor import TorRunner, Runner

from proxy.whatismyip import what_is_my_ip
from proxy.ui_.window.log_window import LogWindow
from proxy.ui_.btn.pulse_button import PulseButton
from proxy.ui_.worker.worker import Worker
from proxy.ui_.worker.utils import Data
from proxy.ui_.emojis import CHANGE_IDENTITY, LOGS, WHAT_IS_MY_IP, TAP_TO_CONNECT
from proxy.config import CONFIG
import json
import logging

logger = logging.getLogger(__name__)



class ProxyWindow(QWidget):
    stop_timer = Signal()
    tor_status_signal = Signal(str)
    tor_log_signal = Signal(str)
    tor_exit_signal = Signal(str)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.data = Data()
        self.running = False
        self.connected = False
        self.failed = False
        self.controller = None
        self._stopping = False
        self._identity_busy = False
        self._parent = parent
        self.tor_socks_port = self._initial_port("tor_port")
        self.proxy_port = self._initial_port("proxy_port")
        self.tor_control_port = self._initial_port("control_port")
        self.tor_dns_port = self._initial_port("dns_port")
        self.tor = TorRunner(self.tor_socks_port, self.tor_control_port, self.tor_dns_port)
        self.tor.bridge = bool(CONFIG["bridge"])
        self.tor.bridges = str(CONFIG["bridges"] or "")
        self.tor.app_window = self
        self.proxy = Runner(self.proxy_port, self.tor_socks_port, self)

        self.logs_widget = LogWindow(self)
        self.logs_widget.apply_theme(getattr(parent, "_display_mode", "dark"))
        self.logs_widget.hide()
        self.logs_open = False
        self._logs_animation = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.home_content = QWidget(self)
        self.home_content.setObjectName("homeContent")
        root.addWidget(self.home_content, 1)
        self.home_layout = QVBoxLayout(self.home_content)
        self.home_layout.setContentsMargins(16, 14, 16, 14)
        self.home_layout.setSpacing(9)

        brand = QVBoxLayout()
        brand.setSpacing(2)
        self.home_title = QLabel("TOR CONNECTION")
        self.home_title.setObjectName("homeEyebrow")
        self.home_subtitle = QLabel("Private routing for this browser")
        self.home_subtitle.setObjectName("homeSubtitle")
        brand.addWidget(self.home_title)
        brand.addWidget(self.home_subtitle)
        self.home_layout.addLayout(brand)

        self.btn_status = QLabel("NOT CONNECTED")
        self.btn_status.setObjectName("connectionStatus")
        self.btn_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.btn_status.setWordWrap(True)
        self.set_btn_status_style("disconnected")
        self.home_layout.addWidget(self.btn_status)

        connect_host = QWidget(self.home_content)
        connect_row = QHBoxLayout(connect_host)
        connect_row.setContentsMargins(0, 2, 0, 2)
        connect_row.addStretch(1)
        self.connect_btn = PulseButton("Connect")
        self.connect_btn.setObjectName("connectPulseButton")
        self.connect_btn.clicked.connect(self._toggle)
        connect_row.addWidget(self.connect_btn, 0, Qt.AlignmentFlag.AlignCenter)
        connect_row.addStretch(1)
        self.home_layout.addWidget(connect_host, 1)

        metrics = QHBoxLayout()
        metrics.setContentsMargins(0, 2, 0, 2)
        metrics.setSpacing(10)
        self.lbl_percent = QLabel("0%")
        self.lbl_percent.setObjectName("bootstrapPercent")
        self.lbl_data_usage = QLabel(f"Proxy traffic · {CONFIG['data_usage'] / 1024**2:.2f} MiB")
        self.lbl_data_usage.setObjectName("trafficUsage")
        metrics.addStretch(1)
        metrics.addWidget(self.lbl_percent)
        separator = QFrame(self.home_content)
        separator.setObjectName("homeMetricSeparator")
        separator.setFrameShape(QFrame.Shape.VLine)
        metrics.addWidget(separator)
        metrics.addWidget(self.lbl_data_usage)
        metrics.addStretch(1)
        self.home_layout.addLayout(metrics)

        self.route_status_label = QLabel("Tor routing stays blocked until the connection is verified.")
        self.route_status_label.setObjectName("routeStatusLabel")
        self.route_status_label.setWordWrap(True)
        self.route_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.home_layout.addWidget(self.route_status_label)
        self.tor_ip_label = QLabel("Exit IP: not checked")
        self.tor_ip_label.setObjectName("exitIpLabel")
        self.tor_ip_label.setWordWrap(True)
        self.tor_ip_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.home_layout.addWidget(self.tor_ip_label)

        utility_row = QHBoxLayout()
        utility_row.setContentsMargins(0, 3, 0, 0)
        utility_row.setSpacing(6)
        self.btn_change_identity = QPushButton(qta.icon("fa6s.arrows-rotate"), "Identity")
        self.btn_change_identity.setObjectName("secondaryAction")
        self.btn_change_identity.setToolTip("Request a new Tor identity")
        self.btn_change_identity.setEnabled(False)
        self.btn_change_identity.clicked.connect(self.change_identity_)
        utility_row.addWidget(self.btn_change_identity, 1)
        self.btn_log = QPushButton(qta.icon("fa6s.align-left"), "Event log")
        self.btn_log.setObjectName("secondaryAction")
        self.btn_log.setCheckable(True)
        self.btn_log.setToolTip("Show live Tor and proxy events")
        self.btn_log.clicked.connect(self.show_logs)
        utility_row.addWidget(self.btn_log, 1)
        self.btn_whatismyip = QPushButton(qta.icon("fa6s.globe"), "Exit IP")
        self.btn_whatismyip.setObjectName("secondaryAction")
        self.btn_whatismyip.setToolTip("Verify the public IP through the Tor proxy")
        self.btn_whatismyip.setEnabled(False)
        self.btn_whatismyip.clicked.connect(self.whatismyip_clicked)
        utility_row.addWidget(self.btn_whatismyip, 1)
        self.home_layout.addLayout(utility_row)

        self.data.valueChanged.connect(self.dataValueChanged)
        self.tor_status_signal.connect(self.dataValueChanged)
        self.tor_log_signal.connect(self.logs_widget.update_log)
        self.tor_exit_signal.connect(self._tor_exited)
        self.timer = QTimer(self)
        try:
            interval = max(0, int(CONFIG["newnym_interval"] or 0))
        except (TypeError, ValueError):
            interval = 0
        self.timer.setInterval(interval)
        self.timer.timeout.connect(self.change_identity_)
        self.stop_timer.connect(self.stop_timers)
        self.timer_data_usage = QTimer(self)
        self.timer_data_usage.setInterval(1000)
        self.timer_data_usage.timeout.connect(self.change_data_usage)
        self._apply_home_theme()

    def _apply_home_theme(self):
        dark = (getattr(self._parent, "_display_mode", CONFIG["mode"])) == "dark"
        border = "#394655" if dark else "#d7e0eb"
        muted = "#9caabb" if dark else "#64748b"
        accent = "#65aaf6" if dark else "#176fc1"
        surface = "#202630" if dark else "#f7f9fc"
        text = "#e8edf3" if dark else "#243247"
        hover = "rgba(101,170,246,0.13)" if dark else "rgba(23,111,193,0.08)"
        self.home_content.setStyleSheet(f"""
            QWidget#homeContent {{ background: {surface}; color: {text}; }}
            QLabel#homeEyebrow {{ background: transparent; color: {accent}; font-size: 10px; font-weight: 850; letter-spacing: 1.1px; }}
            QLabel#homeSubtitle {{ background: transparent; color: {muted}; font-size: 10px; }}
            QLabel#connectionStatus {{ color: {text}; background: transparent; border: none; padding: 4px; font-size: 12px; font-weight: 750; }}
            QLabel#connectionStatus[connectionState="connected"] {{ color: #2eae69; }}
            QLabel#connectionStatus[connectionState="connecting"] {{ color: {accent}; }}
            QLabel#connectionStatus[connectionState="disconnected"] {{ color: {text}; }}
            QLabel#bootstrapPercent {{ color: {accent}; background: transparent; font-size: 12px; font-weight: 800; }}
            QLabel#trafficUsage, QLabel#routeStatusLabel, QLabel#exitIpLabel {{ color: {muted}; background: transparent; border: none; font-size: 11px; padding: 2px; }}
            QFrame#homeMetricSeparator {{ color: {border}; background: {border}; max-width: 1px; }}
            QPushButton#connectPulseButton {{ background: transparent; border: none; padding: 0; margin: 0; }}
            QPushButton#connectPulseButton:hover, QPushButton#connectPulseButton:pressed, QPushButton#connectPulseButton:focus {{ background: transparent; border: none; }}
            QPushButton#secondaryAction {{ min-height: 34px; padding: 0 6px; border-radius: 8px; background: transparent; color: {text}; border: 1px solid {border}; font-size: 10px; font-weight: 650; }}
            QPushButton#secondaryAction:hover {{ background: {hover}; border-color: {accent}; }}
            QPushButton#secondaryAction:checked {{ background: {hover}; border-color: {accent}; }}
            QPushButton#secondaryAction:disabled {{ color: {muted}; background: transparent; }}
        """)
        self.logs_widget.apply_theme("dark" if dark else "light")
        self.btn_change_identity.setIcon(qta.icon("fa6s.arrows-rotate", color=text))
        self.btn_log.setIcon(qta.icon("fa6s.align-left", color=text))
        self.btn_whatismyip.setIcon(qta.icon("fa6s.globe", color=text))

    def apply_theme(self, mode=None):
        if mode in {"dark", "light"}:
            self._parent._display_mode = mode
        self._apply_home_theme()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.logs_open and self._logs_animation is None:
            width = self._log_drawer_width()
            self.logs_widget.setGeometry(QRect(0, 0, width, self.height()))

    def _log_drawer_width(self):
        available = max(1, self.width())
        return min(available, max(220, min(360, int(available * 0.84))))

    @staticmethod
    def _initial_port(config_key):
        value = CONFIG[config_key]
        if CONFIG[config_key + "_checked"] and isinstance(value, int) and 1 <= value <= 65535:
            if config_key == "proxy_port" and not is_port_free("127.0.0.1", value):
                logger.warning("Configured proxy port is already occupied; using a free loopback port")
                return get_free_port()
            return value
        return get_free_port()

    def stop_timers(self):
        self.timer.stop()
        self.timer_data_usage.stop()
        self.connect_btn._idle_timer.stop()

    
    def change_data_usage(self):
        self.lbl_data_usage.setText(f"Data usage: {CONFIG['data_usage']/1024**2:.2f} Mb")

    
    def whatismyip_clicked(self):
        self.worker = Worker(lambda: what_is_my_ip(proxy=f"http://127.0.0.1:{self.proxy_port}"))
        self.worker.signals.finished.connect(self._on_ip_result)
        self.worker.signals.error.connect(self._on_ip_error)
        self.thread_pool.start(self.worker)
        self.btn_whatismyip.setDisabled(True)

    def _on_ip_result(self, address):
        self.tor_ip_label.setText("ip: " + address)
        self.btn_whatismyip.setEnabled(True)

    def _on_ip_error(self, _error):
        self.tor_ip_label.setText("ip: error")
        self.btn_whatismyip.setEnabled(True)
        
    def show_logs(self):
        opening = not self.logs_open
        self.logs_open = opening
        self.btn_log.setChecked(opening)
        if self._logs_animation is not None:
            self._logs_animation.stop()
        width = self._log_drawer_width()
        height = max(1, self.height())
        if opening:
            self.logs_widget.setGeometry(QRect(-width, 0, width, height))
            self.logs_widget.show()
            self.logs_widget.raise_()
        start_rect = self.logs_widget.geometry()
        end_rect = QRect(0, 0, width, height) if opening else QRect(-width, 0, width, height)
        animation = QPropertyAnimation(self.logs_widget, b"geometry", self)
        animation.setDuration(220)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic if opening else QEasingCurve.Type.InCubic)
        animation.setStartValue(start_rect)
        animation.setEndValue(end_rect)
        def finished():
            self._logs_animation = None
            if not self.logs_open:
                self.logs_widget.hide()
        animation.finished.connect(finished)
        self._logs_animation = animation
        animation.start()

    def change_identity_(self):
        if self._identity_busy or not self.connected:
            return
        self._identity_busy = True
        self.btn_change_identity.setEnabled(False)
        worker = Worker(self.change_identity)
        worker.signals.finished.connect(self._on_identity_finished)
        worker.signals.error.connect(self._on_identity_error)
        self.thread_pool.start(worker)

    def _on_identity_finished(self, result):
        self._identity_busy = False
        self.btn_change_identity.setEnabled(bool(self.connected))
        if isinstance(result, dict) and result.get("wait", 0) > 0:
            self.logs_widget.update_log(
                f"Tor rate-limits identity requests; try again in about {result['wait']:.0f} seconds.",
                level="warning",
            )
        elif result is True:
            self.logs_widget.update_log("Tor accepted the new identity request.")
        else:
            self.logs_widget.update_log("Tor did not accept the identity request.", level="warning")

    def _on_identity_error(self, error):
        self._identity_busy = False
        self.btn_change_identity.setEnabled(bool(self.connected))
        self.logs_widget.update_log(f"Identity change failed: {error}", level="error")

    def change_identity(self):
        if not self.connected:
            logger.warning("Identity change requested while Tor is not connected.")
            return False
        try:
            request = getattr(self.tor, "request_new_identity", None)
            if callable(request):
                wait = float(request() or 0)
                return {"wait": wait} if wait > 0 else True
            if self.controller is None:
                raise RuntimeError("Tor ControlPort is not available.")
            wait = float(self.controller.get_newnym_wait())
            if wait > 0:
                return {"wait": wait}
            self.controller.signal(TorSignal.NEWNYM)
            return True
        except SocketClosed:
            logger.error("Tor control socket is closed; marking connection as disconnected.")
            self.connected = False
            return False
        except AuthenticationFailure:
            logger.error("Tor ControlPort authentication failed.")
            return False
        except OperationFailed:
            logger.warning("Tor rejected NEWNYM, likely because of its rate limit.")
            return False
        except Exception:
            logger.exception("Unexpected error while changing Tor identity.")
            return False

    def dataValueChanged(self, v):
        self.lbl_percent.setText(str(v)+"")
        if v != "100%" or not self.running or self.connected:
            return

        # Switch the browser only after Tor reports a complete bootstrap.
        proxy.set_tor_routing(True)
        self.controller = None
        try:
            self.controller = Controller.from_port(
                address="127.0.0.1", port=self.tor.contorl_port, timeout=5
            )
            self.controller.authenticate()
        except Exception as exc:
            logger.warning("Tor control port unavailable (%s); browser routing remains on Tor", type(exc).__name__)

        self._parent._notify("Tor Proxy", "Connected through Tor")
        self.connected = True
        self.connect_btn.set_connected(True)
        self.btn_whatismyip.setEnabled(True)
        self._parent._parent.reload_engine()
        self.btn_status.setText("connected")
        self.set_btn_status_style("connected")
        if self.timer.interval() > 0:
            self.timer.start()
        self.timer_data_usage.start()
        self.btn_change_identity.setEnabled(True)
        
        
    def set_btn_status_style(self, stmt):
        self.btn_status.setProperty("connectionState", stmt)
        self.btn_status.style().unpolish(self.btn_status)
        self.btn_status.style().polish(self.btn_status)
        self.btn_status.update()
        if hasattr(self, "route_status_label"):
            if stmt == "connected":
                self.route_status_label.setText("Tor is verified. Browser traffic can use the protected route.")
                self.btn_change_identity.setEnabled(True)
                self.btn_whatismyip.setEnabled(True)
            elif stmt in {"connecting", "disconnecting"}:
                self.route_status_label.setText("Establishing the Tor route. Traffic remains blocked until readiness is verified.")
                self.btn_change_identity.setEnabled(False)
                self.btn_whatismyip.setEnabled(False)
            else:
                self.route_status_label.setText("Tor routing stays blocked until the connection is verified.")
                self.btn_change_identity.setEnabled(False)
                self.btn_whatismyip.setEnabled(False)

    def _toggle(self):
        browser = self._parent._parent
        if self.running:
            self.connect_btn.set_disconnecting()
            browser._request_network_mode(False)
            return
        if not browser.tor_mode:
            browser._request_network_mode(True)
            return

        self.connect_btn.set_connecting()
        self.connect_btn.setEnabled(False)
        self.btn_status.setText("checking ports ...")
        self.set_btn_status_style("connecting")

        worker = Worker(self._check_ports_worker)
        worker.signals.finished.connect(self._on_ports_checked)
        worker.signals.error.connect(self._on_ports_check_error)
        self.thread_pool.start(worker)

    def _on_ports_check_error(self, error):
        """Restore the connect control when the background port check fails."""
        logger.error("Proxy port check failed: %s", error)
        self.btn_status.setText("port check failed")
        self.set_btn_status_style("disconnected")
        self.connect_btn.set_connected(False)
        self.connect_btn.setEnabled(True)

    # ===== slot that runs on main thread with the result =====
    def _on_ports_checked(self, result):
        """
        result == (ok, ports, messages)
        This runs in the GUI thread so it's safe to touch UI and self.proxy/self.tor.
        """

        try:
            ok, ports, messages = json.loads(result)
        except Exception:
            ok = False
            ports = {}
            messages = [f"Invalid result from port checker: {result!r}"]

        # log messages to widget (safe in main thread)
        for m in messages:
            try:
                self.logs_widget.update_log(m)
            except Exception:
                logger.info("log: %s", m)

        if not ok:
            # failed -> re-enable button and set disconnected style
            self.set_btn_status_style("disconnected")
            self.btn_status.setText("port check failed")
            self.connect_btn.setEnabled(True)
            self.connect_btn.set_connected(False)
            return

        # ok==True -> attempt to set ports and start services (on main thread)
        try:
            # set ports from the ports dict (only keys that passed checks)
            if "proxy_port" in ports:
                self.proxy.port = ports["proxy_port"]
                self.proxy_port = ports["proxy_port"]
            if "tor_port" in ports:
                self.tor.socks_port = ports["tor_port"]
                self.proxy.tor_socks_port = ports["tor_port"]
                if self.proxy.server is not None:
                    self.proxy.server.tor_socks_port = ports["tor_port"]
            if "control_port" in ports:
                self.tor.contorl_port = ports["control_port"]
                self.tor_control_port = ports["control_port"]
            if "dns_port" in ports:
                self.tor.dns_port = ports["dns_port"]

            # start services (wrap try/except)
            self.btn_status.setText("connecting . . .")
            self.set_btn_status_style("connecting")

            try:
                self.proxy.start()
            except Exception as exc:
                logger.exception("proxy.start() failed (%s)", type(exc).__name__)
                raise
            # Proxying begins only after the explicit Connect action. Hold browser
            # traffic at the local bridge while Tor starts, so startup fails closed.
            proxy.set_tor_routing(True)
            manage_proxy(self._parent.profile, "127.0.0.1", self.proxy.port, "set")
            self._parent._parent.reload_engine()
            self.running = True
            self._stopping = False
            self._tor_start_token = self.tor.begin_start()
            if self._tor_start_token is None:
                raise RuntimeError("Tor is already starting or running")
            self.btn_status.setText("preparing Tor . . .")
            worker = Worker(self._prepare_and_start_tor, self._tor_start_token, CONFIG["tor_path"])
            worker.signals.finished.connect(self._on_tor_prepared)
            worker.signals.error.connect(self._on_tor_prepare_error)
            self._tor_start_worker = worker
            self.thread_pool.start(worker)
            self.logs_widget.update_log("Local proxy started; waiting for Tor bootstrap.")
        except Exception as exc:
            logger.exception("Service startup failed (%s)", type(exc).__name__)
            if self.proxy.started:
                self.running = True
                self._enter_tor_failure(f"Tor startup failed ({type(exc).__name__})")
            else:
                self._stop_services()
            QMessageBox.critical(self, "Error", f"Start failed: {exc}")
        finally:
            # always re-enable the button
            self.connect_btn.setEnabled(True)

    def _prepare_and_start_tor(self, token, selected_path):
        try:
            if not self.tor.update_path(selected_path, token=token):
                raise RuntimeError("No checksum-verified compatible Tor bundle is available")
            if not self.tor.start(token=token):
                raise RuntimeError("Tor start was cancelled")
            return json.dumps({"token": token, "ok": True})
        except Exception as exc:
            return json.dumps({
                "token": token,
                "ok": False,
                "error": f"Tor startup failed ({type(exc).__name__})",
            })

    def _on_tor_prepared(self, result):
        try:
            data = json.loads(result)
            token = data["token"]
        except (TypeError, ValueError, KeyError):
            logger.error("Invalid result from Tor startup worker")
            if self.running:
                self._enter_tor_failure("Invalid result from Tor startup worker")
            return
        if token != self._tor_start_token or not self.running:
            return
        if not data.get("ok"):
            message = data.get("error", "Tor could not start")
            self._enter_tor_failure(message)
            QMessageBox.critical(self, "Tor startup failed", message)
            return
        self.btn_status.setText("waiting for Tor . . .")
        self.set_btn_status_style("connecting")
        self.logs_widget.update_log("Tor startup requested; waiting for bootstrap.")

    def _on_tor_prepare_error(self, error):
        logger.error("Tor startup worker failed: %s", error)
        if self.running:
            self._enter_tor_failure("Tor startup worker failed")

    def _enter_tor_failure(self, message):
        """Keep the browser on the proxy, where unavailable Tor means 502 errors."""
        self._tor_start_token = None
        proxy.set_tor_routing(True)
        try:
            self.tor.stop()
        except Exception as exc:
            logger.warning("Tor cleanup after failure failed (%s)", type(exc).__name__)
        self.connected = False
        self.running = True
        # Browser remains routed through the local proxy until the user
        # disconnects, even when Tor bootstrap itself has failed.
        self.connect_btn.set_connected(True)
        self.btn_whatismyip.setEnabled(False)
        self.timer.stop()
        self.timer_data_usage.stop()
        if self.controller:
            try:
                self.controller.close()
            except Exception:
                pass
            self.controller = None
        self.logs_widget.update_log(message)
        self.btn_status.setText("Tor unavailable; traffic blocked")
        self.set_btn_status_style("disconnected")
        self.connect_btn.setEnabled(True)

    def _tor_exited(self, message):
        if not self.running:
            return
        logger.error("%s", message)
        self.logs_widget.update_log(message)
        self._tor_start_token = None
        if self.connected:
            # Keep the browser pointed at the local proxy and retain Tor mode.
            # Its SOCKS connection now fails with 502 until the user disconnects.
            proxy.set_tor_routing(True)
            self.connected = False
            self.connect_btn.set_connected(True)
            self.btn_whatismyip.setEnabled(False)
            if self.controller:
                try:
                    self.controller.close()
                except Exception:
                    pass
                self.controller = None
            self.btn_status.setText("Tor unavailable; traffic blocked")
            self.set_btn_status_style("disconnected")
            self.timer.stop()
            self.timer_data_usage.stop()
            return
        self._enter_tor_failure(message)

   # ===== helper worker (runs in background) =====
    def _check_ports_worker(self):
        """
        Pure worker: no GUI ops here.
        Returns (ok: bool, ports: dict, messages: list[str])
        Clear and explicit failures list is used.
        """
        messages = []
        failures = []
        ports = {}

        checks = [
            ("proxy_port", "proxy_port_checked", "proxy port"),
            ("tor_port", "tor_port_checked", "tor socks port"),
            ("control_port", "control_port_checked", "tor control port"),
            ("dns_port", "dns_port_checked", "dns port"),
        ]

        for cfg_key, checked_key, human in checks:
            # read checked flag (use try/except because CONFIG may not have key)
            try:
                raw_checked = CONFIG[checked_key]
            except KeyError:
                # treat missing checked flag as disabled (like you asked)
                messages.append(f"{human}: missing checked flag '{checked_key}', treating as disabled.")
                continue

            checked = bool(raw_checked)
            messages.append(f"{human}: checked={checked}")

            # read raw port value
            try:
                raw = CONFIG[cfg_key]
            except KeyError:
                raw = None
            
                
                
                

            messages.append(f"{human}: value={raw!r}")

            if not checked:
                messages.append(f"{human}: disabled, skipping.")
                continue

            if raw is None or str(raw).strip() == "":
                failures.append(f"{human}: enabled but no value provided.")
                continue

            try:
                p = int(raw)
            except Exception:
                failures.append(f"{human}: value '{raw}' is not a valid integer.")
                continue
                
            if int(raw) in ports.values():
                failures.append(f"{human}: This port is duplicated.")
                continue

            if not (1 <= p <= 65535):
                failures.append(f"{human}: port {p} out of valid range (1-65535).")
                continue

            if cfg_key == "proxy_port" and self.proxy.started:
                if p != self.proxy.port:
                    messages.append(f"proxy port: browser session is using {self.proxy.port}; retaining its active local proxy port.")
                    ports[cfg_key] = self.proxy.port
                    continue
                messages.append(f"proxy port: {p} is the active local proxy port.")
                ports[cfg_key] = p
                continue

            # Check port free (bind-based). Wrap in try/except and log result.
            try:
                free = is_port_free("127.0.0.1", p)
            except Exception as e:
                free = False
                failures.append(f"{human}: error while checking port: {e}")
                logger.exception("is_port_free error for %s:%s", human, p)
                continue

            if not free:
                failures.append(f"{human}: port {p} not free.")
            else:
                messages.append(f"{human}: port {p} is free.")
                ports[cfg_key] = p

        # finalize messages and ok
        if failures:
            messages.append("Port checks failed.")
            messages.extend(failures)
            ok = False
        else:
            messages.append("All requested ports OK.")
            ok = True

        return json.dumps([ok, ports, messages])

    def _stop_services(self, reload_pages=True):
        if self._stopping:
            return
        if not self.running and not self.connected and not self.proxy.started:
            return
        self._stopping = True
        self._tor_start_token = None
        self.connect_btn.set_disconnecting()
        self.btn_status.setText("disconnecting . . .")
        self.set_btn_status_style("disconnecting")
        self.timer_data_usage.stop()
        self.timer.stop()

        proxy.set_tor_routing(False)
        try:
            manage_proxy(self._parent.profile, "127.0.0.1", self.proxy.port, "clear")
            if reload_pages:
                self._parent._parent.reload_engine()
        except Exception as exc:
            logger.warning("Could not clear browser proxy during shutdown (%s)", type(exc).__name__)

        if self.controller:
            try:
                self.controller.close()
            except Exception:
                pass
            self.controller = None
        try:
            self.tor.stop()
        except Exception as exc:
            logger.warning("Tor shutdown failed (%s)", type(exc).__name__)
        try:
            self.proxy.stop()
        except Exception as exc:
            logger.warning("Local proxy shutdown failed (%s)", type(exc).__name__)

        self.logs_widget.update_log("Proxy and Tor stopped.")
        self.running = False
        self.connected = False
        self.lbl_percent.setText("0%")
        self.btn_status.setText("disconnected")
        self.set_btn_status_style("disconnected")
        self.connect_btn.set_connected(False)
        self.connect_btn.setEnabled(True)
        self._stopping = False
        
