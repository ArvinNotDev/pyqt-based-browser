import os
import json
from proxy.set_proxy import get_os_name, Os
import platform
import tempfile
import threading
import logging

from proxy.utils import resource_path

logger = logging.getLogger(__name__)

IS_WINDOWS = get_os_name() == Os.Windows
IS_LINUX = get_os_name() == Os.Linux
IS_OTHER = not IS_WINDOWS and not IS_LINUX
OS_NAME = get_os_name()
MACHINE = platform.machine().lower()
if MACHINE in ("x86_64", "amd64", "x64"):
    ARCHITECTURE = 64
elif MACHINE in ("i386", "i486", "i586", "i686", "x86"):
    ARCHITECTURE = 32
else:
    ARCHITECTURE = int(platform.architecture()[0][0:2])
BUNDLE_DIR = "bundles/"
CHECKSUM_FILE = "sha256sums.txt"
TOR_BUNDLE_BASE_URL = "https://dist.torproject.org/torbrowser/"
class Config:
    file_config = "config.json"
    default_data = {"bridges": "", "bridge":False, "mode": "dark", "tor_port": None, "tor_port_checked": None,
                    "proxy_port": None, "proxy_port_checked": None, "control_port": None, "control_port_checked": None,
                    "dns_port": None, "dns_port_checked": None, "tor_path": None, "data_usage": 0,
                    "MaxCircuitDirtiness": 300, "newnym_interval": 30000}
    data = default_data.copy()

    def __init__(self):
        self._lock = threading.RLock()
        self.data = self.default_data.copy()
    
    def __getitem__(self, name):
        with self._lock:
            if name in self.data:
                return self.data[name]
            return self.default_data.get(name)
    
    def __setitem__(self, name, value):
        with self._lock:
            self.data[name] = value
            self.save()
        
    def __getattr__(self, name):
        if name in ["bridges", "bridge", "mode"]:
            return self[name]
        raise AttributeError(name)
    
    def __setattr__(self, name, value):
        if name in ["bridges", "bridge", "mode"]:
            self[name] = value
            return
        super().__setattr__(name, value)        
        
    @staticmethod
    def create_if_is_not_exits(fun):
        def inner_function(*args, **kwargs):
            file_path = resource_path(Config.file_config)
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            return fun(*args, **kwargs)
        return inner_function    
    
    def save_config(self, data):
        path = resource_path(Config.file_config)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", dir=os.path.dirname(path),
                prefix=".config-", suffix=".tmp", delete=False
            ) as file:
                temp_path = file.name
                file.write(data)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temp_path, path)
        finally:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)

    @create_if_is_not_exits
    def get_config(self):
        with open(resource_path(Config.file_config), "r") as file:
            return file.read()
    
    def json_format(self, data):
        try:
            parsed = json.loads(data)
            if not isinstance(parsed, dict):
                raise ValueError("configuration root must be an object")
            result = self.default_data.copy()
            result.update(parsed)
            if not isinstance(result.get("bridges"), str):
                result["bridges"] = ""
            if not isinstance(result.get("bridge"), bool):
                result["bridge"] = False
            if result.get("mode") not in ("dark", "light"):
                result["mode"] = "dark"
            if not isinstance(result.get("tor_path"), (str, type(None))):
                result["tor_path"] = None
            for key in ("tor_port", "proxy_port", "control_port", "dns_port"):
                value = result.get(key)
                try:
                    value = int(value) if value is not None and not isinstance(value, bool) else None
                except (TypeError, ValueError, OverflowError):
                    value = None
                result[key] = value if value is not None and 1 <= value <= 65535 else None
            for key in ("tor_port_checked", "proxy_port_checked", "control_port_checked", "dns_port_checked"):
                if not isinstance(result.get(key), bool):
                    result[key] = False
            try:
                usage = int(result.get("data_usage", 0))
                result["data_usage"] = max(0, usage)
            except (TypeError, ValueError, OverflowError):
                result["data_usage"] = 0
            try:
                dirtiness = int(result.get("MaxCircuitDirtiness", 300))
                result["MaxCircuitDirtiness"] = min(max(dirtiness, 1), 86400)
            except (TypeError, ValueError, OverflowError):
                result["MaxCircuitDirtiness"] = 300
            try:
                interval = int(result.get("newnym_interval", 30000))
                result["newnym_interval"] = min(max(interval, 1000), 2_147_483_647)
            except (TypeError, ValueError, OverflowError):
                result["newnym_interval"] = 30000
            return result
        except (json.JSONDecodeError, TypeError, ValueError):
            logger.warning("Invalid proxy configuration; using defaults")
            return self.default_data.copy()

    def json_to_text(self, data):
        return json.dumps(data)
        
    
    def load(self):
        with self._lock:
            try:
                data = self.get_config()
                self.data = self.json_format(data)
            except OSError as exc:
                logger.warning("Could not read proxy configuration (%s); using defaults", type(exc).__name__)
                self.data = self.default_data.copy()
            return self.data.copy()

    def save(self):
        with self._lock:
            data = self.json_to_text(self.data)
            self.save_config(data)

    def add_data_usage(self, byte_count):
        """Add a batch of traffic bytes and persist one atomic snapshot."""
        with self._lock:
            self.data["data_usage"] = int(self.data.get("data_usage", 0) or 0) + int(byte_count)
            self.save()
            return self.data["data_usage"]

CONFIG = Config()
