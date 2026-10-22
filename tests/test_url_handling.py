import importlib
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


@pytest.fixture
def browser_class(tmp_path, monkeypatch):
    # proxy.ui loads its config during import; redirect that read/write into this test's temp dir.
    isolated_bundle = tmp_path / "bundle"
    isolated_bundle.mkdir()
    monkeypatch.setattr(sys, "_MEIPASS", str(isolated_bundle), raising=False)
    module = importlib.import_module("ui.browser_window")
    return module.BrowserWindow


def navigate_with_fake_browser(browser_class, text):
    view = SimpleNamespace(setUrl=Mock())
    address_bar = SimpleNamespace(setText=Mock())
    browser = SimpleNamespace(
        settings=SimpleNamespace(default_search_engine="https://search.example/?q="),
        current_view=lambda: view,
        navbar=SimpleNamespace(url_bar=address_bar),
    )

    browser_class.navigate(browser, text)
    return browser, view, address_bar


def test_navigation_treats_words_as_a_search(browser_class):
    _browser, view, _address_bar = navigate_with_fake_browser(browser_class, "privacy browser")
    target = view.setUrl.call_args.args[0].toString()

    assert target == "https://search.example/?q=privacy+browser"


def test_navigation_adds_https_to_a_domain_address(browser_class):
    _browser, view, address_bar = navigate_with_fake_browser(browser_class, "example.com/path")

    assert view.setUrl.call_args.args[0].toString() == "https://example.com/path"
    address_bar.setText.assert_called_once_with("https://example.com/path")


def test_navigation_preserves_an_explicit_http_scheme(browser_class):
    _browser, view, _address_bar = navigate_with_fake_browser(
        browser_class, "http://example.com/path"
    )

    assert view.setUrl.call_args.args[0].toString() == "http://example.com/path"
