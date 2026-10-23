"""Regression tests for the custom browser frame and compact tab strip."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")

import pytest
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget

from ui.browser_window import TAB_HEIGHT, CustomTabBar, TabButton, _rounded_region
from ui.title_bar import CustomTitleBar


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_rounded_region_clips_square_page_corners():
    region = _rounded_region(QRect(0, 0, 100, 80), 16)

    assert region.contains(QPoint(50, 40))
    assert region.contains(QPoint(15, 15))
    assert not region.contains(QPoint(0, 0))
    assert not region.contains(QPoint(99, 0))


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
