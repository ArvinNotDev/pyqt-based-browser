"""Download and validate Tor expert bundles from the Tor Project distribution."""

import glob
import hashlib
import logging
import os
import re
import shutil
import tempfile
import threading
import time
import weakref
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

from proxy.config import (
    ARCHITECTURE,
    BUNDLE_DIR,
    CHECKSUM_FILE,
    MACHINE,
    OS_NAME,
    TOR_BUNDLE_BASE_URL,
)
from proxy.utils import resource_path

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = (3, 8)
MAX_BUNDLE_BYTES = 512 * 1024 * 1024
MAX_DOWNLOAD_SECONDS = 600
_VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+-]{0,63}$")
_BUNDLE_RE = re.compile(
    r"^tor-expert-bundle-(windows|linux)-(x86_64|i686)-([A-Za-z0-9][A-Za-z0-9.+-]{0,63})\.tar\.gz$"
)
_CHECKSUM_FILES = ("sha256sums-signed-build.txt", CHECKSUM_FILE, "sha256sums-unsigned-build.txt")


class DownloadCancelledError(InterruptedError):
    """Raised when a Tor bundle operation is cancelled during application shutdown."""


class CancellationToken:
    """Cooperative cancellation token that closes any HTTP responses in flight."""

    def __init__(self):
        self._event = threading.Event()
        self._lock = threading.RLock()
        self._responses = weakref.WeakSet()

    def is_set(self) -> bool:
        return self._event.is_set()

    def check(self) -> None:
        if self.is_set():
            raise DownloadCancelledError("Tor bundle operation was cancelled.")

    def register_response(self, response) -> None:
        with self._lock:
            already_cancelled = self._event.is_set()
            if not already_cancelled:
                self._responses.add(response)
        if already_cancelled:
            try:
                response.close()
            finally:
                raise DownloadCancelledError("Tor bundle operation was cancelled.")

    def set(self) -> None:
        self._event.set()
        with self._lock:
            responses = tuple(self._responses)
        for response in responses:
            try:
                response.close()
            except Exception:
                logger.debug("Could not close a cancelled Tor bundle response.", exc_info=True)


def _check_cancelled(cancel_event=None) -> None:
    if cancel_event is None:
        return
    check = getattr(cancel_event, "check", None)
    if callable(check):
        check()
        return
    is_set = getattr(cancel_event, "is_set", None)
    if callable(is_set) and is_set():
        raise DownloadCancelledError("Tor bundle operation was cancelled.")


def bundle_path(filename):
    name = os.path.basename(os.fspath(filename))
    if name != os.fspath(filename) and not os.path.isabs(os.fspath(filename)):
        raise ValueError("Bundle path must be a filename")
    if not name or name in (".", ".."):
        raise ValueError("Invalid bundle filename")
    root = os.path.realpath(resource_path(BUNDLE_DIR))
    candidate = os.path.realpath(os.fspath(filename)) if os.path.isabs(os.fspath(filename)) else os.path.realpath(os.path.join(root, name))
    if os.path.commonpath((root, candidate)) != root:
        raise ValueError("Bundle path escapes the bundle directory")
    return candidate


def create_bundle_dir():
    os.makedirs(resource_path(BUNDLE_DIR), exist_ok=True)


def _validate_version(version):
    version = str(version).strip().strip("/")
    if not _VERSION_RE.fullmatch(version) or ".." in version:
        raise ValueError("Invalid Tor bundle version")
    return version


def _official_base(base_url):
    parts = urlsplit(base_url)
    if (
        parts.scheme.lower() != "https"
        or parts.hostname != "dist.torproject.org"
        or parts.port not in (None, 443)
        or parts.username is not None
        or parts.password is not None
        or parts.query
        or parts.fragment
    ):
        raise ValueError("Tor bundle sources must use the official Tor Project HTTPS host")
    return base_url.rstrip("/") + "/"


def _get_response(url, *, stream=False, cancel_event=None, timeout=REQUEST_TIMEOUT):
    _check_cancelled(cancel_event)
    response = requests.get(url, stream=stream, timeout=timeout)
    try:
        register = getattr(cancel_event, "register_response", None)
        if callable(register):
            register(response)
        else:
            _check_cancelled(cancel_event)
        response.raise_for_status()
        final = urlsplit(response.url)
        if (
            final.scheme.lower() != "https"
            or final.hostname != "dist.torproject.org"
            or final.port not in (None, 443)
            or final.username is not None
            or final.password is not None
        ):
            raise ValueError("Tor bundle request redirected away from the official host")
        return response
    except Exception:
        response.close()
        raise


def _read_response_text(response, cancel_event=None, *, max_bytes=16 * 1024 * 1024):
    """Read small directory/checksum responses in chunks so cancellation is observed."""
    chunks = []
    received = 0
    for chunk in response.iter_content(chunk_size=16 * 1024):
        _check_cancelled(cancel_event)
        if not chunk:
            continue
        received += len(chunk)
        if received > max_bytes:
            raise ValueError("Tor bundle metadata response exceeds the configured size limit")
        chunks.append(chunk)
    _check_cancelled(cancel_event)
    return b"".join(chunks).decode(response.encoding or "utf-8", errors="replace")


def get_tor_versions(url=TOR_BUNDLE_BASE_URL, *, cancel_event=None):
    versions = []
    try:
        _check_cancelled(cancel_event)
        url = _official_base(url)
        with _get_response(url, stream=True, cancel_event=cancel_event) as response:
            soup = BeautifulSoup(_read_response_text(response, cancel_event), "html.parser")
        for link in soup.find_all("a"):
            _check_cancelled(cancel_event)
            candidate = link.get("href", "").strip("/")
            if candidate and _VERSION_RE.fullmatch(candidate) and ".." not in candidate:
                versions.append(candidate)
    except (requests.RequestException, ValueError) as exc:
        logger.warning("Could not retrieve Tor bundle versions (%s)", type(exc).__name__)
    return sorted(set(versions), reverse=True)


def _supported_bundle_name(name):
    match = _BUNDLE_RE.fullmatch(os.path.basename(name))
    if not match:
        return False
    bundle_os, bundle_arch, _version = match.groups()
    expected_os = {"Windows": "windows", "Linux": "linux"}.get(OS_NAME)
    if bundle_os != expected_os:
        return False
    machine = MACHINE.lower()
    if bundle_arch == "x86_64":
        return ARCHITECTURE == 64 and machine in ("x86_64", "amd64", "x64")
    return ARCHITECTURE == 32 and machine in ("i386", "i486", "i586", "i686", "x86")


def get_bundle_links(version, base_url=TOR_BUNDLE_BASE_URL, *, cancel_event=None):
    links = []
    try:
        _check_cancelled(cancel_event)
        version = _validate_version(version)
        base_url = _official_base(base_url)
        with _get_response(
            urljoin(base_url, version + "/"), stream=True, cancel_event=cancel_event
        ) as response:
            soup = BeautifulSoup(_read_response_text(response, cancel_event), "html.parser")
        for link in soup.find_all("a"):
            _check_cancelled(cancel_event)
            name = os.path.basename(link.get("href", ""))
            if _supported_bundle_name(name):
                links.append(name)
    except (requests.RequestException, ValueError) as exc:
        logger.warning("Could not retrieve Tor bundle links (%s)", type(exc).__name__)
    return sorted(set(links))


def sha256_file(filename, *, cancel_event=None):
    digest = hashlib.sha256()
    with open(filename, "rb") as stream:
        while True:
            _check_cancelled(cancel_event)
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    _check_cancelled(cancel_event)
    return digest.hexdigest()


def _checksum_cache_path(version):
    return resource_path(os.path.join(BUNDLE_DIR, f"{version}-{CHECKSUM_FILE}"))


def _extract_expected_hash(text, filename):
    for line in text.splitlines():
        match = re.match(r"^\s*([0-9a-fA-F]{64})\s+\*?(.+?)\s*$", line)
        if not match:
            continue
        digest, listed_name = match.groups()
        listed_name = listed_name.removeprefix("./").replace("\\", "/")
        if listed_name == filename or listed_name.endswith("/" + filename):
            return digest.lower()
    return None


def _fetch_checksum(version, base_url=TOR_BUNDLE_BASE_URL, filename=None, *, cancel_event=None):
    version = _validate_version(version)
    base_url = _official_base(base_url)
    last_error = None
    for checksum_file in _CHECKSUM_FILES:
        _check_cancelled(cancel_event)
        url = urljoin(base_url, f"{version}/{checksum_file}")
        try:
            with _get_response(url, stream=True, cancel_event=cancel_event) as response:
                text = _read_response_text(response, cancel_event)
            if text.strip() and (filename is None or _extract_expected_hash(text, filename) is not None):
                return text
        except requests.RequestException as exc:
            last_error = exc
    _check_cancelled(cancel_event)
    if last_error:
        raise ValueError("Tor Project checksum file is unavailable") from last_error
    raise ValueError("Tor Project checksum file is empty")


def _save_checksum(text, version):
    create_bundle_dir()
    path = _checksum_cache_path(version)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=os.path.dirname(path),
            prefix=".checksum-", suffix=".tmp", delete=False
        ) as stream:
            temp_path = stream.name
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


def get_checksum(version, base_url=TOR_BUNDLE_BASE_URL):
    text = _fetch_checksum(version, base_url)
    _save_checksum(text, _validate_version(version))
    return text


def get_version_by_bundle(filename, with_slash=False):
    name = os.path.basename(os.fspath(filename))
    match = _BUNDLE_RE.fullmatch(name)
    if not match:
        raise ValueError("Invalid Tor expert bundle filename")
    version = match.group(3)
    return version + "/" if with_slash else version


def check_hash(filename, base_url=TOR_BUNDLE_BASE_URL, go_online=False, *, cancel_event=None):
    try:
        _check_cancelled(cancel_event)
        path = bundle_path(filename)
        name = os.path.basename(path)
        version = get_version_by_bundle(name)
        if not os.path.isfile(path):
            return False
        if go_online:
            checksum_text = _fetch_checksum(version, base_url, name, cancel_event=cancel_event)
        else:
            cache_path = _checksum_cache_path(version)
            if not os.path.isfile(cache_path):
                return False
            with open(cache_path, "r", encoding="utf-8") as stream:
                checksum_text = stream.read()
        expected = _extract_expected_hash(checksum_text, name)
        return expected is not None and sha256_file(path, cancel_event=cancel_event) == expected
    except DownloadCancelledError:
        raise
    except (OSError, ValueError, requests.RequestException) as exc:
        logger.warning("Tor bundle checksum verification failed (%s)", type(exc).__name__)
        return False


def download_file(filename, version, base_url=TOR_BUNDLE_BASE_URL, *, cancel_event=None):
    _check_cancelled(cancel_event)
    create_bundle_dir()
    name = os.path.basename(os.fspath(filename))
    if name != os.fspath(filename) or not _BUNDLE_RE.fullmatch(name):
        raise ValueError("Invalid Tor expert bundle filename")
    version = _validate_version(version)
    if get_version_by_bundle(name) != version:
        raise ValueError("Bundle filename and version do not match")
    base_url = _official_base(base_url)
    path = bundle_path(name)

    if os.path.exists(path):
        if check_hash(path, base_url=base_url, go_online=True, cancel_event=cancel_event):
            _check_cancelled(cancel_event)
            return path
        raise ValueError("Existing Tor bundle failed checksum verification; it was left untouched")

    checksum_text = _fetch_checksum(version, base_url, name, cancel_event=cancel_event)
    _check_cancelled(cancel_event)
    expected = _extract_expected_hash(checksum_text, name)
    if expected is None:
        raise ValueError("Tor Project checksum does not contain this bundle")

    url = urljoin(base_url, f"{version}/{name}")
    temp_path = None
    started_at = time.monotonic()
    try:
        with tempfile.NamedTemporaryFile(
            "wb", dir=os.path.dirname(path), prefix=".tor-download-", suffix=".tmp", delete=False
        ) as stream:
            temp_path = stream.name
            with _get_response(url, stream=True, cancel_event=cancel_event, timeout=(5, 10)) as response:
                content_length = response.headers.get("Content-Length")
                if content_length and int(content_length) > MAX_BUNDLE_BYTES:
                    raise ValueError("Tor bundle exceeds the configured size limit")
                received = 0
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    _check_cancelled(cancel_event)
                    if time.monotonic() - started_at > MAX_DOWNLOAD_SECONDS:
                        raise TimeoutError("Tor bundle download exceeded its time limit")
                    if not chunk:
                        continue
                    received += len(chunk)
                    if received > MAX_BUNDLE_BYTES:
                        raise ValueError("Tor bundle exceeds the configured size limit")
                    stream.write(chunk)
            _check_cancelled(cancel_event)
            stream.flush()
            os.fsync(stream.fileno())
        if sha256_file(temp_path, cancel_event=cancel_event) != expected:
            raise ValueError("Downloaded Tor bundle checksum does not match Tor Project data")
        _check_cancelled(cancel_event)
        os.replace(temp_path, path)
        temp_path = None
        _check_cancelled(cancel_event)
        _save_checksum(checksum_text, version)
        logger.info("Downloaded and checksum-verified Tor bundle %s", name)
        return path
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


def list_downloaded_bundles():
    return sorted(glob.glob(os.path.join(resource_path(BUNDLE_DIR), "tor-expert-bundle-*.tar.gz")))


def check_bundle_compatibility(filename):
    name = os.path.basename(os.fspath(filename))
    # Extracted bundles are directories whose names omit the archive suffix.
    if not name.endswith(".tar.gz"):
        name += ".tar.gz"
    return _supported_bundle_name(name)


def get_own_bundles():
    pattern = os.path.join(resource_path(BUNDLE_DIR), "tor-expert-bundle-*")
    return sorted(path for path in glob.glob(pattern) if os.path.isdir(path) and check_bundle_compatibility(path))


def delete_bundle(name):
    bundle_name = os.path.basename(os.fspath(name)).removesuffix(".tar.gz")
    if not bundle_name.startswith("tor-expert-bundle-") or any(sep in bundle_name for sep in ("/", "\\")):
        raise ValueError("Invalid Tor bundle name")
    root = os.path.abspath(resource_path(BUNDLE_DIR))
    directory = os.path.abspath(os.path.join(root, bundle_name))
    archive = os.path.abspath(os.path.join(root, bundle_name + ".tar.gz"))
    if os.path.commonpath((root, directory)) != root or os.path.commonpath((root, archive)) != root:
        raise ValueError("Tor bundle path escapes the bundle directory")
    if os.path.isdir(directory):
        shutil.rmtree(directory)
    if os.path.isfile(archive):
        os.remove(archive)
