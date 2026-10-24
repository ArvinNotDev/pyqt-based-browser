"""Trackpad two-finger back/forward navigation with a lightweight animated cue.

The WebEngine viewport owns the gesture controller, so each tab operates on its
own QWebEngineHistory and the gesture never snapshots or composites live pages.
"""
from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QObject,
    QRectF,
    Qt,
    QTimer,
    QVariantAnimation,
)
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget


_BACK = 1
_FORWARD = -1


class _HistorySwipeIndicator(QWidget):
    """Small Chromium-style arrow indicator that tracks swipe progress."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("historySwipeIndicator")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._direction = 0
        self._progress = 0.0
        self._opacity = 1.0
        self._committed = False

        self._fade_animation = QVariantAnimation(self)
        self._fade_animation.setDuration(150)
        self._fade_animation.setStartValue(1.0)
        self._fade_animation.setEndValue(0.0)
        self._fade_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade_animation.valueChanged.connect(self._set_opacity)
        self._fade_animation.finished.connect(self.hide)

        self._commit_timer = QTimer(self)
        self._commit_timer.setSingleShot(True)
        self._commit_timer.setInterval(90)
        self._commit_timer.timeout.connect(self.fade_out)
        self.hide()

    def set_gesture_progress(self, direction: int, distance: float, threshold: float) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        self._fade_animation.stop()
        self._commit_timer.stop()
        self._direction = direction
        self._progress = max(0.0, min(1.0, distance / max(1.0, threshold)))
        self._opacity = 1.0
        self._committed = False
        self.setGeometry(parent.rect())
        self.show()
        self.raise_()
        self.update()

    def show_committed(self, direction: int) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        self._fade_animation.stop()
        self._direction = direction
        self._progress = 1.0
        self._opacity = 1.0
        self._committed = True
        self.setGeometry(parent.rect())
        self.show()
        self.raise_()
        self.update()
        self._commit_timer.start()

    def fade_out(self) -> None:
        if self.isHidden():
            return
        self._commit_timer.stop()
        self._fade_animation.stop()
        self._fade_animation.setStartValue(float(self._opacity))
        self._fade_animation.setEndValue(0.0)
        self._fade_animation.start()

    def _set_opacity(self, value) -> None:
        self._opacity = max(0.0, min(1.0, float(value)))
        self.update()

    def paintEvent(self, event) -> None:
        if self._direction not in (_BACK, _FORWARD) or self._opacity <= 0.0:
            return

        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setOpacity(self._opacity)

            radius = 23.0
            travel = min(58.0, 58.0 * self._progress)
            centre_y = self.height() / 2.0
            if self._direction == _BACK:
                centre_x = -radius + 9.0 + travel
            else:
                centre_x = self.width() + radius - 9.0 - travel
            outer = QRectF(
                centre_x - radius,
                centre_y - radius,
                radius * 2.0,
                radius * 2.0,
            )

            fill = (
                QColor(47, 123, 239, 245)
                if self._committed
                else QColor(28, 38, 53, 232)
            )
            painter.setPen(QPen(QColor(255, 255, 255, 65), 1.0))
            painter.setBrush(fill)
            painter.drawEllipse(outer)

            # A thin progress arc turns solid with the commit state.
            ring = QRectF(
                centre_x - radius + 3.0,
                centre_y - radius + 3.0,
                (radius - 3.0) * 2.0,
                (radius - 3.0) * 2.0,
            )
            ring_color = (
                QColor(255, 255, 255, 230)
                if self._committed
                else QColor(137, 185, 255, 235)
            )
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(
                QPen(
                    ring_color,
                    2.2,
                    Qt.PenStyle.SolidLine,
                    Qt.PenCapStyle.RoundCap,
                    Qt.PenJoinStyle.RoundJoin,
                )
            )
            painter.drawArc(ring, 90 * 16, -int(360 * 16 * self._progress))

            # The arrow points toward the history destination; it is drawn as
            # vector geometry so it remains crisp at every display scale.
            arrow = QPainterPath()
            if self._direction == _BACK:
                arrow.moveTo(centre_x + 5.0, centre_y - 8.0)
                arrow.lineTo(centre_x - 4.0, centre_y)
                arrow.lineTo(centre_x + 5.0, centre_y + 8.0)
                arrow.moveTo(centre_x - 4.0, centre_y)
                arrow.lineTo(centre_x + 8.0, centre_y)
            else:
                arrow.moveTo(centre_x - 5.0, centre_y - 8.0)
                arrow.lineTo(centre_x + 4.0, centre_y)
                arrow.lineTo(centre_x - 5.0, centre_y + 8.0)
                arrow.moveTo(centre_x - 8.0, centre_y)
                arrow.lineTo(centre_x + 4.0, centre_y)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(
                QPen(
                    QColor(255, 255, 255, 250),
                    2.2,
                    Qt.PenStyle.SolidLine,
                    Qt.PenCapStyle.RoundCap,
                    Qt.PenJoinStyle.RoundJoin,
                )
            )
            painter.drawPath(arrow)
        finally:
            painter.end()


class HistorySwipeController(QObject):
    """Recognize horizontal trackpad gestures and navigate on release."""

    BACK = _BACK
    FORWARD = _FORWARD
    HORIZONTAL_DOMINANCE = 1.45
    END_IDLE_MS = 170
    END_PHASE_MS = 120

    def __init__(self, view: QWidget):
        super().__init__(view)
        self.view = view
        self.indicator = _HistorySwipeIndicator(view)
        self._active = False
        self._direction = 0
        self._distance = 0.0
        self._threshold = 120.0

        self._end_timer = QTimer(self)
        self._end_timer.setSingleShot(True)
        self._end_timer.timeout.connect(self._finish_gesture)
        view.installEventFilter(self)

    def eventFilter(self, watched, event) -> bool:
        if watched is self.view and event.type() == QEvent.Type.Wheel:
            return self.handle_wheel_event(event)
        if watched is self.view and event.type() == QEvent.Type.Hide:
            self._cancel_gesture()
        return super().eventFilter(watched, event)

    @staticmethod
    def _wheel_delta(event) -> tuple[float, float]:
        pixel_delta = event.pixelDelta()
        if not pixel_delta.isNull():
            return float(pixel_delta.x()), float(pixel_delta.y())
        angle_delta = event.angleDelta()
        # Angle deltas are in eighths of a degree. Scaling keeps a horizontal
        # wheel stream usable while requiring multiple ticks for a full swipe.
        return float(angle_delta.x()) / 3.0, float(angle_delta.y()) / 3.0

    def _can_navigate(self, direction: int) -> bool:
        try:
            history = self.view.history()
            if direction == _BACK:
                return bool(history.canGoBack())
            if direction == _FORWARD:
                return bool(history.canGoForward())
        except (AttributeError, RuntimeError):
            return False
        return False

    def _start_gesture(self, direction: int) -> None:
        self._active = True
        self._direction = direction
        self._distance = 0.0
        self._threshold = max(96.0, min(float(max(1, self.view.width())) * 0.24, 260.0))

    def _add_delta(self, dx: float) -> None:
        directional_delta = dx if self._direction == _BACK else -dx
        self._distance = max(0.0, self._distance + directional_delta)
        self.indicator.set_gesture_progress(
            self._direction,
            self._distance,
            self._threshold,
        )

    def _arm_end_timer(self, phase) -> None:
        delay = (
            self.END_PHASE_MS
            if phase == Qt.ScrollPhase.ScrollEnd
            else self.END_IDLE_MS
        )
        self._end_timer.start(delay)

    def handle_wheel_event(self, event) -> bool:
        """Return True only while the event belongs to a recognized history swipe."""
        phase = event.phase()

        if self._active:
            if phase == Qt.ScrollPhase.ScrollEnd:
                dx, _dy = self._wheel_delta(event)
                if dx:
                    self._add_delta(dx)
                self._arm_end_timer(phase)
                event.accept()
                return True

            dx, dy = self._wheel_delta(event)
            if dx and abs(dx) >= abs(dy) * self.HORIZONTAL_DOMINANCE:
                self._add_delta(dx)
            self._arm_end_timer(phase)
            event.accept()
            return True

        # Momentum may extend a swipe that was already recognized, but must
        # never start a new history navigation on its own.
        if phase == Qt.ScrollPhase.ScrollMomentum:
            return False

        dx, dy = self._wheel_delta(event)
        if not dx or abs(dx) < abs(dy) * self.HORIZONTAL_DOMINANCE:
            return False

        direction = _BACK if dx > 0.0 else _FORWARD
        if not self._can_navigate(direction):
            # Let the page handle the event when history cannot move that way.
            return False

        self._start_gesture(direction)
        self._add_delta(dx)
        self._arm_end_timer(phase)
        event.accept()
        return True

    def _finish_gesture(self) -> None:
        self._end_timer.stop()
        if not self._active:
            return

        direction = self._direction
        should_navigate = (
            self._distance >= self._threshold
            and self._can_navigate(direction)
        )
        self._active = False
        self._direction = 0
        self._distance = 0.0

        if not should_navigate:
            self.indicator.fade_out()
            return

        self.indicator.show_committed(direction)
        try:
            if direction == _BACK:
                self.view.back()
            else:
                self.view.forward()
        except RuntimeError:
            self.indicator.fade_out()

    def _cancel_gesture(self) -> None:
        self._end_timer.stop()
        self._active = False
        self._direction = 0
        self._distance = 0.0
        self.indicator.fade_out()
