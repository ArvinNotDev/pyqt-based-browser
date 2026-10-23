import json
from types import SimpleNamespace
from unittest.mock import Mock

from PySide6.QtCore import QEventLoop, QObject, QTimer, QUrl, QUrlQuery
from PySide6.QtWidgets import QApplication
from PySide6.QtWebEngineCore import QWebEngineProfile

from managers.dashboard_manager import DEFAULTS as DASHBOARD_DEFAULTS, PRESETS
from ui.browser_window import (
    BrowserPage,
    BrowserWindow,
    DASHBOARD_URL,
    DASHBOARD_SCHEME,
)
from ui.dashboard.internal_page import DashboardSchemeHandler
from ui.dashboard.bridge import DashboardBridge


def test_startup_home_and_new_tab_routes_use_configured_page():
    browser = SimpleNamespace(settings=SimpleNamespace(
        homepage="https://home.example/",
        startup_page="dashboard",
        new_tab_page="dashboard",
    ))
    assert BrowserWindow._startup_address(browser) == DASHBOARD_URL
    assert BrowserWindow._new_tab_address(browser) == DASHBOARD_URL

    browser.settings.startup_page = "homepage"
    browser.settings.new_tab_page = "homepage"
    assert BrowserWindow._startup_address(browser) == "https://home.example/"
    assert BrowserWindow._new_tab_address(browser) == "https://home.example/"


def test_dashboard_homepage_is_internal_and_not_sent_to_search():
    assert BrowserWindow._is_dashboard_address(DASHBOARD_URL)
    assert BrowserWindow._is_dashboard_address(QUrl(DASHBOARD_URL))
    assert not BrowserWindow._is_dashboard_address("https://example.test/")
    assert not BrowserWindow._is_dashboard_address("arma://other/")


def test_closing_the_last_tab_opens_a_fresh_dashboard_tab():
    view = Mock()
    view.url.return_value = QUrl("about:blank")
    placeholder = Mock()
    browser = SimpleNamespace(
        views=[view],
        current_index=0,
        tabbar=SimpleNamespace(remove_tab=Mock()),
        _placeholders={view: placeholder},
        view_layout=SimpleNamespace(removeWidget=Mock()),
        _snapshots={},
        _recorded_history_urls={},
        new_tab=Mock(),
    )

    BrowserWindow.request_close_tab(browser, 0)

    assert browser.views == []
    browser.new_tab.assert_called_once_with(DASHBOARD_URL)


def test_recently_closed_tabs_are_scoped_to_profile_and_private_session():
    browser = SimpleNamespace(
        selected_profile="Guest",
        settings=SimpleNamespace(private_mode=False),
        _closed_tab_urls={},
    )
    guest_tabs = BrowserWindow._closed_tabs_for_current_session(browser)
    guest_tabs.append("https://guest.example/")

    browser.selected_profile = "Work"
    assert BrowserWindow._closed_tabs_for_current_session(browser) == []
    browser.selected_profile = "Guest"
    browser.settings.private_mode = True
    assert BrowserWindow._closed_tabs_for_current_session(browser) == []
    BrowserWindow._closed_tabs_for_current_session(browser).append("https://private.example/")
    browser.settings.private_mode = False
    assert BrowserWindow._closed_tabs_for_current_session(browser) == ["https://guest.example/"]


def test_private_dashboard_uses_memory_notes_and_hides_history():
    browser = SimpleNamespace(
        selected_profile="Guest",
        settings=SimpleNamespace(
            private_mode=True,
            save_history=True,
            dark_mode=False,
            default_search_engine="https://search.example/?q=",
        ),
        dashboard_manager=SimpleNamespace(export=lambda: {"notes": "persistent note"}),
        _private_dashboard_notes={"Guest": "private session note"},
        _private_dashboard_quick_notes={"Guest": ["temporary note"]},
        bookmarks_manager=None,
        history=SimpleNamespace(history={"https://visited.example/": [{"date": "2026-10-23"}]}),
        _closed_tab_urls={},
        _closed_tabs_for_current_session=lambda: [],
    )

    state = BrowserWindow._dashboard_state(browser)

    assert state["notes"] == "private session note"
    assert state["quick_notes"] == ["temporary note"]
    assert state["recent"] == []


def test_dashboard_recent_pages_selects_only_the_six_most_recent():
    browser = SimpleNamespace(
        selected_profile="Guest",
        settings=SimpleNamespace(
            private_mode=False,
            save_history=True,
            dark_mode=True,
            default_search_engine="https://search.example/?q=",
        ),
        dashboard_manager=SimpleNamespace(export=lambda: {}),
        bookmarks_manager=None,
        history=SimpleNamespace(history={
            f"https://page-{day}.example/": [{"date": f"2026-10-{day:02}", "time": "12:00"}]
            for day in range(1, 13)
        }),
        _closed_tabs_for_current_session=lambda: [],
    )

    recent = BrowserWindow._dashboard_state(browser)["recent"]

    assert [item["url"] for item in recent] == [
        f"https://page-{day}.example/" for day in range(12, 6, -1)
    ]


def test_dashboard_actions_are_rejected_from_external_pages():
    browser = SimpleNamespace(_handle_dashboard_action=Mock())

    class ExternalPage(QObject):
        _dashboard_active = True

        def url(self):
            return QUrl("https://outside.example/")

    bridge = DashboardBridge(browser, ExternalPage())
    bridge.dispatch("open", json.dumps({"url": "https://target.example/"}))

    browser._handle_dashboard_action.assert_not_called()


def test_dashboard_state_sync_checks_origin_again_at_execution_time():
    browser = SimpleNamespace(_dashboard_state=lambda: {"notes": "private text"})
    page = SimpleNamespace(_dashboard_active=True, runJavaScript=Mock())

    BrowserWindow._sync_dashboard_page(browser, page)

    script = page.runJavaScript.call_args.args[0]
    assert "location.protocol === 'arma:'" in script
    assert "location.host === 'dashboard'" in script


def test_dashboard_search_uses_existing_url_resolver():
    query = QUrlQuery()
    query.addQueryItem("action", "search")
    query.addQueryItem("payload", json.dumps({"query": "privacy browser", "engine": "default"}))
    action_url = QUrl("arma-action://dispatch/")
    action_url.setQuery(query)
    page = SimpleNamespace(_dashboard_active=True, runJavaScript=Mock())
    view = SimpleNamespace(setUrl=Mock(), page=lambda: page)
    browser = SimpleNamespace(
        dashboard_manager=object(),
        settings=SimpleNamespace(default_search_engine="https://search.example/?q="),
        views=[view],
        current_view=lambda: view,
        navigate=Mock(),
    )

    BrowserWindow._handle_dashboard_action(browser, page, action_url)

    browser.navigate.assert_called_once_with("https://search.example/?q=privacy+browser")


def test_internal_dashboard_scheme_serves_a_reloadable_document():
    app = QApplication.instance() or QApplication([])
    profile = QWebEngineProfile("dashboard-test", app)
    dashboard_state = {
        **DASHBOARD_DEFAULTS,
        "presets": PRESETS,
        "wallpaper_url": "",
        "dark_mode": True,
        "default_search_engine": "https://search.example/?q=",
        "bookmarks": [],
        "recent": [],
        "closed": [],
    }
    browser = SimpleNamespace(
        _dashboard_state=lambda: dashboard_state,
        _handle_dashboard_action=Mock(),
    )
    dashboard_document = BrowserWindow._dashboard_document(browser)
    browser._dashboard_document = lambda: dashboard_document
    handler = DashboardSchemeHandler(browser, app)
    profile.installUrlSchemeHandler(DASHBOARD_SCHEME, handler)
    page = BrowserPage(browser, profile, None)
    page._enable_dashboard_bridge()
    loaded = []
    loop = QEventLoop()
    page.loadFinished.connect(lambda ok: (loaded.append(ok), loop.quit()))
    QTimer.singleShot(8000, loop.quit)

    page.setUrl(QUrl(DASHBOARD_URL))
    loop.exec()

    assert loaded == [True]
    assert page.title() == "ARMA Start"

    action_loop = QEventLoop()
    action_poll = QTimer()
    action_poll.setInterval(20)
    action_poll.timeout.connect(
        lambda: action_loop.quit() if browser._handle_dashboard_action.called else None
    )
    action_poll.start()
    QTimer.singleShot(3000, action_loop.quit)
    page.runJavaScript(
        "setTimeout(() => { const input = document.getElementById('search-input'); "
        "input.value = 'privacy browser'; "
        "document.getElementById('search-form').requestSubmit(); }, 250)"
    )
    action_loop.exec()
    action_poll.stop()
    browser._handle_dashboard_action.assert_called_once()
    action_url = browser._handle_dashboard_action.call_args.args[1]
    action_query = QUrlQuery(action_url)
    assert action_query.queryItemValue("action") == "search"
    assert '"query":"privacy browser"' in action_query.queryItemValue("payload")
    page._disable_dashboard_bridge()
    assert page._dashboard_active is False
    page._dashboard_bridge.dispatch("probe", "{}")
    browser._handle_dashboard_action.assert_called_once()
    page.deleteLater()
    profile.deleteLater()
    app.processEvents()
