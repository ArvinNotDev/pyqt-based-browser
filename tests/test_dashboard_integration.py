import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PySide6.QtCore import QEventLoop, QObject, QTimer, QUrl, QUrlQuery
from PySide6.QtNetwork import QNetworkProxy, QNetworkProxyFactory
from PySide6.QtWidgets import QApplication
from PySide6.QtWebEngineCore import QWebEngineLoadingInfo, QWebEngineProfile, QWebEngineUrlScheme

from managers.dashboard_manager import DEFAULTS as DASHBOARD_DEFAULTS, PRESETS
from ui.browser_window import (
    BrowserPage,
    BrowserWindow,
    DASHBOARD_URL,
    DASHBOARD_SCHEME,
)
from ui.dashboard.internal_page import DASHBOARD_DEFAULT_PORT, register_dashboard_scheme
from ui.dashboard.internal_page import DashboardSchemeHandler
from ui.dashboard.bridge import DashboardBridge
from proxy.set_proxy import manage_proxy


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
    browser = SimpleNamespace(
        _dashboard_state=lambda: {"notes": "private text"},
        _internal_host=lambda url: "dashboard" if url.toString().startswith("arma://dashboard/") else None,
    )
    page = SimpleNamespace(
        _dashboard_active=True,
        url=lambda: QUrl("arma://dashboard/"),
        runJavaScript=Mock(),
    )

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
    page = SimpleNamespace(
        _dashboard_active=True,
        url=lambda: QUrl("arma://dashboard/"),
        runJavaScript=Mock(),
    )
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

    proxy_requests = []

    class ProxyHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            proxy_requests.append(self.path)
            body = b"<html><title>proxy-enabled</title></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            pass

    proxy_server = ThreadingHTTPServer(("127.0.0.1", 0), ProxyHandler)
    Thread(target=proxy_server.serve_forever, daemon=True).start()
    had_system_proxy_factory = QNetworkProxyFactory.usesSystemConfiguration()
    proxy_loaded = []
    proxy_errors = []
    configured_proxy = None
    proxy_loop = QEventLoop()
    try:
        # A Tor-mode restart applies the proxy before creating WebEngine profiles.
        manage_proxy(None, "127.0.0.1", proxy_server.server_port, "set")
        configured_proxy = QNetworkProxy.applicationProxy()
        proxy_profile = QWebEngineProfile("tor-proxy-test", app)
        proxy_page = BrowserPage(browser, proxy_profile, None)
        proxy_page.loadFinished.connect(
            lambda ok: (proxy_loaded.append(ok), proxy_loop.quit())
        )
        proxy_page.loadingChanged.connect(
            lambda info: proxy_errors.append(
                (
                    info.errorDomain(), info.errorCode(), info.errorString(),
                    repr(info.responseHeaders()),
                )
            ) if info.status() == QWebEngineLoadingInfo.LoadStatus.LoadFailedStatus else None
        )
        QTimer.singleShot(8000, proxy_loop.quit)
        proxy_page.setUrl(QUrl("http://example.test/tor-opt-in"))
        proxy_loop.exec()

        assert proxy_loaded == [True], (
            f"proxy request failed: {proxy_page.url()} {proxy_requests} {proxy_errors} "
            f"proxy={configured_proxy.hostName()}:{configured_proxy.port()}"
        )
        assert proxy_page.title() == "proxy-enabled"
        assert "http://example.test/tor-opt-in" in proxy_requests
    finally:
        manage_proxy(None, "127.0.0.1", proxy_server.server_port, "clear")
        assert QNetworkProxyFactory.usesSystemConfiguration() == had_system_proxy_factory
        proxy_server.shutdown()
        proxy_server.server_close()

    proxy_page.deleteLater()
    proxy_profile.deleteLater()
    page.deleteLater()
    profile.deleteLater()
    app.processEvents()

def test_loading_placeholder_is_full_size_and_has_a_retry_action():
    from PySide6.QtWidgets import QPushButton, QSizePolicy, QWidget

    app = QApplication.instance() or QApplication([])
    browser = SimpleNamespace(
        settings=SimpleNamespace(dark_mode=True),
        view_container=QWidget(),
        _is_dashboard_address=BrowserWindow._is_dashboard_address,
    )

    placeholder = BrowserWindow._make_placeholder(browser, "https://offline.example/")

    assert placeholder.objectName() == "pageLoadingScreen"
    assert placeholder.sizePolicy().verticalPolicy() == QSizePolicy.Policy.Expanding
    assert placeholder.loading_detail_label.text() == "Connecting to the website…"
    retry = placeholder.findChild(QPushButton, "loadingRetry")
    assert retry is not None
    assert not retry.isVisible()
    placeholder.deleteLater()
    browser.view_container.deleteLater()
    app.processEvents()


def test_loading_failure_shows_retryable_error_but_ignores_aborted_navigation():
    view = Mock()
    view.url.return_value = QUrl("https://offline.example/")
    placeholder = Mock()
    placeholder._load_error = False
    placeholder.loading_title_label.setText = Mock()
    placeholder.loading_detail_label.setText = Mock()
    placeholder.loading_progress.hide = Mock()
    placeholder.loading_progress.show = Mock()
    placeholder.retry_button.show = Mock()
    placeholder.retry_button.hide = Mock()
    browser = SimpleNamespace(
        views=[view],
        current_view=lambda: view,
        _placeholders={view: placeholder},
        _page_load_overlays={view: Mock()},
        tabbar=SimpleNamespace(set_loading=Mock()),
        statusBar=lambda: SimpleNamespace(showMessage=Mock()),
    )

    aborted = SimpleNamespace(
        status=lambda: QWebEngineLoadingInfo.LoadStatus.LoadFailedStatus,
        errorCode=lambda: -3,
        url=lambda: QUrl("https://offline.example/"),
        errorString=lambda: "Operation canceled",
    )
    BrowserWindow._on_loading_changed(browser, aborted, view, object())
    assert placeholder._load_error is False
    placeholder.loading_title_label.setText.assert_not_called()

    failed = SimpleNamespace(
        status=lambda: QWebEngineLoadingInfo.LoadStatus.LoadFailedStatus,
        errorCode=lambda: -105,
        url=lambda: QUrl("https://offline.example/"),
        errorString=lambda: "Name not resolved",
    )
    BrowserWindow._on_loading_changed(browser, failed, view, object())
    assert placeholder._load_error is True
    placeholder.loading_title_label.setText.assert_called_once_with("This page didn’t load")
    placeholder.loading_detail_label.setText.assert_called_once_with("Name not resolved")
    placeholder.loading_progress.hide.assert_called_once_with()
    placeholder.retry_button.show.assert_called_once_with()
    browser._page_load_overlays[view].hide.assert_called_once_with()
    browser.tabbar.set_loading.assert_called_once_with(0, False)

def test_proxy_panel_is_created_only_when_requested():
    placeholder = Mock()
    browser = SimpleNamespace(
        proxy_panel=None,
        profile=object(),
        dock=SimpleNamespace(setWidget=Mock()),
        _proxy_placeholder=placeholder,
    )
    panel = Mock()

    with patch("ui.browser_window.Window", return_value=panel) as create_panel:
        result = BrowserWindow._ensure_proxy_panel(browser)

    assert result is panel
    assert browser.proxy_panel is panel
    assert panel.profile is browser.profile
    browser.dock.setWidget.assert_called_once_with(panel)
    placeholder.deleteLater.assert_called_once_with()
    assert browser._proxy_placeholder is None
    create_panel.assert_called_once_with(browser, None)

def test_dashboard_scheme_has_a_valid_default_port_and_registers_idempotently():
    register_dashboard_scheme()
    scheme = QWebEngineUrlScheme.schemeByName(DASHBOARD_SCHEME)
    assert scheme.defaultPort() == DASHBOARD_DEFAULT_PORT == 443
    assert scheme.flags() & QWebEngineUrlScheme.Flag.LocalAccessAllowed

def test_external_browser_fallback_opens_only_http_and_https_pages():
    web_view = SimpleNamespace(url=lambda: QUrl("https://game.example/"))
    status_bar = SimpleNamespace(showMessage=Mock())
    browser = SimpleNamespace(
        current_view=lambda: web_view,
        statusBar=lambda: status_bar,
    )

    with patch("ui.browser_window.QDesktopServices.openUrl", return_value=True) as open_url:
        BrowserWindow.open_current_page_externally(browser)

    open_url.assert_called_once_with(QUrl("https://game.example/"))
    status_bar.showMessage.assert_called_once_with("Opened in the default browser.", 2500)

    status_bar.showMessage.reset_mock()
    web_view.url = lambda: QUrl("arma://dashboard/")
    with patch("ui.browser_window.QDesktopServices.openUrl") as open_url:
        BrowserWindow.open_current_page_externally(browser)

    open_url.assert_not_called()
    status_bar.showMessage.assert_called_once_with("Only web pages can be opened externally.", 3000)

def test_audio_decode_diagnostics_are_recognized_without_matching_unrelated_console_errors():
    assert BrowserPage._is_audio_decode_error(
        'Loading FSB failed for audio clip "15 EngA_08282".'
    )
    assert BrowserPage._is_audio_decode_error(
        "Uncaught (in promise) EncodingError: Unable to decode audio data"
    )
    assert not BrowserPage._is_audio_decode_error("WebGL context restored")
    assert not BrowserPage._is_audio_decode_error("Uncaught ReferenceError: game is not defined")

def test_download_toast_keeps_its_own_opacity_animation():
    from PySide6.QtWidgets import QFrame, QWidget

    app = QApplication.instance() or QApplication([])

    class ToastHarness(QWidget):
        _setup_download_toast = BrowserWindow._setup_download_toast
        _finish_download_toast_animation = BrowserWindow._finish_download_toast_animation
        _hide_download_toast = BrowserWindow._hide_download_toast

        def show_downloads(self):
            pass

    harness = ToastHarness()
    harness._setup_download_toast(harness)

    assert isinstance(harness.download_toast, QFrame)
    assert harness.download_toast_effect.opacity() == 0.0
    assert harness.download_toast_animation.duration() == 180
    harness.deleteLater()
    app.processEvents()

def test_bookmarks_menu_stays_available_on_every_page():
    bar = Mock()
    browser = SimpleNamespace(bookmarks_bar=bar)

    BrowserWindow._update_bookmarks_bar_visibility(browser, DASHBOARD_URL)
    BrowserWindow._update_bookmarks_bar_visibility(browser, "https://example.test/")
    assert bar.setVisible.call_count == 2
    assert all(call.args == (True,) for call in bar.setVisible.call_args_list)


def test_cache_bypass_reload_is_limited_to_web_pages():
    from PySide6.QtWebEngineCore import QWebEnginePage

    page = Mock()
    view = SimpleNamespace(
        url=lambda: QUrl("https://example.test/"),
        page=lambda: page,
    )
    status_bar = SimpleNamespace(showMessage=Mock())
    browser = SimpleNamespace(
        current_view=lambda: view,
        statusBar=lambda: status_bar,
    )

    BrowserWindow.reload_current_page_bypassing_cache(browser)
    page.triggerAction.assert_called_once_with(
        QWebEnginePage.WebAction.ReloadAndBypassCache
    )
    status_bar.showMessage.assert_called_once_with(
        "Reloading without the local cache…", 2500
    )

    page.triggerAction.reset_mock()
    view.url = lambda: QUrl("arma://dashboard/")
    BrowserWindow.reload_current_page_bypassing_cache(browser)
    page.triggerAction.assert_not_called()




def test_page_load_overlay_hides_after_the_active_navigation_finishes():
    view = Mock()
    view.page.return_value.isLoading.return_value = False
    overlay = Mock()
    browser = SimpleNamespace(
        views=[view],
        current_view=lambda: view,
        _page_load_overlays={view: overlay},
        _page_load_overlay_for=lambda target: overlay,
    )

    BrowserWindow._hide_page_load_overlay_if_current(browser, view)

    overlay.hide.assert_called_once_with()


def test_snap_aligned_geometry_is_detected_for_half_and_quarter_windows():
    from PySide6.QtCore import QRect
    from ui.browser_window import _is_snap_aligned_geometry

    available = QRect(0, 0, 1920, 1080)
    assert _is_snap_aligned_geometry(QRect(960, 0, 960, 1080), available)
    assert _is_snap_aligned_geometry(QRect(0, 0, 960, 540), available)
    assert not _is_snap_aligned_geometry(QRect(137, 91, 1200, 770), available)



def test_tab_strip_has_favicons_loading_feedback_and_drag_reordering():
    from PySide6.QtWidgets import QApplication
    from ui.browser_window import CustomTabBar, TAB_HEIGHT

    app = QApplication.instance() or QApplication([])
    tabs = CustomTabBar()
    tabs.resize(640, 40)
    first = tabs.add_tab("First website", make_active=True)
    tabs.add_tab("Second website", make_active=False)
    tabs.add_tab("Third website", make_active=False)

    first_tab = tabs.tabs[first]
    assert first_tab.close_btn.isHidden()
    tabs.show()
    app.processEvents()

    assert not first_tab.favicon.pixmap().isNull()
    assert first_tab.height() == TAB_HEIGHT - 4
    assert tabs.height() == TAB_HEIGHT + 4
    assert tabs.scroll.height() == TAB_HEIGHT - 4

    tabs.set_loading(first, True)
    assert first_tab._loading is True
    tabs.set_loading(first, False)
    assert first_tab._loading is False

    reordered = []
    tabs.tab_reordered.connect(lambda old, new: reordered.append((old, new)))
    tabs._move_tab_to(tabs.tabs[first], 2)
    assert [tab._title for tab in tabs.tabs] == [
        "Second website", "Third website", "First website"
    ]
    assert reordered == [(0, 2)]
    tabs.close()
    tabs.deleteLater()
    app.processEvents()



def test_activating_a_loading_tab_shows_its_page_overlay():
    overlay = Mock()
    loading_view = Mock()
    loading_view.page.return_value.isLoading.return_value = True
    browser = SimpleNamespace(
        current_index=0,
        views=[loading_view],
        _page_load_overlays={loading_view: overlay},
        _placeholders={loading_view: None},
        _show_page_load_overlay=lambda target, progress=None: overlay.show_loading(progress),
        _set_tab_visibility=Mock(),
        _update_bookmarks_bar_visibility=Mock(),
        navbar=SimpleNamespace(
            url_bar=SimpleNamespace(setText=Mock()),
            set_site_connection_state=Mock(),
            set_bookmark_state=Mock(),
            back_btn=SimpleNamespace(setEnabled=Mock()),
            forward_btn=SimpleNamespace(setEnabled=Mock()),
        ),
        current_view=lambda: loading_view,
        _sync_site_connection_action=Mock(),
        bookmarks_manager=None,
        _update_navigation_actions=Mock(),
        tabbar=SimpleNamespace(set_active=Mock()),
    )
    BrowserWindow._activate(browser, 0)
    overlay.show_loading.assert_called_once_with(None)



def test_activating_a_loaded_tab_hides_a_stale_page_overlay():
    overlay = Mock()
    loaded_view = Mock()
    loaded_view.page.return_value.isLoading.return_value = False
    browser = SimpleNamespace(
        current_index=0,
        views=[loaded_view],
        _page_load_overlays={loaded_view: overlay},
        _placeholders={loaded_view: None},
        _set_tab_visibility=Mock(),
        _update_bookmarks_bar_visibility=Mock(),
        navbar=SimpleNamespace(
            url_bar=SimpleNamespace(setText=Mock()),
            set_site_connection_state=Mock(),
            set_bookmark_state=Mock(),
            back_btn=SimpleNamespace(setEnabled=Mock()),
            forward_btn=SimpleNamespace(setEnabled=Mock()),
        ),
        current_view=lambda: loaded_view,
        _sync_site_connection_action=Mock(),
        bookmarks_manager=None,
        _update_navigation_actions=Mock(),
        tabbar=SimpleNamespace(set_active=Mock()),
    )

    BrowserWindow._activate(browser, 0)

    overlay.hide.assert_called_once_with()



def test_many_tabs_use_compact_scrolling_and_an_all_tabs_menu():
    from PySide6.QtWidgets import QApplication
    from ui.browser_window import CustomTabBar, MIN_TAB_WIDTH, TAB_HEIGHT

    app = QApplication.instance() or QApplication([])
    tabs = CustomTabBar()
    tabs.resize(420, TAB_HEIGHT + 4)
    for index in range(16):
        tabs.add_tab(f"Long example website title {index + 1}", make_active=index == 0)
    tabs.show()
    app.processEvents()

    assert tabs.height() == TAB_HEIGHT + 4
    assert tabs.btn_left.isVisible()
    assert tabs.btn_right.isVisible()
    assert tabs.tab_list_button.isVisible()
    assert tabs.plus_inside is False
    assert all(tab.width() == MIN_TAB_WIDTH for tab in tabs.tabs)

    tabs._populate_tab_list_menu()
    tab_actions = [
        action for action in tabs.tab_list_menu.actions()
        if action.text() != "New tab" and not action.isSeparator()
    ]
    assert len(tab_actions) == 16
    assert tab_actions[0].isChecked()

    tabs.close()
    tabs.deleteLater()
    app.processEvents()



def test_custom_tab_bar_constructs_its_all_tabs_button():
    from PySide6.QtWidgets import QApplication, QToolButton
    from ui.browser_window import CustomTabBar

    app = QApplication.instance() or QApplication([])
    tabs = CustomTabBar()
    assert isinstance(tabs.tab_list_button, QToolButton)
    assert tabs.tab_list_button.objectName() == "tabListButton"
    assert not tabs.tab_list_button.icon().isNull()
    tabs.close()
    tabs.deleteLater()
    app.processEvents()


def test_native_frameless_style_preserves_resize_and_snap_capabilities():
    from ui.browser_window import (
        _WIN_WS_CAPTION,
        _WIN_WS_MAXIMIZEBOX,
        _WIN_WS_MINIMIZEBOX,
        _WIN_WS_SYSMENU,
        _WIN_WS_THICKFRAME,
        _with_resizable_frameless_windows_style,
    )

    original = 0x80000000 | _WIN_WS_CAPTION
    updated = _with_resizable_frameless_windows_style(original)

    assert updated & _WIN_WS_THICKFRAME
    assert updated & _WIN_WS_MAXIMIZEBOX
    assert updated & _WIN_WS_MINIMIZEBOX
    assert updated & _WIN_WS_SYSMENU
    assert updated & 0x80000000
    assert not updated & _WIN_WS_CAPTION


def test_resize_handles_cover_and_raise_all_four_window_corners():
    from PySide6.QtCore import QRect
    from ui.browser_window import BrowserWindow

    names = (
        "top", "bottom", "left", "right",
        "top_left", "top_right", "bottom_left", "bottom_right",
    )
    handles = {
        name: SimpleNamespace(setGeometry=Mock(), setVisible=Mock(), raise_=Mock())
        for name in names
    }
    browser = SimpleNamespace(
        _resize_handles=handles,
        width=lambda: 900,
        height=lambda: 700,
        isMaximized=lambda: False,
        isFullScreen=lambda: False,
    )

    BrowserWindow._update_resize_handles(browser)

    assert handles["bottom_left"].setGeometry.call_args.args[0] == QRect(0, 686, 14, 14)
    assert handles["bottom_right"].setGeometry.call_args.args[0] == QRect(886, 686, 14, 14)
    for handle in handles.values():
        handle.setVisible.assert_called_once_with(True)
        handle.raise_.assert_called_once_with()
