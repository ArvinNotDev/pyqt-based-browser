"""Unit tests for touchpad history-swipe gesture handling."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication, QWidget

from ui.history_swipe import HistorySwipeController


class _FakeHistory:
    def __init__(self, back=False, forward=False):
        self.back = bool(back)
        self.forward = bool(forward)

    def canGoBack(self):
        return self.back

    def canGoForward(self):
        return self.forward


class _FakePage:
    def __init__(self):
        self.pending_scroll_query = None

    def runJavaScript(self, _script, callback):
        self.pending_scroll_query = callback

    def resolve_scroll_query(self, can_scroll):
        callback = self.pending_scroll_query
        self.pending_scroll_query = None
        assert callback is not None
        callback(bool(can_scroll))


class _FakeView(QWidget):
    def __init__(self, back=False, forward=False):
        super().__init__()
        self._history = _FakeHistory(back=back, forward=forward)
        self._page = _FakePage()
        self.navigation_actions = []

    def history(self):
        return self._history

    def page(self):
        return self._page

    def back(self):
        self.navigation_actions.append("back")

    def forward(self):
        self.navigation_actions.append("forward")


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _wheel(dx, dy=0, phase=Qt.ScrollPhase.ScrollUpdate):
    position = QPointF(120.0, 90.0)
    return QWheelEvent(
        position,
        position,
        QPoint(round(dx), round(dy)),
        QPoint(),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        phase,
        False,
    )


def _make_controller(qapp, *, back=False, forward=False):
    view = _FakeView(back=back, forward=forward)
    view.resize(400, 280)
    controller = HistorySwipeController(view)
    return view, controller


def test_swipe_right_commits_back_navigation_only_after_release(qapp):
    view, controller = _make_controller(qapp, back=True)

    assert not controller.handle_wheel_event(_wheel(55, phase=Qt.ScrollPhase.ScrollBegin))
    assert not controller.handle_wheel_event(_wheel(65, phase=Qt.ScrollPhase.ScrollUpdate))
    assert view.navigation_actions == []

    # Resolve the DOM scrollability check as "not scrollable"; recognition starts
    # with the accumulated deltas, but navigation still waits for gesture release.
    view.page().resolve_scroll_query(False)
    assert controller._active
    assert controller.indicator._progress == 1.0
    assert view.navigation_actions == []

    assert controller.handle_wheel_event(_wheel(0, phase=Qt.ScrollPhase.ScrollEnd))
    controller._finish_gesture()
    assert view.navigation_actions == ["back"]

    view.close()


def test_swipe_left_commits_forward_navigation(qapp):
    view, controller = _make_controller(qapp, forward=True)

    assert not controller.handle_wheel_event(
        _wheel(-70, phase=Qt.ScrollPhase.ScrollBegin)
    )
    assert not controller.handle_wheel_event(
        _wheel(-50, phase=Qt.ScrollPhase.ScrollUpdate)
    )
    view.page().resolve_scroll_query(False)
    assert controller._active
    controller._finish_gesture()

    assert view.navigation_actions == ["forward"]
    view.close()


def test_short_swipe_cancels_without_navigating(qapp):
    view, controller = _make_controller(qapp, back=True)

    assert not controller.handle_wheel_event(
        _wheel(28, phase=Qt.ScrollPhase.ScrollBegin)
    )
    assert not controller.handle_wheel_event(
        _wheel(24, phase=Qt.ScrollPhase.ScrollUpdate)
    )
    view.page().resolve_scroll_query(False)
    assert controller._active
    controller._finish_gesture()

    assert view.navigation_actions == []
    view.close()


def test_vertical_or_diagonal_scroll_is_left_to_the_page(qapp):
    view, controller = _make_controller(qapp, back=True)

    assert not controller.handle_wheel_event(
        _wheel(12, 45, phase=Qt.ScrollPhase.ScrollUpdate)
    )
    assert view.page().pending_scroll_query is None
    assert view.navigation_actions == []
    assert not controller._active
    view.close()


def test_swipe_without_history_in_that_direction_is_left_to_the_page(qapp):
    view, controller = _make_controller(qapp, back=False, forward=True)

    assert not controller.handle_wheel_event(_wheel(120))
    assert view.page().pending_scroll_query is None
    assert not controller._active
    assert view.navigation_actions == []
    view.close()


def test_page_horizontal_scrolling_has_priority_over_history(qapp):
    view, controller = _make_controller(qapp, back=True)

    assert not controller.handle_wheel_event(
        _wheel(70, phase=Qt.ScrollPhase.ScrollBegin)
    )
    view.page().resolve_scroll_query(True)

    assert not controller._active
    assert controller._ignore_current_gesture
    assert not controller.handle_wheel_event(
        _wheel(70, phase=Qt.ScrollPhase.ScrollUpdate)
    )
    assert view.navigation_actions == []
    view.close()


def test_momentum_cannot_start_a_new_gesture(qapp):
    view, controller = _make_controller(qapp, back=True)

    assert not controller.handle_wheel_event(
        _wheel(160, phase=Qt.ScrollPhase.ScrollMomentum)
    )
    assert view.page().pending_scroll_query is None
    assert not controller._active
    assert view.navigation_actions == []
    view.close()
