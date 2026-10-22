"""Loopback-only HTTP proxy with explicit, fail-closed Tor routing."""

import ipaddress
import json
import logging
import os
import queue
import re
import select
import socket
import threading
import tempfile
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from urllib.parse import urlsplit

import socks

from proxy.config import CONFIG
from proxy.utils import resource_path

logger = logging.getLogger(__name__)

BLOCKED_FILE = "blocked_hosts.json"
EXCLUDE_FILE = "exclude_hosts.json"
CONNECT_TIMEOUT = 10
CLIENT_TIMEOUT = 30
TUNNEL_IDLE_TIMEOUT = 120
MAX_REQUEST_BODY = 512 * 1024 * 1024

blocked_hosts = []
exclude_hosts = []
queue_bytes = queue.Queue()
PROXY_INTO_TOR = False
_state_lock = threading.RLock()
_HOST_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$", re.IGNORECASE)


class InvalidHost(ValueError):
    pass


class BlockedHost(PermissionError):
    pass


def normalize_host(host):
    """Return a canonical DNS name or IP address; reject malformed authorities."""
    if not isinstance(host, str):
        raise InvalidHost("host must be text")
    host = host.strip()
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    if not host or any(ord(char) < 33 or ord(char) == 127 for char in host):
        raise InvalidHost("host is empty or contains whitespace/control characters")
    if "%" in host:
        raise InvalidHost("scoped IP addresses are not supported")
    if host.endswith("."):
        host = host[:-1]
    if not host:
        raise InvalidHost("host is empty")
    if host.endswith("."):
        raise InvalidHost("host has multiple trailing dots")
    try:
        address = ipaddress.ip_address(host)
        if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
            return address.ipv4_mapped.compressed.lower()
        return address.compressed.lower()
    except ValueError:
        pass
    if ":" in host:
        raise InvalidHost("invalid IP address")
    try:
        ascii_host = host.encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise InvalidHost("invalid internationalized domain name") from exc
    if re.fullmatch(r"[0-9.]+", ascii_host):
        raise InvalidHost("ambiguous numeric IP address")
    if len(ascii_host) > 253 or any(not _HOST_LABEL.fullmatch(label) for label in ascii_host.split(".")):
        raise InvalidHost("invalid domain name")
    return ascii_host


def normalize_host_rule(value):
    """Canonicalize plain and legacy wildcard rules without suffix ambiguity."""
    if not isinstance(value, str):
        raise InvalidHost("host rule must be text")
    rule = value.strip()
    if rule.startswith("*"):
        rule = rule[1:]
        if rule.startswith("."):
            rule = rule[1:]
    return normalize_host(rule)


def _matches_rule(host, rules):
    for rule in rules:
        try:
            canonical = normalize_host_rule(rule)
        except InvalidHost:
            continue
        if host == canonical or host.endswith("." + canonical):
            return True
    return False


def _load_rules(filename):
    path = resource_path(filename)
    try:
        with open(path, "r", encoding="utf-8") as stream:
            raw = json.load(stream)
        if not isinstance(raw, list):
            raise ValueError("host rules must be a JSON array")
        rules = []
        for entry in raw:
            try:
                normalized = normalize_host_rule(entry)
            except InvalidHost:
                logger.warning("Ignoring malformed host rule in %s", filename)
                continue
            canonical = "*." + normalized if isinstance(entry, str) and entry.strip().startswith("*") else normalized
            if canonical not in rules:
                rules.append(canonical)
        return rules
    except FileNotFoundError:
        return []
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        logger.warning("Could not load %s (%s); using an empty list", filename, type(exc).__name__)
        return []


def _atomic_json_write(filename, value):
    path = resource_path(filename)
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=directory,
            prefix=".host-rules-", suffix=".tmp", delete=False
        ) as stream:
            temp_path = stream.name
            json.dump(value, stream, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


def load_blocked():
    global blocked_hosts
    with _state_lock:
        blocked_hosts = _load_rules(BLOCKED_FILE)


def add_to_blocked_hosts(host):
    try:
        normalized = normalize_host_rule(host)
    except InvalidHost:
        return False
    canonical = "*." + normalized if isinstance(host, str) and host.strip().startswith("*") else normalized
    with _state_lock:
        if canonical in blocked_hosts:
            return False
        blocked_hosts.append(canonical)
        return True


def get_blocked():
    with _state_lock:
        return list(blocked_hosts)


def remove_blocked(host):
    with _state_lock:
        if host in blocked_hosts:
            blocked_hosts.remove(host)


def save_blocked():
    with _state_lock:
        _atomic_json_write(BLOCKED_FILE, list(blocked_hosts))


def load_exclude():
    global exclude_hosts
    with _state_lock:
        exclude_hosts = _load_rules(EXCLUDE_FILE)


def add_to_exclude_hosts(host):
    try:
        normalized = normalize_host_rule(host)
    except InvalidHost:
        return False
    canonical = "*." + normalized if isinstance(host, str) and host.strip().startswith("*") else normalized
    with _state_lock:
        if canonical in exclude_hosts:
            return False
        exclude_hosts.append(canonical)
        return True


def get_exclude():
    with _state_lock:
        return list(exclude_hosts)


def remove_exclude(host):
    with _state_lock:
        if host in exclude_hosts:
            exclude_hosts.remove(host)


def save_exclude():
    with _state_lock:
        _atomic_json_write(EXCLUDE_FILE, list(exclude_hosts))


def save_all():
    save_exclude()
    save_blocked()


def set_tor_routing(enabled):
    global PROXY_INTO_TOR
    with _state_lock:
        PROXY_INTO_TOR = bool(enabled)


def route_uses_tor(host):
    """Return the routing decision; blocked rules always take precedence."""
    canonical = normalize_host(host)
    with _state_lock:
        if _matches_rule(canonical, blocked_hosts):
            raise BlockedHost("destination is blocked")
        if not PROXY_INTO_TOR:
            return False
        return not _matches_rule(canonical, exclude_hosts)


def worker_data_usage_tracker(stop_event, flush_interval=3.0):
    """Aggregate packet counters and save one configuration snapshot per interval."""
    pending = 0
    last_flush = time.monotonic()
    while True:
        if stop_event.is_set():
            while True:
                try:
                    pending += queue_bytes.get_nowait()
                except queue.Empty:
                    break
            break
        try:
            pending += queue_bytes.get(timeout=0.2)
        except queue.Empty:
            pass
        now = time.monotonic()
        if pending and now - last_flush >= flush_interval:
            try:
                CONFIG.add_data_usage(pending)
            except Exception as exc:
                logger.warning("Could not persist proxy traffic counter (%s)", type(exc).__name__)
            pending = 0
            last_flush = now
    if pending:
        try:
            CONFIG.add_data_usage(pending)
        except Exception as exc:
            logger.warning("Could not persist proxy traffic counter (%s)", type(exc).__name__)


def get_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as stream:
        stream.bind(("127.0.0.1", 0))
        return stream.getsockname()[1]


def is_port_free(host: str, port: int, timeout: float = 0.15) -> bool:
    # Validate before name resolution or socket creation. In particular, avoid
    # int() coercion here: it accepts booleans, numeric strings, and floats.
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        return False
    try:
        if not isinstance(host, str) or not host or host != host.strip():
            return False
        host = normalize_host(host)
        results = socket.getaddrinfo(host, port, socket.AF_UNSPEC, socket.SOCK_STREAM)
        if not results:
            return False
        for af, socktype, proto, _canonname, address in results:
            with socket.socket(af, socktype, proto) as stream:
                stream.bind(address)
        return True
    except (OSError, ValueError, TypeError):
        return False


def _parse_authority(authority, default_port=None, require_port=False):
    if not authority or any(char in authority for char in "\r\n\t /\\?#"):
        raise InvalidHost("malformed host authority")
    try:
        parsed = urlsplit("//" + authority)
        if parsed.username is not None or parsed.password is not None or not parsed.hostname:
            raise InvalidHost("malformed host authority")
        host = normalize_host(parsed.hostname)
        port = parsed.port
    except (ValueError, UnicodeError) as exc:
        raise InvalidHost("malformed host authority") from exc
    if port is None:
        if require_port or default_port is None:
            raise InvalidHost("port is required")
        port = default_port
    if not 1 <= port <= 65535:
        raise InvalidHost("port is outside the valid range")
    return host, port


def _format_host_header(host, port, default_port=80):
    authority_host = f"[{host}]" if ":" in host else host
    return authority_host if port == default_port else f"{authority_host}:{port}"


class ProxyHandler(BaseHTTPRequestHandler):
    app_window = None
    server_version = "LocalProxy"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    def setup(self):
        super().setup()
        self.connection.settimeout(CLIENT_TIMEOUT)

    def _send_client_error(self, code, message):
        self.close_connection = True
        try:
            self.send_error(code, message)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass

    def _connect_upstream(self, host, port, use_tor):
        remote = socks.socksocket()
        remote.settimeout(CONNECT_TIMEOUT)
        if use_tor:
            remote.set_proxy(socks.SOCKS5, "127.0.0.1", self.server.tor_socks_port, rdns=True)
        remote.connect((host, port))
        remote.settimeout(CLIENT_TIMEOUT)
        return remote

    def do_CONNECT(self):
        self.close_connection = True
        remote = None
        replied = False
        try:
            host, port = _parse_authority(self.path, require_port=True)
            use_tor = route_uses_tor(host)
            remote = self._connect_upstream(host, port, use_tor)
            self.send_response(200, "Connection Established")
            self.end_headers()
            replied = True
            self._tunnel(self.connection, remote)
        except BlockedHost:
            self._send_client_error(403, "Forbidden")
        except InvalidHost:
            self._send_client_error(400, "Invalid CONNECT target")
        except (OSError, socks.ProxyError, socks.GeneralProxyError, socket.timeout):
            if not replied:
                self._send_client_error(502, "Upstream connection failed")
            logger.warning("CONNECT upstream failed (%s)", "Tor" if route_uses_tor_safe(self.path) else "direct")
        except Exception as exc:
            if not replied:
                self._send_client_error(502, "Upstream connection failed")
            logger.warning("CONNECT failed (%s)", type(exc).__name__)
        finally:
            if remote is not None:
                try:
                    remote.close()
                except OSError:
                    pass

    def do_GET(self):
        self._handle_http()

    def do_HEAD(self):
        self._handle_http()

    def do_POST(self):
        self._handle_http()

    def do_PUT(self):
        self._handle_http()

    def do_PATCH(self):
        self._handle_http()

    def do_DELETE(self):
        self._handle_http()

    def do_OPTIONS(self):
        self._handle_http()

    def _request_target(self):
        try:
            host_headers = self.headers.get_all("Host", [])
            if len(host_headers) > 1:
                raise InvalidHost("duplicate Host headers")
            parsed = urlsplit(self.path)
            if parsed.scheme:
                if parsed.scheme.lower() != "http" or not parsed.netloc:
                    raise InvalidHost("only absolute HTTP request targets are supported")
                if parsed.username is not None or parsed.password is not None:
                    raise InvalidHost("user information is not allowed in proxy targets")
                host = normalize_host(parsed.hostname)
                port = parsed.port
                if port is None:
                    port = 80
                target = parsed.path or "/"
                if parsed.query:
                    target += "?" + parsed.query
            else:
                host, port = _parse_authority(self.headers.get("Host", ""), default_port=80)
                if not self.path.startswith("/"):
                    raise InvalidHost("invalid origin-form request target")
                target = self.path
        except (ValueError, UnicodeError) as exc:
            raise InvalidHost("invalid HTTP request target") from exc
        if not 1 <= port <= 65535:
            raise InvalidHost("port is outside the valid range")
        if any(ord(char) < 32 or ord(char) == 127 for char in target):
            raise InvalidHost("invalid request path")
        return host, port, target

    def _handle_http(self):
        self.close_connection = True
        remote = None
        replied = False
        try:
            host, port, target = self._request_target()
            use_tor = route_uses_tor(host)

            transfer_encodings = self.headers.get_all("Transfer-Encoding", [])
            content_lengths = self.headers.get_all("Content-Length", [])
            if transfer_encodings and content_lengths:
                raise InvalidHost("ambiguous request body framing")
            if transfer_encodings and ",".join(transfer_encodings).strip().lower() != "chunked":
                self._send_client_error(501, "Unsupported request transfer encoding")
                return
            if len(content_lengths) > 1:
                raise InvalidHost("duplicate Content-Length headers")
            content_length = 0
            if content_lengths:
                raw_length = content_lengths[0].strip()
                if not raw_length.isascii() or not raw_length.isdecimal():
                    raise InvalidHost("invalid Content-Length")
                content_length = int(raw_length)
                if content_length > MAX_REQUEST_BODY:
                    self._send_client_error(413, "Request body too large")
                    return

            connection_tokens = set()
            for value in self.headers.get_all("Connection", []):
                connection_tokens.update(token.strip().lower() for token in value.split(",") if token.strip())
            hop_by_hop = {
                "connection", "keep-alive", "proxy-connection", "proxy-authorization",
                "proxy-authenticate", "te", "trailer", "transfer-encoding", "upgrade",
            }
            remote = self._connect_upstream(host, port, use_tor)
            headers = []
            for name, value in self.headers.items():
                lname = name.lower()
                if lname in hop_by_hop or lname in connection_tokens or lname in ("host", "content-length"):
                    continue
                headers.append(f"{name}: {value}\r\n")
            headers.append(f"Host: {_format_host_header(host, port)}\r\n")
            if transfer_encodings:
                headers.append("Transfer-Encoding: chunked\r\n")
            elif content_lengths:
                headers.append(f"Content-Length: {content_length}\r\n")
            headers.append("Connection: close\r\n")
            upstream_request = f"{self.command} {target} HTTP/1.1\r\n" + "".join(headers) + "\r\n"
            header_bytes = upstream_request.encode("latin-1", "strict")
            remote.sendall(header_bytes)
            queue_bytes.put(len(header_bytes))
            if transfer_encodings:
                self._copy_chunked_body(remote)
            else:
                self._copy_exact_body(remote, content_length)
            replied = True
            self._tunnel(remote, self.connection)
        except BlockedHost:
            self._send_client_error(403, "Forbidden")
        except InvalidHost:
            self._send_client_error(400, "Invalid HTTP request")
        except (OSError, socks.ProxyError, socks.GeneralProxyError, socket.timeout, UnicodeError):
            if not replied:
                self._send_client_error(502, "Upstream connection failed")
            logger.warning("HTTP upstream failed")
        except Exception as exc:
            if not replied:
                self._send_client_error(502, "Upstream connection failed")
            logger.warning("HTTP proxy request failed (%s)", type(exc).__name__)
        finally:
            if remote is not None:
                try:
                    remote.close()
                except OSError:
                    pass

    def _copy_exact_body(self, remote, remaining):
        while remaining:
            chunk = self.rfile.read(min(65536, remaining))
            if not chunk:
                raise ConnectionError("client closed before request body completed")
            remote.sendall(chunk)
            queue_bytes.put(len(chunk))
            remaining -= len(chunk)

    def _copy_chunked_body(self, remote):
        total = 0
        while True:
            line = self.rfile.readline(8192)
            if not line.endswith(b"\r\n"):
                raise InvalidHost("malformed chunked request")
            size_text = line[:-2].split(b";", 1)[0].strip()
            try:
                size = int(size_text, 16)
            except ValueError as exc:
                raise InvalidHost("malformed chunk size") from exc
            if not re.fullmatch(rb"[0-9A-Fa-f]+", size_text):
                raise InvalidHost("malformed chunk size")
            total += size
            if total > MAX_REQUEST_BODY:
                raise InvalidHost("request body too large")
            remote.sendall(line)
            queue_bytes.put(len(line))
            if size == 0:
                while True:
                    trailer = self.rfile.readline(8192)
                    if not trailer.endswith(b"\r\n"):
                        raise InvalidHost("malformed chunk trailer")
                    if trailer == b"\r\n":
                        remote.sendall(trailer)
                        queue_bytes.put(len(trailer))
                        return
                    field_name, separator, field_value = trailer[:-2].partition(b":")
                    if (not separator or not re.fullmatch(rb"[!#$%&'*+.^_`|~0-9A-Za-z-]+", field_name)
                            or any(byte < 32 and byte != 9 for byte in field_value)):
                        raise InvalidHost("malformed chunk trailer")
                    if field_name.lower() in {
                        b"host", b"content-length", b"transfer-encoding", b"authorization",
                        b"proxy-authorization", b"connection", b"trailer", b"te", b"upgrade",
                        b"proxy-connection",
                    }:
                        raise InvalidHost("forbidden chunk trailer")
                    remote.sendall(trailer)
                    queue_bytes.put(len(trailer))
            remaining = size
            while remaining:
                chunk = self.rfile.read(min(65536, remaining))
                if not chunk:
                    raise ConnectionError("client closed during chunked request")
                remote.sendall(chunk)
                queue_bytes.put(len(chunk))
                remaining -= len(chunk)
            ending = self.rfile.read(2)
            if ending != b"\r\n":
                raise InvalidHost("malformed chunk ending")
            remote.sendall(ending)
            queue_bytes.put(len(ending))

    def _tunnel(self, first, second):
        readable = {first, second}
        last_activity = time.monotonic()
        try:
            while readable:
                timeout = max(0, TUNNEL_IDLE_TIMEOUT - (time.monotonic() - last_activity))
                ready, _, _ = select.select(list(readable), [], [], timeout)
                if not ready:
                    break
                for source in ready:
                    data = source.recv(65536)
                    if not data:
                        readable.discard(source)
                        destination = second if source is first else first
                        try:
                            destination.shutdown(socket.SHUT_WR)
                        except OSError:
                            pass
                        continue
                    last_activity = time.monotonic()
                    queue_bytes.put(len(data))
                    destination = second if source is first else first
                    destination.sendall(data)
        except (OSError, ValueError):
            pass
        finally:
            for stream in (first, second):
                try:
                    stream.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                try:
                    stream.close()
                except OSError:
                    pass

    def log_message(self, format, *args):
        # BaseHTTPRequestHandler includes full URLs in its default access log.
        logger.debug("proxy client request handled")


def route_uses_tor_safe(authority):
    try:
        host, _port = _parse_authority(authority, default_port=443)
        return route_uses_tor(host)
    except (InvalidHost, BlockedHost):
        return False


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    allow_reuse_address = True
    daemon_threads = True
    block_on_close = False
    request_queue_size = 128

    def __init__(self, addr, handler, tor_socks_port):
        try:
            bind_address = ipaddress.ip_address(addr[0])
        except (ValueError, TypeError) as exc:
            raise ValueError("The local proxy must bind to a numeric loopback address") from exc
        if not bind_address.is_loopback:
            raise ValueError("The local proxy must bind to a loopback address")
        tor_socks_port = int(tor_socks_port)
        if not 1 <= tor_socks_port <= 65535:
            raise ValueError("Tor SOCKS port is outside the valid range")
        super().__init__(addr, handler)
        self.tor_socks_port = tor_socks_port
