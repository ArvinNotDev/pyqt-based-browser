"""Regression tests for the custom browser frame and compact tab strip."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")

import pytest
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtTest import QTest
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget

from ui.browser_window import (
    TAB_HEIGHT, CustomTabBar, TabButton, _StatusMessageOverlay, _RoundedCornerCutout,
)
from ui.title_bar import CustomTitleBar


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_rounded_corner_cutout_uses_antialiased_paint(qapp):
    host = QWidget()
    cutout = _RoundedCornerCutout(host, "top-left", 12)
    cutout.set_color(QColor("#ff0000"))
    cutout.resize(12, 12)

    image = QImage(12, 12, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    cutout.render(image)

    assert image.pixelColor(0, 0).alpha() == 255
    assert image.pixelColor(11, 11).alpha() == 0
    assert any(
        0 < image.pixelColor(x, y).alpha() < 255
        for y in range(image.height())
        for x in range(image.width())
    )
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
