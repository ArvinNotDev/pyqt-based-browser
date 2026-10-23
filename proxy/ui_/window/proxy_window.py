from PySide6.QtWidgets import (
    QLabel,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QMessageBox,
)


from PySide6.QtCore import Qt, QTimer, QThreadPool, Signal
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
        self.controller = None
        self._stopping = False
        self._tor_start_token = None
        self._parent = parent
        self.tor_socks_port = self._initial_port("tor_port")
        self.proxy_port = self._initial_port("proxy_port")
        self.tor_control_port = self._initial_port("control_port")
        self.tor_dns_port = self._initial_port("dns_port")
        logger.info(f'port(proxy): {self.proxy_port} - port(socks): {self.tor_socks_port} - port(control): {self.tor_control_port}, - port(dns): {self.tor_dns_port}')
        self.tor = TorRunner(self.tor_socks_port, self.tor_control_port, self.tor_dns_port)
        self.tor.bridge = CONFIG["bridge"]
        self.tor.bridges = CONFIG["bridges"]
        self.tor.app_window = self
        self.proxy = Runner(self.proxy_port, self.tor_socks_port,self)
        self.main_layout = QVBoxLayout(self)
        self.setLayout(self.main_layout)
        self.main_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.btn_status = QLabel(TAP_TO_CONNECT)
        self.set_btn_status_style("disconnected")
        self.main_layout.addWidget(self.btn_status)
        self.connect_btn = PulseButton("Connect")
        self.connect_btn.clicked.connect(self._toggle)
        self.main_layout.addWidget(self.connect_btn)

        lyt_info = QHBoxLayout()
        self.main_layout.addLayout(lyt_info)
        self.lbl_percent = QLabel("0%") 
        lyt_info.addWidget(self.lbl_percent)
        self.lbl_data_usage = QLabel(f"Data usage: {CONFIG['data_usage']/1024**2:.2f} Mb")
        lyt_info.addWidget(self.lbl_data_usage)
        
        self.data.valueChanged.connect(self.dataValueChanged)
        self.tor_status_signal.connect(self.dataValueChanged)
        self.tor_exit_signal.connect(self._tor_exited)
        self.btn_change_identity = QPushButton(CHANGE_IDENTITY)
        self.main_layout.addWidget(self.btn_change_identity)
        self.btn_change_identity.clicked.connect(self.change_identity_)
        self.logs_widget = LogWindow(self)
        self.tor_log_signal.connect(self.logs_widget.update_log)
        self.btn_log = QPushButton(LOGS)
        self.btn_log.clicked.connect(self.show_logs)
        self.main_layout.addWidget(self.btn_log)
        self.timer = QTimer(self)
        self.timer.setInterval(30000)
        self.timer.timeout.connect(self.change_identity_)
        self.stop_timer.connect(self.stop_timers)
        
        
        
        layout_ip = QVBoxLayout()
        layout_top_ip = QHBoxLayout()
        layout_ip.addLayout(layout_top_ip)
        self.tor_ip_label = QLabel()
        layout_top_ip.addWidget(self.tor_ip_label)

        self.btn_whatismyip = QPushButton(WHAT_IS_MY_IP)
        self.btn_whatismyip.setEnabled(False)
        layout_ip.addWidget(self.btn_whatismyip)
        self.btn_whatismyip.clicked.connect(self.whatismyip_clicked)
        self.main_layout.addLayout(layout_ip)
        self.thread_pool = QThreadPool()
        
        self.timer_data_usage = QTimer(self)
        self.timer_data_usage.setInterval(1000)
        self.timer_data_usage.timeout.connect(self.change_data_usage)

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
        if self.logs_widget.isHidden():
            self.logs_widget.setParent(self)
            self.logs_widget.move(10,10)
            self.logs_widget.show() 
        else:
            self.logs_widget.hide() 
            
       
    def change_identity_(self):
        worker = Worker(
            self.change_identity
        )
        self.thread_pool.start(worker)

    def change_identity(self):
        if not self.connected:
            logger.warning("change_tor_identity called but not connected to Tor.")
            return False

        try:
            
                self.controller.authenticate()
                self.controller.signal(TorSignal.NEWNYM)
                logger.info("Tor identity changed successfully (NEWNYM sent).")
                return True

        except SocketClosed:
            logger.error("Tor control socket is closed. Marking connection as disconnected.")
            self.connected = False
            return False

        except AuthenticationFailure:
            logger.critical("Authentication to Tor control port failed. Check password or cookie.")
            return False

        except OperationFailed:
            logger.warning("Tor NEWNYM signal was rejected. Possibly due to rate limit.")
            return False

        except Exception as e:
            logger.exception(f"Unexpected error while sending NEWNYM: {e}")
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
        self.btn_whatismyip.setEnabled(True)
        self._parent._parent.reload_engine()
        self.btn_status.setText("connected")
        self.set_btn_status_style("connected")
        self.timer.start()
        self.timer_data_usage.start()
        
        
    def set_btn_status_style(self, stmt):
        if stmt == "disconnected":
            color = "#e74c3c"
        elif stmt == "connected":
            color = "#2ecc71"
        else:
            color = "#f39c12"
        
        self.btn_status.setStyleSheet("""
            QLabel {
                padding: 20px;
                border-radius: 15px;
                font-size: 18px;
                font-weight: bold;
                border: 4px solid %s;
            }
            QLabel:hover {
                border: 4px solid #1B5E20;
            }
        """%(color))
        
    def _toggle(self):
        browser = self._parent._parent
        if self.running:
            browser._request_network_mode(False)
            return
        if not browser.tor_mode:
            browser._request_network_mode(True)
            return

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
        self.connect_btn.connected = False
        self.connect_btn.updateStyle()
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
            self.connect_btn.connected = False
            self.connect_btn.updateStyle()
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
        self.connect_btn.connected = False
        self.connect_btn.updateStyle()
        self.connect_btn.setEnabled(True)
        self._stopping = False
        
