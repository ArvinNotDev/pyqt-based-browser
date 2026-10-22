"""Helpers for resolving address-bar input without guessing from dots/spaces."""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import quote_plus, urlsplit, urlunsplit


class URLInputError(ValueError):
    """Raised when address-bar input is an unsupported or malformed URL."""


_SCHEME_RE = re.compile(r"^([A-Za-z][A-Za-z0-9+.-]*):")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


def _valid_host(host: str) -> bool:
    if not host:
        return False
    if re.fullmatch(r"\d+(?:\.\d+){3}", host):
        try:
            ipaddress.IPv4Address(host)
        except ValueError:
            return False
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        pass

    candidate = host.rstrip(".")
    if not candidate or len(candidate) > 253:
        return False
    try:
        ascii_host = candidate.encode("idna").decode("ascii")
    except UnicodeError:
        return False
    labels = ascii_host.split(".")
    return all(
        label
        and len(label) <= 63
        and re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?", label)
        for label in labels
    )


def _http_url(value: str, *, explicit: bool) -> str | None:
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        if explicit:
            raise URLInputError(f"Invalid URL: {exc}") from exc
        return None

    if parsed.scheme.lower() not in ("http", "https"):
        if explicit:
            raise URLInputError(f"Unsupported URL scheme: {parsed.scheme}")
        return None
    if parsed.username is not None or parsed.password is not None:
        if explicit:
            raise URLInputError("Credentials are not allowed in a web address.")
        return None
    if not parsed.netloc or not _valid_host(parsed.hostname or ""):
        if explicit:
            raise URLInputError("Enter a valid web address with a hostname.")
        return None
    if port is not None and not 1 <= port <= 65535:
        if explicit:
            raise URLInputError("The URL port must be between 1 and 65535.")
        return None

    return urlunsplit(
        (parsed.scheme.lower(), parsed.netloc, parsed.path, parsed.query, parsed.fragment)
    )


def _bare_web_address(value: str) -> str | None:
    # A raw IPv6 literal has no unambiguous port separator; accept it without a port.
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        ip = None
    if isinstance(ip, ipaddress.IPv6Address):
        return f"https://[{ip.compressed}]"

    try:
        parsed = urlsplit("//" + value)
        host = parsed.hostname or ""
        port = parsed.port
    except ValueError as exc:
        raise URLInputError(f"Invalid host or port: {exc}") from exc

    if not _valid_host(host):
        return None
    if port is not None and not 1 <= port <= 65535:
        raise URLInputError("The URL port must be between 1 and 65535.")

    # Dotted names, IP addresses, localhost, and explicit host:port inputs are
    # address-like. Other single words remain useful search queries.
    host_is_address_like = (
        "." in host
        or host.lower() == "localhost"
        or port is not None
        or isinstance(ip, (ipaddress.IPv4Address, ipaddress.IPv6Address))
    )
    if not host_is_address_like:
        return None
    return urlunsplit(("https", parsed.netloc, parsed.path, parsed.query, parsed.fragment))


def _search_url(query: str, search_engine: str) -> str:
    engine = _http_url(search_engine.strip(), explicit=True)
    if engine is None:
        raise URLInputError("The configured search engine must be an HTTP or HTTPS URL.")
    encoded_query = quote_plus(query, safe="")
    if "{query}" in engine:
        return engine.replace("{query}", encoded_query)
    parts = urlsplit(engine)
    if parts.query.endswith(("=", "&")):
        search_query = parts.query + encoded_query
    elif parts.query:
        search_query = parts.query + "&q=" + encoded_query
    else:
        search_query = "q=" + encoded_query
    return urlunsplit((parts.scheme, parts.netloc, parts.path, search_query, parts.fragment))


def resolve_address_input(value: str, search_engine: str) -> str:
    """Resolve address-bar input to a safe HTTP(S) URL or ``about:blank``.

    Unsupported explicit schemes raise :class:`URLInputError`; they are never
    silently sent to the configured search engine.
    """
    text = value.strip()
    if not text:
        raise URLInputError("Enter a web address or a search phrase.")
    if _CONTROL_RE.search(text):
        raise URLInputError("The address contains whitespace or control characters.")
    if text.lower() == "about:blank":
        return "about:blank"

    scheme_match = _SCHEME_RE.match(text)
    scheme = scheme_match.group(1).lower() if scheme_match else ""

    if text.lower().startswith(("http://", "https://")):
        normalized = _http_url(text, explicit=True)
        assert normalized is not None
        return normalized

    if "://" in text:
        raise URLInputError(f"Unsupported URL scheme: {scheme or text.split(':', 1)[0]}")

    if scheme_match:
        if scheme in {"javascript", "data", "file", "blob", "vbscript", "ftp", "mailto"}:
            raise URLInputError(f"Unsupported URL scheme: {scheme}")
        if scheme in {"http", "https"}:
            raise URLInputError(f"Malformed {scheme.upper()} URL; include // after the scheme.")
        host_port = re.split(r"[/\?#]", text[scheme_match.end():], maxsplit=1)[0]
        if host_port.isdecimal():
            pass
        elif any(character.isspace() for character in text[scheme_match.end():]):
            return _search_url(text, search_engine)
        else:
            raise URLInputError(f"Unsupported URL scheme: {scheme}")

    # Host:port is checked before treating a colon as a URI scheme.
    bare = _bare_web_address(text)
    if bare is not None:
        return bare

    if scheme_match:
        raise URLInputError(f"Unsupported URL scheme: {scheme}")

    return _search_url(text, search_engine)
