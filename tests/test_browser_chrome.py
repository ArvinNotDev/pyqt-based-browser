"""Regression tests for the custom browser frame and compact tab strip."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget

from ui.browser_window import (
    TAB_HEIGHT, CustomTabBar, TabButton, _StatusMessageOverlay, _RoundedWebView,
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
    assert all(button.size() == QSize(34, 30) for button in buttons)
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
