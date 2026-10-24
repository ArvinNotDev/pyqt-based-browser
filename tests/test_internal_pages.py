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
    )
    history = SimpleNamespace(history={
        "https://example.org/": [{"date": "2026-10-24", "time": "10:00"}],
    })
    manager = SimpleNamespace(get_downloads=lambda: [])
    return SimpleNamespace(settings=settings, history=history, download_manager=manager)


def test_internal_pages_share_modern_theme_and_navigation():
    browser = _browser()
    for host in ("settings", "history", "downloads"):
        document = render_internal_page(browser, host)
        assert '<nav class="nav" aria-label="Browser pages">' in document
        assert "Premium, consistent surfaces" in document
        assert "border-radius:20px" in document
        assert "class=\"nav-link active\"" in document


def test_history_and_download_pages_show_clear_summary_metrics():
    browser = _browser()
    history_page = render_internal_page(browser, "history")
    downloads_page = render_internal_page(browser, "downloads")

    assert "Saved addresses" in history_page
    assert "Recorded visits" in history_page
    assert "Active transfers" in downloads_page
    assert "Completed" in downloads_page
    assert "Failed or cancelled" in downloads_page


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
