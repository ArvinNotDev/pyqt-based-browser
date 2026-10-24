from pathlib import Path
from types import SimpleNamespace

from ui.internal_pages import render_internal_page


def _browser():
    settings = SimpleNamespace(
        dark_mode=True,
        homepage="https://example.org/",
        startup_page="dashboard",
        new_tab_page="dashboard",
        default_search_engine="https://www.google.com/search?q=",
        site_compatibility_mode=False,
        private_mode=False,
        save_history=True,
        save_cookies=True,
        hardware_acceleration=True,
        webgpu_enabled=False,
        download_folder="C:/Downloads",
        proxy_panel_visible=True,
        tabs_in_title_bar=False,
    )
    history = SimpleNamespace(history={
        "https://example.org/": [{"date": "2026-10-24", "time": "10:00"}],
    })
    manager = SimpleNamespace(get_downloads=lambda: [])
    bookmarks_manager = SimpleNamespace(list_bookmarks=lambda: [
        {
            "id": "example-id",
            "title": "Example",
            "url": "https://example.org/",
            "created_at": "2026-10-24T10:00:00+00:00",
        },
        {
            "id": "home-id",
            "title": "ARMA Home",
            "url": "arma://dashboard/",
            "created_at": "2026-10-24T10:01:00+00:00",
        },
    ])
    return SimpleNamespace(
        settings=settings, history=history, download_manager=manager,
        bookmarks_manager=bookmarks_manager,
    )


def test_internal_pages_share_modern_theme_and_navigation():
    browser = _browser()
    for host in ("settings", "history", "downloads", "bookmarks"):
        document = render_internal_page(browser, host)
        assert '<nav class="nav" aria-label="Browser pages">' in document
        assert "Premium, consistent surfaces" in document
        assert "border-radius:20px" in document
        assert "class=\"nav-link active\"" in document


def test_settings_page_exposes_title_bar_tab_placement():
    document = render_internal_page(_browser(), "settings")

    assert 'id="tabs_in_title_bar"' in document
    assert 'name="tabs_in_title_bar"' in document
    assert "Show tabs in the title bar" in document
    assert "keep the window controls on the right" in document


def test_history_and_download_pages_show_clear_summary_metrics():
    browser = _browser()
    history_page = render_internal_page(browser, "history")
    downloads_page = render_internal_page(browser, "downloads")

    assert "Saved addresses" in history_page
    assert "Recorded visits" in history_page
    assert "Active transfers" in downloads_page
    assert "Completed" in downloads_page
    assert "Failed or cancelled" in downloads_page


def test_bookmarks_page_supports_search_and_safe_item_actions():
    document = render_internal_page(_browser(), "bookmarks")

    assert "Saved pages" in document
    assert "Saved items" in document
    assert "Example" in document
    assert "https://example.org/" in document
    assert "ARMA page" in document
    assert 'id="bookmark-filter"' in document
    assert 'data-action="bookmark_open"' in document
    assert 'data-action="bookmark_open_new"' in document
    assert 'data-action="bookmark_remove"' in document
    assert "Open in new tab" in document


def test_embedded_tor_connect_area_uses_transparent_shell_background():
    source = (
        Path(__file__).resolve().parents[1]
        / "proxy"
        / "ui_"
        / "window"
        / "proxy_window.py"
    ).read_text(encoding="utf-8")

    assert 'connect_host.setObjectName("connectHost")' in source
    assert 'QWidget#connectHost {{ background: transparent; border: none; border-radius: 0; }}' in source
    assert "Qt.WidgetAttribute.WA_StyledBackground" in source
