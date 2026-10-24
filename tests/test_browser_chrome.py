"""Regression tests for the custom browser frame and compact tab strip."""
import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget

from ui.browser_window import (
    TAB_HEIGHT, CustomTabBar, TabButton, _StatusMessageOverlay, _RoundedWebView,
    _BrowserShell, _title_bar_point_is_interactive,
)
from ui.title_bar import CustomTitleBar


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_webengine_viewport_is_square_and_has_no_overlaid_corner_mask(qapp):
    view = _RoundedWebView()
    assert view.objectName() == "browserPageView"
    assert not hasattr(view, "_corner_cutouts")
    view.close()


def test_custom_title_bar_does_not_show_active_page_title(qapp):
    host = _StateTrackingWindow()
    title_bar = CustomTitleBar(host)
    assert title_bar.title.text() == "ARMA Browser"
    assert not hasattr(title_bar, "page_context")
    assert not hasattr(title_bar, "set_page_title")
    host.close()


def test_clicking_an_existing_titlebar_tab_switches_back_to_it(qapp):
    host = _StateTrackingWindow()
    host.resize(900, 120)
    host_layout = QVBoxLayout(host)
    title_bar = CustomTitleBar(host)
    host_layout.addWidget(title_bar)

    tab_bar = CustomTabBar()
    title_bar.set_tabs_widget(tab_bar)
    tab_bar.add_tab("Previously opened tab", make_active=True)
    tab_bar.add_tab("Current tab", make_active=True)

    host.show()
    qapp.processEvents()

    previous_tab = tab_bar.tabs[0]
    previous_center = previous_tab.mapTo(
        title_bar, previous_tab.rect().center()
    )
    assert _title_bar_point_is_interactive(title_bar, previous_center)

    # The strip's padding and gaps must also remain client area; Windows must
    # not reinterpret a click near a tab as a window-drag gesture.
    strip_padding = tab_bar.mapTo(
        title_bar, QPoint(2, tab_bar.height() // 2)
    )
    assert _title_bar_point_is_interactive(title_bar, strip_padding)

    changed = QSignalSpy(tab_bar.tab_changed)
    QTest.mouseClick(previous_tab, Qt.MouseButton.LeftButton)
    qapp.processEvents()

    assert tab_bar.active_index == 0
    assert changed.count() == 1
    assert changed.at(0)[0] == 0

    host.close()
    qapp.processEvents()


def test_tab_strip_can_move_into_title_bar_and_return_to_workspace(qapp):
    from ui.browser_window import BrowserWindow

    host = _StateTrackingWindow()
    title_bar = CustomTitleBar(host)
    workspace = QWidget()
    workspace_layout = QVBoxLayout(workspace)
    tab_bar = CustomTabBar()
    workspace_layout.addWidget(tab_bar)

    browser = SimpleNamespace(
        settings=SimpleNamespace(tabs_in_title_bar=True),
        title_bar=title_bar,
        tabbar=tab_bar,
        browser_workspace_layout=workspace_layout,
    )

    BrowserWindow._apply_tabbar_placement(browser)
    qapp.processEvents()

    assert title_bar.tabs_widget is tab_bar
    assert title_bar.left_stack.currentWidget() is tab_bar
    assert title_bar.brand_widget.isHidden()
    assert workspace_layout.indexOf(tab_bar) == -1
    assert tab_bar.property("inTitleBar") is True
    assert title_bar.layout().indexOf(title_bar.close_button) == title_bar.layout().count() - 1

    browser.settings.tabs_in_title_bar = False
    BrowserWindow._apply_tabbar_placement(browser)
    qapp.processEvents()

    assert title_bar.tabs_widget is None
    assert title_bar.left_stack.currentWidget() is title_bar.brand_widget
    assert workspace_layout.indexOf(tab_bar) == 0
    assert tab_bar.property("inTitleBar") is False

    tab_bar.close()
    title_bar.close()
    workspace.close()
    host.close()
    qapp.processEvents()


def test_tab_widgets_fit_inside_their_strip(qapp):
    tab_bar = CustomTabBar()
    tab_bar.add_tab("A deliberately long title")
    tab = tab_bar.tabs[0]

    assert TAB_HEIGHT == 30
    assert tab.height() == TAB_HEIGHT - 4
    assert tab_bar.height() == TAB_HEIGHT + 4
    assert tab_bar.scroll.height() == TAB_HEIGHT - 4
    assert tab.close_btn.height() == 18

    tab_bar.close()
    tab.close()


class _StateTrackingWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.maximized = False
        self.fullscreen = False

    def isMaximized(self):
        return self.maximized

    def isFullScreen(self):
        return self.fullscreen

    def showMaximized(self):
        self.maximized = True

    def showNormal(self):
        self.maximized = False


def test_custom_maximize_control_toggles_and_updates_its_accessible_state(qapp):
    host = _StateTrackingWindow()
    host.resize(640, 400)
    layout = QVBoxLayout(host)
    title_bar = CustomTitleBar(host)
    layout.addWidget(title_bar)
    host.show()
    qapp.processEvents()

    QTest.mouseClick(title_bar.maximize_button, Qt.MouseButton.LeftButton)
    qapp.processEvents()
    assert host.maximized
    assert title_bar.maximize_button.toolTip() == "Restore"
    assert title_bar.maximize_button.accessibleName() == "Restore"

    QTest.mouseClick(title_bar.maximize_button, Qt.MouseButton.LeftButton)
    qapp.processEvents()
    assert not host.maximized
    assert title_bar.maximize_button.toolTip() == "Maximize"
    assert title_bar.maximize_button.accessibleName() == "Maximize"

    host.close()



def test_only_dashboard_tab_hides_close_button_and_navigation_updates_sole_tab_state(qapp):
    tabs = CustomTabBar()
    tabs.add_tab("ARMA Start", is_dashboard=True)

    dashboard_tab = tabs.tabs[0]
    assert dashboard_tab.property("dashboardTab") is True
    assert dashboard_tab._close_button_allowed is False
    assert dashboard_tab.close_btn.isHidden()

    # Every hover-driven path must respect the non-closable state.
    dashboard_tab._show_close_button_if_allowed()
    assert dashboard_tab.close_btn.isHidden()

    tabs.add_tab("Example", make_active=False)
    assert len(tabs.tabs) == 2
    assert dashboard_tab._close_button_allowed is True
    assert tabs.tabs[1]._close_button_allowed is True

    # Returning to a single dashboard tab hides its close button again.
    tabs.remove_tab(1, activate=False)
    assert len(tabs.tabs) == 1
    assert tabs.tabs[0] is dashboard_tab
    assert dashboard_tab._close_button_allowed is False
    assert dashboard_tab.close_btn.isHidden()

    # A single non-dashboard tab remains closable, matching normal tab behavior.
    tabs.add_tab("Example", make_active=False)
    tabs.remove_tab(0, activate=False)
    assert len(tabs.tabs) == 1
    assert tabs.tabs[0].property("dashboardTab") is False
    assert tabs.tabs[0]._close_button_allowed is True

    tabs.close()
    tabs.deleteLater()
    qapp.processEvents()


def test_tab_close_button_is_visible_immediately_on_hover_and_stays_visible_over_button(qapp):
    host = QWidget()
    host_layout = QVBoxLayout(host)
    tab = TabButton("Hover test")
    host_layout.addWidget(tab)
    host.resize(240, 70)
    host.show()
    qapp.processEvents()

    QTest.mouseMove(tab, QPoint(34, 10))
    qapp.processEvents()
    assert not tab.close_btn.isHidden()

    QTest.mouseMove(tab.close_btn, tab.close_btn.rect().center())
    qapp.processEvents()
    assert not tab.close_btn.isHidden()

    QTest.mouseMove(host, QPoint(230, 60))
    qapp.processEvents()
    assert tab.close_btn.isHidden()

    host.close()
    host.deleteLater()
    qapp.processEvents()



def test_status_message_is_a_bottom_left_overlay_not_a_status_bar(qapp):
    page = QWidget()
    page.resize(640, 420)
    page.show()
    qapp.processEvents()

    overlay = _StatusMessageOverlay(page, dark=True)
    overlay.showMessage("Opened in the default browser.", 2500)
    qapp.processEvents()

    assert overlay.isVisible()
    assert overlay.label.text() == "Opened in the default browser."
    assert overlay.x() < 40
    assert overlay.y() > page.height() // 2
    assert overlay.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    overlay.hide()
    page.close()
    page.deleteLater()
    qapp.processEvents()


def _make_navigation_bar(qapp):
    from ui.navigation_bar import NavigationBar
    from ui.settings import Settings

    settings = Settings()
    settings.dark_mode = False
    bar = NavigationBar(["Guest"], settings=settings)
    bar.resize(960, 50)
    bar.show()
    qapp.processEvents()
    return bar


def test_page_load_progress_tints_the_address_field_without_percentage_text(qapp):
    bar = _make_navigation_bar(qapp)
    bar.set_load_progress(45)
    qapp.processEvents()

    progress_style = bar.url_bar.styleSheet()
    assert "qlineargradient" in progress_style
    assert "stop:0.4500" in progress_style
    assert "%" not in progress_style

    bar.set_load_progress(100)
    assert "rgba(57,121,214,54)" in bar.url_bar.styleSheet()

    bar.set_load_progress(None)
    assert "qlineargradient" not in bar.url_bar.styleSheet()
    assert bar._url_load_progress is None
    bar.close()
    bar.deleteLater()
    qapp.processEvents()


def test_address_suggestions_update_in_place_without_moving_the_popup(qapp):
    bar = _make_navigation_bar(qapp)
    bar.history = {
        "https://alpha.example/": {},
        "https://another.example/": {},
        "https://bravo.example/": {},
    }

    bar._on_url_typed("a")
    popup = bar.suggestion_popup
    assert popup is not None and popup.isVisible()
    initial_geometry = popup.geometry()
    assert bar.suggestion_list.count() == 3

    bar._on_url_typed("al")
    qapp.processEvents()

    assert bar.suggestion_popup is popup
    assert popup.isVisible()
    assert popup.geometry() == initial_geometry
    assert bar.suggestion_list.count() == 1
    assert bar.suggestion_list.item(0).text() == "https://alpha.example/"

    bar._close_suggestion_popup()
    bar.close()
    bar.deleteLater()
    qapp.processEvents()


def test_navigation_controls_share_a_fixed_size_and_menu_is_the_final_action(qapp):
    from PySide6.QtCore import QSize
    from PySide6.QtWidgets import QToolButton

    bar = _make_navigation_bar(qapp)
    buttons = [
        bar.widgetForAction(bar.back_btn),
        bar.widgetForAction(bar.forward_btn),
        bar.widgetForAction(bar.reload_btn),
        bar.widgetForAction(bar.home_btn),
        bar.widgetForAction(bar.profile_btn),
        bar.bookmark_btn,
        bar.downloads_btn,
        bar.proxy_panel_btn,
        bar.menu_button,
    ]
    assert all(isinstance(button, QToolButton) for button in buttons)
    assert all(
        button.minimumSize() == QSize(34, 30)
        and button.maximumSize() == QSize(34, 30)
        for button in buttons
    )
    assert all(button.focusPolicy() == Qt.FocusPolicy.TabFocus for button in buttons)
    assert bar.url_bar.height() == 30
    centre_y = bar.url_bar.geometry().center().y()
    assert all(abs(button.geometry().center().y() - centre_y) <= 1 for button in buttons)
    assert bar.widgetForAction(bar.actions()[-1]) is bar.menu_button
    assert bar.contentsMargins().right() == 4

    bar.close()
    bar.deleteLater()
    qapp.processEvents()



def test_downloads_layout_toggle_uses_pin_and_unpin_icon_actions(qapp):
    from ui.downloads_panel import DownloadsPanel

    panel = DownloadsPanel()
    button = panel.mode_button
    assert button.text() == ""
    assert button.iconSize().width() == 15
    assert button.focusPolicy() == Qt.FocusPolicy.TabFocus
    assert button.property("downloadsPinned") is False
    assert button.toolTip() == "Pin downloads panel beside the page"
    assert not button.icon().isNull()

    panel.set_docked(True)
    assert button.property("downloadsPinned") is True
    assert button.toolTip() == "Unpin downloads panel and return to overlay"
    assert button.accessibleName() == "Unpin downloads panel"
    assert not button.icon().isNull()

    panel.close()
    panel.deleteLater()
    qapp.processEvents()


def test_proxy_indicator_restores_explicitly_visible_panel_state_on_startup():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "ui/browser_window.py").read_text(
        encoding="utf-8"
    )
    assert source.count("self.navbar.set_proxy_panel_state(not self.dock.isHidden())") == 2
    assert "self.navbar.set_proxy_panel_state(self.dock.isVisible())" not in source


def test_title_bar_hosted_tab_strip_new_and_close_controls_emit_actions(qapp):
    host = _StateTrackingWindow()
    host.resize(900, 120)
    host_layout = QVBoxLayout(host)
    title_bar = CustomTitleBar(host)
    host_layout.addWidget(title_bar)
    tab_bar = CustomTabBar()
    title_bar.set_tabs_widget(tab_bar)
    host.show()
    qapp.processEvents()

    # A native Windows hit-test must leave child controls clickable even while
    # treating the rest of the custom title bar as a draggable caption.
    plus_point = tab_bar.plus_tab.mapTo(
        title_bar, tab_bar.plus_tab.rect().center()
    )
    assert _title_bar_point_is_interactive(title_bar, plus_point)
    blank_point = title_bar.left_stack.mapTo(
        title_bar, QPoint(title_bar.left_stack.width() - 12, title_bar.left_stack.height() // 2)
    )
    assert not _title_bar_point_is_interactive(title_bar, blank_point)

    new_tab_spy = QSignalSpy(tab_bar.new_tab_requested)
    close_tab_spy = QSignalSpy(tab_bar.tab_closed)

    # QPushButton.clicked carries a checked bool; the tab-bar signal has no args.
    QTest.mouseClick(tab_bar.plus_tab, Qt.MouseButton.LeftButton)
    qapp.processEvents()
    assert new_tab_spy.count() == 1

    # The overflow layout uses a second plus button; the tab-list menu has
    # another "New tab" action. All entry points must discard Qt's checked bool.
    tab_bar.external_plus.show()
    QTest.mouseClick(tab_bar.external_plus, Qt.MouseButton.LeftButton)
    qapp.processEvents()
    assert new_tab_spy.count() == 2

    tab_bar._populate_tab_list_menu()
    new_action = next(action for action in tab_bar.tab_list_menu.actions() if action.text() == "New tab")
    new_action.trigger()
    qapp.processEvents()
    assert new_tab_spy.count() == 3

    tab_bar.add_tab("Closable tab")
    qapp.processEvents()
    tab = tab_bar.tabs[0]
    tab.close_btn.show()
    qapp.processEvents()
    QTest.mouseClick(tab.close_btn, Qt.MouseButton.LeftButton)
    qapp.processEvents()

    assert close_tab_spy.count() == 1
    assert close_tab_spy.at(0)[0] == 0

    host.close()
    tab_bar.close()
    title_bar.close()
    qapp.processEvents()



def test_resize_overlays_stop_before_the_interactive_title_bar(qapp):
    from ui.browser_window import BrowserWindow
    from PySide6.QtWidgets import QWidget

    host = _StateTrackingWindow()
    host.resize(900, 320)
    layout = QVBoxLayout(host)
    layout.setContentsMargins(4, 4, 4, 4)
    title_bar = CustomTitleBar(host)
    layout.addWidget(title_bar)
    host.title_bar = title_bar
    host._resize_handles = {
        name: QWidget(host)
        for name in (
            "top", "bottom", "left", "right",
            "top_left", "top_right", "bottom_left", "bottom_right",
        )
    }
    host.show()
    qapp.processEvents()

    title_top = title_bar.mapTo(host, QPoint(0, 0)).y()
    BrowserWindow._update_resize_handles(host)

    assert host._resize_handles["top"].height() <= title_top
    assert host._resize_handles["top_left"].height() <= title_top
    assert host._resize_handles["top_right"].height() <= title_top
    assert host._resize_handles["top"].geometry().bottom() < title_top

    host.close()
    title_bar.close()
    qapp.processEvents()


def test_browser_shell_paints_imported_wallpaper_behind_transparent_header(qapp):
    from PySide6.QtCore import QByteArray, QBuffer, QIODevice
    from PySide6.QtGui import QColor, QImage, QPixmap
    from PySide6.QtWidgets import QWidget

    shell = _BrowserShell()
    shell.setObjectName("browserShell")
    shell.resize(420, 130)
    shell.setStyleSheet("QFrame#browserShell { background: #ffffff; border: none; }")

    title_bar = QWidget(shell)
    title_bar.setObjectName("customTitleBar")
    title_bar.setGeometry(0, 0, 420, 36)
    title_bar.setStyleSheet("QWidget#customTitleBar { background: transparent; border: none; }")
    navbar = QWidget(shell)
    navbar.setObjectName("NavigationBar")
    navbar.setGeometry(0, 36, 420, 50)
    navbar.setStyleSheet("QWidget#NavigationBar { background: transparent; border: none; }")

    image = QImage(64, 32, QImage.Format.Format_RGB32)
    image.fill(QColor("#e54545"))
    payload = QByteArray()
    buffer = QBuffer(payload)
    assert buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    assert image.save(buffer, "PNG")
    buffer.close()

    assert shell.set_header_wallpaper(bytes(payload), title_bar, navbar, dark_mode=False)
    shell.show()
    qapp.processEvents()
    # Repeated paints catch failures that leave the QPainter active and break
    # later repaints of the header or the rest of the window.
    for _ in range(2):
        rendered = QPixmap(shell.size())
        rendered.fill(Qt.GlobalColor.transparent)
        shell.render(rendered)
        pixel = rendered.toImage().pixelColor(210, 20)

        # The light glass tint alters red, but the selected image remains visible
        # through the title bar instead of being covered by an opaque theme fill.
        assert pixel.red() > pixel.green() + 35
        assert pixel.red() > pixel.blue() + 25

    shell.close()
    shell.deleteLater()
    qapp.processEvents()
