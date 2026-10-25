from PySide6.QtWidgets import QPushButton
from PySide6.QtCore import Qt, QEasingCurve, QPropertyAnimation, Property, QTimer
from PySide6.QtGui import QPainter, QColor, QBrush, QPen, QRadialGradient


class PulseButton(QPushButton):
    """Circular, animated Connect button synchronized with Tor's actual lifecycle."""

    def __init__(self, text="CONNECT"):
        super().__init__(text)
        self.setFixedSize(264, 264)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)
        self.setStyleSheet("QPushButton { background: transparent; border: none; padding: 0; margin: 0; }")
        self._state = "disconnected"
        self._dark_mode = False
        self.connected = False
        self.hovered = False
        self._pulse_radius = 103.0
        self._halo_radius = 115.0

        self.outer_anim = QPropertyAnimation(self, b"pulseRadius", self)
        self.outer_anim.setStartValue(101)
        self.outer_anim.setEndValue(124)
        self.outer_anim.setDuration(1800)
        self.outer_anim.setLoopCount(-1)
        self.outer_anim.setEasingCurve(QEasingCurve.Type.InOutSine)

        self.halo_anim = QPropertyAnimation(self, b"haloRadius", self)
        self.halo_anim.setStartValue(108)
        self.halo_anim.setEndValue(127)
        self.halo_anim.setDuration(2600)
        self.halo_anim.setLoopCount(-1)
        self.halo_anim.setEasingCurve(QEasingCurve.Type.InOutSine)

        self._connected_feedback_timer = QTimer(self)
        self._connected_feedback_timer.setSingleShot(True)
        self._connected_feedback_timer.timeout.connect(self._finish_connected_feedback)
        self.outer_anim.start()
        self.halo_anim.start()

    @property
    def state(self):
        return self._state

    def _set_state(self, state, text):
        self._connected_feedback_timer.stop()
        self._state = state
        self.connected = state in {"connected", "disconnect", "stopping"}
        # Give startup a quicker, more noticeable pulse while keeping the
        # connected/disconnected idle animation calm.
        animation_speeds = {
            "disconnected": (1800, 2600),
            "connecting": (760, 1280),
            "connected": (1350, 2100),
            "disconnect": (2050, 2900),
            "stopping": (980, 1550),
        }
        outer_duration, halo_duration = animation_speeds.get(state, (1800, 2600))
        self.outer_anim.setDuration(outer_duration)
        self.halo_anim.setDuration(halo_duration)
        self.setText(text)
        self.update()

    def set_connecting(self):
        self._set_state("connecting", "CONNECTING…")
        self.setToolTip("Starting Tor and waiting for bootstrap to complete.")

    def set_connected(self, connected):
        """Show a brief success acknowledgement, then leave a red Disconnect button."""
        if not connected:
            self._set_state("disconnected", "CONNECT")
            self.setToolTip("Connect to Tor.")
            return
        self._set_state("connected", "CONNECTED")
        self.setToolTip("Tor is connected. Disconnect from Tor.")
        self._connected_feedback_timer.start(1000)

    def _finish_connected_feedback(self):
        if self._state == "connected":
            self._state = "disconnect"
            self.connected = True
            self.setText("DISCONNECT")
            self.update()

    def set_routing_active(self):
        """Show a persistent disconnect action without implying Tor is healthy."""
        self._connected_feedback_timer.stop()
        self._set_state("disconnect", "DISCONNECT")
        self.setToolTip("Tor is unavailable. Click to leave Tor routing and restore direct browsing.")

    def set_theme(self, mode):
        """Match the animated Connect control to the surrounding Tor theme."""
        self._dark_mode = mode == "dark"
        self.update()

    def set_compact(self, compact: bool):
        """Scale the Connect control down for narrow/mobile browser panels."""
        target = 220 if compact else 264
        if self.width() != target or self.height() != target:
            self.setFixedSize(target, target)
            self.update()

    def stop_animations(self):
        """Stop all animations before the owning Tor panel shuts down."""
        for name in ("outer_anim", "halo_anim", "_connected_feedback_timer"):
            item = getattr(self, name, None)
            if item is not None:
                item.stop()

    def set_disconnecting(self):
        self._set_state("stopping", "DISCONNECTING…")
        self.setToolTip("Stopping Tor and the local proxy.")

    def enterEvent(self, event):
        self.hovered = True
        super().enterEvent(event)
        self.update()

    def leaveEvent(self, event):
        self.hovered = False
        super().leaveEvent(event)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        center = self.rect().center()
        dark_colors = {
            "disconnected": ("#4c8fe8", "#a9ceff", "#244f8b"),
            "connecting": ("#3e9bf4", "#b6dcff", "#24598f"),
            "connected": ("#2fb87b", "#a1f0c1", "#145f40"),
            "disconnect": ("#e65a6a", "#ffadb6", "#8e2636"),
            "stopping": ("#c9854b", "#ffd0a1", "#76451f"),
        }
        light_colors = {
            "disconnected": ("#3979d6", "#9ec5ff", "#1e4f91"),
            "connecting": ("#2f84d8", "#8fc9ff", "#1c528c"),
            "connected": ("#269e70", "#8fe0b8", "#176448"),
            "disconnect": ("#d94f5e", "#ff9fa8", "#8f2634"),
            "stopping": ("#bc773b", "#f5c18b", "#7c461d"),
        }
        colors = dark_colors if self._dark_mode else light_colors
        base, highlight, edge = colors.get(self._state, colors["disconnected"])
        base_color = QColor(base)
        highlight_color = QColor(highlight)
        if self.hovered:
            highlight_color = highlight_color.lighter(108)

        # During startup the outer rings move faster and use a cool blue color.
        scale = min(self.width(), self.height()) / 264.0
        if not self.isEnabled():
            painter.setOpacity(0.62)
        for radius, alpha, width, low, high in (
            (self._halo_radius, 36, 2.0, 108.0, 127.0),
            (self._pulse_radius, 78, 2.4, 101.0, 124.0),
        ):
            ring_color = QColor(base_color)
            progress = min(1.0, max(0.0, (radius - low) / (high - low)))
            ring_color.setAlpha(int(alpha * (1.0 - 0.78 * progress)))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(ring_color, width * scale))
            painter.drawEllipse(center, int(radius * scale), int(radius * scale))

        main_radius = 100 * scale
        gradient = QRadialGradient(center.x() - 30 * scale, center.y() - 37 * scale, main_radius * 2.0)
        gradient.setColorAt(0.0, highlight_color)
        gradient.setColorAt(0.62, base_color)
        gradient.setColorAt(1.0, QColor(edge))
        painter.setPen(QPen(base_color.lighter(128), 1.4 * scale))
        painter.setBrush(QBrush(gradient))
        painter.drawEllipse(center, int(main_radius), int(main_radius))

        outline = QColor("#ffffff")
        outline.setAlpha(45)
        painter.setPen(QPen(outline, 1.2 * scale))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(center, int(78 * scale), int(78 * scale))

        painter.setPen(QColor("#ffffff"))
        font = painter.font()
        font.setBold(True)
        logical_size = 13 if self._state in {"connecting", "stopping"} else 14
        # Explicitly supply a positive point size (never inherit a native -1).
        font.setPointSize(max(10, int(round(logical_size * scale))))
        painter.setFont(font)
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.text())
        painter.end()

    def getPulseRadius(self):
        return float(self._pulse_radius)

    def setPulseRadius(self, value):
        self._pulse_radius = float(value)
        self.update()

    pulseRadius = Property(float, getPulseRadius, setPulseRadius)

    def getHaloRadius(self):
        return float(self._halo_radius)

    def setHaloRadius(self, value):
        self._halo_radius = float(value)
        self.update()

    haloRadius = Property(float, getHaloRadius, setHaloRadius)
