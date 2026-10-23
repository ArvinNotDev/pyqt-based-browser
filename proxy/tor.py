"""Bounded Tor process and loopback proxy lifecycle management."""

import logging
import os
import re
import subprocess
import tarfile
import tempfile
import threading
import time
from pathlib import Path

from torproxy.paths import user_directories
from torproxy.tor_manager import TorManager, TorManagerError, TorSettings

from proxy.config import BUNDLE_DIR, CONFIG, IS_WINDOWS
from proxy.proxy import ProxyHandler, ThreadedHTTPServer, worker_data_usage_tracker
from proxy.updater import (
    check_bundle_compatibility,
    check_hash,
    get_own_bundles,
    list_downloaded_bundles,
)
from proxy.utils import extract_tar_gz_file, resource_path

logger = logging.getLogger(__name__)

PROCESS_STOP_TIMEOUT = 5
THREAD_STOP_TIMEOUT = 5
_BOOTSTRAP_RE = re.compile(r"Bootstrapped\s+(\d+)%", re.IGNORECASE)


class TorRunner:
    def __init__(self, socks_port, contorl_port, dns_port):
        self.proc = None
        self.thread = None
        self.log_file = str(user_directories("ARMA Browser Tor").logs / "tor.log")
        self.socks_port = int(socks_port)
        self.bridge = False
        self.bridges = ""
        self.contorl_port = int(contorl_port)
        self.dns_port = int(dns_port)
        self.ExcludeNodes = []
        self.ExitNodes = []
        self.StrictNodes = 0
        self.MaxCircuitDirtiness = 300
        self.NewCircuitPeriod = 30
        self.ClientUseIPv4 = 1
        self.ClientUseIPv6 = 0
        self.Log = "notice stdout"
        self.bridge_types = ["obfs4", "webtunnel", "meek", "snowflake", "scramblesuit", "fte"]
        self.tor_path = None
        self.lyrebird_path = None
        self.geoip_path = None
        self.geoip6_path = None
        self.path_set = False
        self.app_window = None
        self._state_lock = threading.RLock()
        self._stop_requested = False
        self._launch_error = None
        self._torrc_path = None
        self._lifecycle_generation = 0
        self.manager = None
        self.state = "STOPPED"
        self.last_error = None
        self._last_status_report = None

    def _bundle_archive(self, bundle_path):
        name = os.path.basename(os.path.normpath(bundle_path))
        return resource_path(os.path.join(BUNDLE_DIR, name + ".tar.gz"))

    def _verify_archive(self, archive, cancel_event=None):
        if cancel_event is not None and cancel_event.is_set():
            raise InterruptedError("Tor bundle verification was cancelled.")
        if check_hash(archive, go_online=False, cancel_event=cancel_event):
            return True
        if cancel_event is not None and cancel_event.is_set():
            raise InterruptedError("Tor bundle verification was cancelled.")
        return check_hash(archive, go_online=True, cancel_event=cancel_event)

    def update_path(self, base_path=None, token=None, cancel_event=None):
        candidates = [base_path] if base_path else get_own_bundles() + list_downloaded_bundles()
        bundle_root = os.path.realpath(resource_path(BUNDLE_DIR))
        for candidate in candidates:
            if cancel_event is not None and cancel_event.is_set():
                raise InterruptedError("Tor startup was cancelled.")
            if not candidate:
                continue
            candidate = os.path.abspath(os.fspath(candidate))
            if os.path.commonpath((bundle_root, os.path.realpath(candidate))) != bundle_root:
                continue
            is_archive = os.path.isfile(candidate) and candidate.endswith(".tar.gz")
            bundle_name = os.path.basename(candidate[:-7] if is_archive else os.path.normpath(candidate))
            if not check_bundle_compatibility(bundle_name + ".tar.gz"):
                continue
            archive = candidate if is_archive else self._bundle_archive(candidate)
            if not os.path.isfile(archive) or not self._verify_archive(archive, cancel_event=cancel_event):
                if cancel_event is not None and cancel_event.is_set():
                    raise InterruptedError("Tor startup was cancelled.")
                logger.warning("Skipping Tor bundle without a valid Tor Project checksum")
                continue
            bundle_dir = (
                resource_path(os.path.join(BUNDLE_DIR, bundle_name))
                if is_archive else candidate
            )
            if os.path.commonpath((bundle_root, os.path.realpath(bundle_dir))) != bundle_root:
                continue
            if is_archive and not os.path.isdir(bundle_dir):
                try:
                    extract_tar_gz_file(archive, bundle_dir, cancel_event=cancel_event)
                except (OSError, ValueError, tarfile.TarError) as exc:
                    logger.warning("Could not extract Tor bundle (%s)", type(exc).__name__)
                    continue
            tor_dir = os.path.join(bundle_dir, "tor")
            tor_binary = os.path.join(tor_dir, "tor.exe" if IS_WINDOWS else "tor")
            transport_binary = os.path.join(
                tor_dir, "pluggable_transports",
                "lyrebird.exe" if IS_WINDOWS else "lyrebird",
            )
            geoip = os.path.join(bundle_dir, "data", "geoip")
            geoip6 = os.path.join(bundle_dir, "data", "geoip6")
            if not os.path.isfile(tor_binary) or not os.path.isfile(geoip) or not os.path.isfile(geoip6):
                logger.warning("Tor bundle is missing required runtime files")
                continue
            with self._state_lock:
                if token is not None and token != self._lifecycle_generation:
                    return False
                self.tor_path = os.path.normpath(tor_binary)
                self.lyrebird_path = os.path.normpath(transport_binary)
                self.geoip_path = os.path.normpath(geoip)
                self.geoip6_path = os.path.normpath(geoip6)
                self.path_set = True
            return True

        with self._state_lock:
            if token is not None and token != self._lifecycle_generation:
                return False
            self.path_set = False
        logger.error("No checksum-verified compatible Tor bundle is available")
        return False

    @staticmethod
    def _valid_port(port):
        return isinstance(port, int) and 1 <= port <= 65535

    @staticmethod
    def _torrc_quote(value):
        value = str(value)
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError("Tor configuration paths cannot contain control characters")
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'

    def _make_manager(self):
        """Build a supervised Tor manager with validated ports and current bridge parsing."""
        if not self.path_set or not self.tor_path:
            raise TorManagerError(
                "No verified compatible Tor bundle is configured. Open Bundles to select one."
            )
        directories = user_directories("ARMA Browser Tor").ensure()
        try:
            max_circuit = int(self.MaxCircuitDirtiness or 600)
        except (TypeError, ValueError):
            max_circuit = 600
        try:
            new_circuit = int(self.NewCircuitPeriod or 60)
        except (TypeError, ValueError):
            new_circuit = 60
        max_circuit = min(86400, max(10, max_circuit))
        new_circuit = min(86400, max(10, new_circuit))
        return TorManager(TorSettings(
            executable=Path(self.tor_path),
            socks_port=int(self.socks_port),
            control_port=int(self.contorl_port),
            dns_port=int(self.dns_port) if self.dns_port is not None else None,
            data_directory=directories.data / "tor",
            geoip_path=Path(self.geoip_path) if self.geoip_path else None,
            geoip6_path=Path(self.geoip6_path) if self.geoip6_path else None,
            bridges_enabled=bool(self.bridge),
            bridges=str(self.bridges or ""),
            max_circuit_dirtiness_seconds=max_circuit,
            new_circuit_period_seconds=new_circuit,
            startup_timeout_seconds=180.0,
            shutdown_timeout_seconds=float(PROCESS_STOP_TIMEOUT),
            log_path=directories.logs / "tor.log",
            webtunnel_sni_imitation=str(CONFIG["webtunnel_sni_imitation"] or ""),
        ))

    def generate_torcc(self):
        """Render the same validated configuration that the supervisor will launch."""
        return self._make_manager().render_torrc()

    def _emit_log(self, message):
        signal = getattr(self.app_window, "tor_log_signal", None)
        if signal is not None:
            signal.emit(str(message))
        else:
            logger.info("Tor: %s", message)

    def _emit_status(self, value):
        signal = getattr(self.app_window, "tor_status_signal", None)
        if signal is not None:
            signal.emit(value if isinstance(value, str) else f"{int(value)}%")

    def _emit_exit(self, message):
        signal = getattr(self.app_window, "tor_exit_signal", None)
        if signal is not None:
            signal.emit(str(message))
        else:
            logger.error("Tor supervisor failed: %s", message)

    def begin_start(self):
        with self._state_lock:
            if self.thread and self.thread.is_alive():
                return None
            self._lifecycle_generation += 1
            self._stop_requested = False
            self._launch_error = None
            self.last_error = None
            return self._lifecycle_generation

    def start(self, token=None):
        with self._state_lock:
            if token is None:
                self._lifecycle_generation += 1
                token = self._lifecycle_generation
                self._stop_requested = False
            if token != self._lifecycle_generation or self._stop_requested:
                return False
            if self.thread and self.thread.is_alive():
                return False
            if not self.path_set:
                raise TorManagerError("No verified compatible Tor bundle is configured.")
            self.manager = None
            self.state = "STARTING"
            self._last_status_report = None
            self._launch_error = None
            self.last_error = None
            self.thread = threading.Thread(
                target=self._run, args=(token,), name="arma-tor-supervisor", daemon=True
            )
            self.thread.start()
            return True

    def _on_manager_status(self, token, state, progress, message):
        state_value = getattr(state, "value", str(state))
        normalized = str(state_value).upper().split(".")[-1]
        with self._state_lock:
            if token != self._lifecycle_generation or self._stop_requested:
                return
            self.state = normalized
            if normalized == "FAILED":
                self.last_error = str(message or "Tor startup failed")
            elif normalized == "READY":
                self.last_error = None
        detail = " ".join(str(message or "").split())
        report = (normalized, progress, detail)
        if report != self._last_status_report:
            self._last_status_report = report
            suffix = f" ({int(progress)}%)" if progress is not None else ""
            self._emit_log(f"Tor state: {normalized.lower()}{suffix}" + (f" — {detail}" if detail else ""))

        # Never tell the browser Tor is ready until ControlPort identity and the
        # SOCKS listener have been verified together by TorManager.
        if normalized == "READY" and progress is not None and int(progress) >= 100:
            self._emit_status("100%")
        elif progress is not None and int(progress) >= 100:
            self._emit_status("Verifying Tor listeners…")
        elif progress is not None:
            self._emit_status(min(99, max(0, int(progress))))
        elif normalized in {"STARTING", "BOOTSTRAPPING"}:
            self._emit_status("Starting Tor…")

    def _run(self, token):
        manager = None
        try:
            manager = self._make_manager()
            with self._state_lock:
                if token != self._lifecycle_generation or self._stop_requested:
                    return
                self.manager = manager
            manager.start(on_status=lambda state, progress, message:
                          self._on_manager_status(token, state, progress, message))
            with self._state_lock:
                if token != self._lifecycle_generation or self._stop_requested:
                    return
                self.state = "READY"
            self.proc = getattr(manager, "process", None)
            self._emit_status("100%")
            self._emit_log("Tor bootstrap verified; authenticated control and SOCKS listeners are ready.")

            # Retain a lightweight supervisor after bootstrap so an unexpected Tor
            # exit is surfaced immediately and the proxy can remain fail-closed.
            while True:
                with self._state_lock:
                    if token != self._lifecycle_generation or self._stop_requested:
                        break
                process = getattr(manager, "process", None)
                self.proc = process
                if process is not None and process.poll() is not None:
                    raise TorManagerError(
                        f"Tor exited unexpectedly (exit code {process.returncode}). "
                        "Traffic remains blocked by the local proxy until Tor is ready again."
                    )
                time.sleep(0.35)
        except Exception as exc:
            self._launch_error = exc
            self.last_error = str(exc)
            with self._state_lock:
                active = token == self._lifecycle_generation and not self._stop_requested
                if active:
                    self.state = "FAILED"
            if active:
                logger.warning("Tor supervisor failed: %s", type(exc).__name__, exc_info=True)
                self._emit_log(f"Tor startup/runtime failure: {exc}")
                self._emit_exit(str(exc))
        finally:
            if manager is not None:
                try:
                    manager.stop()
                except Exception:
                    logger.debug("Tor manager cleanup raised after stop/failure.", exc_info=True)
            with self._state_lock:
                if token == self._lifecycle_generation:
                    self.proc = None
                    if self._stop_requested:
                        self.state = "STOPPED"
                if self.manager is manager:
                    self.manager = None

    def _remove_torrc(self):
        """Compatibility shim; TorManager securely owns the torrc lifecycle."""
        return None

    def request_new_identity(self):
        manager = self.manager
        if manager is None or self.state != "READY":
            raise TorManagerError("Tor is not ready; identity changes are unavailable.")
        return manager.request_new_identity()

    def stop(self):
        with self._state_lock:
            self._lifecycle_generation += 1
            self._stop_requested = True
            manager = self.manager
            process = self.proc
            thread = self.thread
            self.state = "STOPPING"
        if manager is not None:
            try:
                manager.stop()
            except Exception as exc:
                logger.warning("TorManager shutdown raised (%s)", type(exc).__name__)
        if process is not None and process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=PROCESS_STOP_TIMEOUT)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    process.kill()
                    process.wait(timeout=2)
                except (OSError, subprocess.TimeoutExpired):
                    logger.error("Tor process did not terminate after force termination.")
        if thread and thread is not threading.current_thread():
            thread.join(timeout=THREAD_STOP_TIMEOUT)
            if thread.is_alive():
                logger.error("Tor supervisor did not stop within the timeout")
        self._remove_torrc()
        with self._state_lock:
            if self.thread is thread and (thread is None or not thread.is_alive()):
                self.thread = None
            if process is not None and process.poll() is not None and self.proc is process:
                self.proc = None
            self.state = "STOPPED"



class Runner:
    def __init__(self, port, tor_socks_port, app_window, host="127.0.0.1"):
        self.app_window = app_window
        self.host = host
        self.port = int(port)
        self.tor_socks_port = int(tor_socks_port)
        self.server = None
        self.thread = None
        self.data_usage_tracker = None
        self.stop_data_usage_tracker_event = None
        self.started = False
        self._stopping = False
        self._lock = threading.RLock()

    def start(self):
        with self._lock:
            if self.started or self._stopping:
                return False
            if self.host != "127.0.0.1":
                raise ValueError("The local proxy must bind to 127.0.0.1")
            server = ThreadedHTTPServer((self.host, self.port), ProxyHandler, self.tor_socks_port)
            server.timeout = 0.5
            ProxyHandler.app_window = self.app_window
            self.server = server
            serve_thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.25},
                                           name="local-proxy", daemon=True)
            stop_event = threading.Event()
            tracker = threading.Thread(target=worker_data_usage_tracker, args=(stop_event,),
                                       name="proxy-traffic-tracker", daemon=True)
            self.thread = serve_thread
            self.stop_data_usage_tracker_event = stop_event
            self.data_usage_tracker = tracker
            try:
                serve_thread.start()
                tracker.start()
                self.started = True
            except Exception:
                stop_event.set()
                if serve_thread.is_alive():
                    server.shutdown()
                    serve_thread.join(timeout=3)
                server.server_close()
                self.server = None
                self.thread = None
                self.stop_data_usage_tracker_event = None
                self.data_usage_tracker = None
                raise
            logger.info("Local proxy started on %s:%s", self.host, self.port)
            return True

    def stop(self):
        with self._lock:
            if not self.started:
                return False
            self.started = False
            self._stopping = True
            server = self.server
            serve_thread = self.thread
            tracker = self.data_usage_tracker
            stop_event = self.stop_data_usage_tracker_event
        try:
            if server is not None:
                server.shutdown()
                server.server_close()
            if serve_thread and serve_thread is not threading.current_thread():
                serve_thread.join(timeout=3)
                if serve_thread.is_alive():
                    logger.error("Local proxy server thread did not stop within the timeout")
        finally:
            if stop_event:
                stop_event.set()
            if tracker and tracker is not threading.current_thread():
                tracker.join(timeout=5)
                if tracker.is_alive():
                    logger.error("Proxy traffic tracker did not stop within the timeout")
            with self._lock:
                self.server = None
                self.thread = None
                self.data_usage_tracker = None
                self.stop_data_usage_tracker_event = None
                self._stopping = False
        logger.info("Local proxy stopped")
        return True
