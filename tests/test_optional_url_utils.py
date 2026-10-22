"""Address-bar helper tests; the helper is supplied by the browser-core branch."""

import importlib
from pathlib import Path

import pytest


URL_UTILS_PATH = Path(__file__).resolve().parents[1] / "ui" / "url_utils.py"


@pytest.fixture(scope="module")
def url_utils():
    if not URL_UTILS_PATH.is_file():
        pytest.skip("ui/url_utils.py has not been integrated on this branch")
    return importlib.import_module("ui.url_utils")


def test_url_helper_distinguishes_queries_and_web_addresses(url_utils):
    search = "https://search.example/?q="
    assert url_utils.resolve_address_input("privacy browser", search) == (
        "https://search.example/?q=privacy+browser"
    )
    assert url_utils.resolve_address_input("example.com/path", search) == (
        "https://example.com/path"
    )
    assert url_utils.resolve_address_input("localhost:8080", search) == (
        "https://localhost:8080"
    )
    assert url_utils.resolve_address_input("about:blank", search) == "about:blank"


@pytest.mark.parametrize(
    "value",
    ["file:///tmp/private", "https://example.com:99999", "https://user:pass@example.com"],
)
def test_url_helper_rejects_unsupported_or_unsafe_input(value, url_utils):
    with pytest.raises(url_utils.URLInputError):
        url_utils.resolve_address_input(value, "https://search.example/?q=")


def test_url_helper_supports_query_template_and_encodes_query(url_utils):
    resolved = url_utils.resolve_address_input(
        "cats & dogs", "https://search.example/?q={query}"
    )

    assert resolved == "https://search.example/?q=cats+%26+dogs"
