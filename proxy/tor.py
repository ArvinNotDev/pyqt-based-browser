"""Bounded Tor process and loopback proxy lifecycle management."""

import logging
import os
import re
import subprocess
import tarfile
import tempfile
import threading

from proxy.config import BUNDLE_DIR, IS_WINDOWS
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
        self.log_file = resource_path("tor_log.txt")
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

    def _bundle_archive(self, bundle_path):
        name = os.path.basename(os.path.normpath(bundle_path))
        return resource_path(os.path.join(BUNDLE_DIR, name + ".tar.gz"))

    def _verify_archive(self, archive):
        if check_hash(archive, go_online=False):
            return True
        return check_hash(archive, go_online=True)

    def update_path(self, base_path=None, token=None):
        candidates = [base_path] if base_path else get_own_bundles() + list_downloaded_bundles()
        bundle_root = os.path.realpath(resource_path(BUNDLE_DIR))
        for candidate in candidates:
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
            if not os.path.isfile(archive) or not self._verify_archive(archive):
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
                    extract_tar_gz_file(archive, bundle_dir)
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

    def generate_torcc(self):
        ports = (self.socks_port, self.contorl_port, self.dns_port)
        if not all(self._valid_port(port) for port in ports) or len(set(ports)) != len(ports):
            raise ValueError("Tor ports must be distinct values between 1 and 65535")
        config = [
            f"SocksPort 127.0.0.1:{self.socks_port}",
            f"ControlPort 127.0.0.1:{self.contorl_port}",
            f"DNSPort 127.0.0.1:{self.dns_port}",
            f"GeoIPFile {self._torrc_quote(self.geoip_path)}",
            f"GeoIPv6File {self._torrc_quote(self.geoip6_path)}",
            f"Log {self.Log}",
            f"MaxCircuitDirtiness {int(self.MaxCircuitDirtiness)}",
            f"NewCircuitPeriod {int(self.NewCircuitPeriod)}",
            f"ExcludeNodes {','.join(self.ExcludeNodes)}",
            f"ExitNodes {','.join(self.ExitNodes)}",
            f"StrictNodes {int(bool(self.StrictNodes))}",
            f"ClientUseIPv4 {1 if self.ClientUseIPv4 else 0}",
            f"ClientUseIPv6 {1 if self.ClientUseIPv6 else 0}",
        ]
        if self.bridge and self.bridges:
            selected_type = next((kind for kind in self.bridge_types if kind in self.bridges), None)
            if selected_type:
                bridge_lines = []
                for raw in self.bridges.splitlines():
                    line = raw.strip()
                    if not line or line.startswith("#"):
                        continue
                    if any(ord(char) < 32 or ord(char) == 127 for char in line):
                        raise ValueError("Bridge configuration contains control characters")
                    if line.lower().startswith("bridge "):
                        line = line[7:].strip()
                    if not line.startswith(selected_type + " "):
                        raise ValueError("Bridge type does not match the selected transport")
                    bridge_lines.append("Bridge " + line)
                if bridge_lines:
                    if not os.path.isfile(self.lyrebird_path):
                        raise ValueError("Selected bridge transport is missing")
                    config.extend([
                        "UseBridges 1",
                        f"ClientTransportPlugin {selected_type} exec {self._torrc_quote(self.lyrebird_path)}",
                        *bridge_lines,
                    ])
        return "\n".join(config)

    def _emit_log(self, message):
        signal = getattr(self.app_window, "tor_log_signal", None)
        if signal is not None:
            signal.emit(message)
        else:
            logger.info("Tor: %s", message)

    def _emit_status(self, percent):
        signal = getattr(self.app_window, "tor_status_signal", None)
        if signal is not None:
            signal.emit(f"{percent}%")

    def _emit_exit(self, message):
        signal = getattr(self.app_window, "tor_exit_signal", None)
        if signal is not None:
            signal.emit(message)

    def begin_start(self):
        with self._state_lock:
            if self.thread and self.thread.is_alive():
                return None
            self._lifecycle_generation += 1
            self._stop_requested = False
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
                raise RuntimeError("No verified compatible Tor bundle is configured")
            self._launch_error = None
            self.thread = threading.Thread(target=self._run, args=(token,), name="tor-runner", daemon=True)
            self.thread.start()
            return True

    def _run(self, token):
        process = None
        try:
            torrc_content = self.generate_torcc()
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", prefix="pyqt-browser-tor-", suffix=".torrc", delete=False
            ) as torrc:
                self._torrc_path = torrc.name
                torrc.write(torrc_content)
                torrc.flush()
                os.fsync(torrc.fileno())

            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if IS_WINDOWS else 0
            with self._state_lock:
                if self._stop_requested or token != self._lifecycle_generation:
                    return
                process = subprocess.Popen(
                    [self.tor_path, "-f", self._torrc_path],
                    cwd=os.path.dirname(self.tor_path),
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    bufsize=1,
                    creationflags=flags,
                )
                self.proc = process
            unexpected_exit = None
            with open(self.log_file, "a", encoding="utf-8", errors="replace") as log:
                if process.stdout is not None:
                    for raw_line in iter(process.stdout.readline, b""):
                        line = raw_line.decode("utf-8", errors="replace").rstrip()
                        if not line:
                            continue
                        log.write(line + "\n")
                        log.flush()
                        self._emit_log(line)
                        match = _BOOTSTRAP_RE.search(line)
                        if match:
                            self._emit_status(min(100, int(match.group(1))))
                return_code = process.wait()
            with self._state_lock:
                if not self._stop_requested:
                    unexpected_exit = f"Tor exited with status {return_code}"
            if unexpected_exit:
                self._emit_exit(unexpected_exit)
        except Exception as exc:
            self._launch_error = exc
            logger.exception("Tor process failed (%s)", type(exc).__name__)
            with self._state_lock:
                unexpected = not self._stop_requested and token == self._lifecycle_generation
            if unexpected:
                self._emit_exit(f"Tor could not start ({type(exc).__name__})")
        finally:
            if process is not None:
                try:
                    if process.stdout:
                        process.stdout.close()
                except OSError:
                    pass
            with self._state_lock:
                if self.proc is process:
                    self.proc = None
            self._remove_torrc()

    def _remove_torrc(self):
        path, self._torrc_path = self._torrc_path, None
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except OSError as exc:
                logger.warning("Could not remove temporary Tor config (%s)", type(exc).__name__)

    def stop(self):
        with self._state_lock:
            self._lifecycle_generation += 1
            self._stop_requested = True
            process = self.proc
            thread = self.thread
        if process is not None and process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=PROCESS_STOP_TIMEOUT)
            except subprocess.TimeoutExpired:
                logger.warning("Tor did not stop in time; terminating it forcefully")
                try:
                    process.kill()
                    process.wait(timeout=2)
                except (OSError, subprocess.TimeoutExpired):
                    logger.error("Tor process did not terminate after kill request")
            except OSError as exc:
                logger.warning("Could not terminate Tor process (%s)", type(exc).__name__)
        if thread and thread is not threading.current_thread():
            thread.join(timeout=THREAD_STOP_TIMEOUT)
            if thread.is_alive():
                logger.error("Tor monitor thread did not stop within the timeout")
        self._remove_torrc()
        with self._state_lock:
            if self.thread is thread and (thread is None or not thread.is_alive()):
                self.thread = None
            if process is not None and process.poll() is not None and self.proc is process:
                self.proc = None


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
