import math
from PyQt6.QtWidgets import QWidget, QLabel
from PyQt6.QtCore import Qt, QPoint, QTimer, QSize
from PyQt6.QtGui import QCursor, QColor, QPainter, QPainterPath, QBrush, QPolygonF, QRegion
from PyQt6.QtCore import QPointF


class BuddyWindow(QWidget):
    """
    Top-level transparent widget that follows the cursor.
    Renders ONLY the blue triangle + optional text bubble.
    No layout used — text label is manually positioned to avoid
    Qt enforcing a minimum window size when the label is hidden.
    """

    def __init__(self):
        super().__init__(None)

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowTransparentForInput
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)
        self.setStyleSheet("background: transparent; border: none;")

        self._state = "IDLE"
        self._halo_phase = 0.0

        from config_manager import config
        color_str = config.get("cursor_color", "66,133,244")
        try:
            r, g, b = map(int, color_str.split(","))
        except Exception:
            r, g, b = 66, 133, 244
        self.cursor_color = QColor(r, g, b)

        # Pulse timer
        self._pulse_timer = QTimer(self)
        self._pulse_timer.timeout.connect(self._tick_pulse)
        self._pulse_timer.setInterval(33)

        # Cursor-follow
        cursor_pos = QCursor.pos()
        self.target_pos = QPoint(cursor_pos.x() + 20, cursor_pos.y())
        self.current_pos = QPoint(cursor_pos.x() + 20, cursor_pos.y())
        self.lerp_speed = 0.18

        self._follow_timer = QTimer(self)
        self._follow_timer.timeout.connect(self._update_position)
        self._follow_timer.start(16)

        self.setFixedSize(30, 30)
        # Apply a circular clipping mask so Windows mathematically cannot draw a rectangle
        self.setMask(QRegion(0, 0, 30, 30, QRegion.RegionType.Ellipse))

    # ------------------------------------------------------------------
    # Override size hints so Qt never enforces a bigger minimum
    # ------------------------------------------------------------------
    def minimumSizeHint(self):
        return QSize(30, 30)

    def sizeHint(self):
        return QSize(30, 30)

    # ------------------------------------------------------------------
    # Live preview injection
    # ------------------------------------------------------------------
    def set_color(self, rgb_str):
        try:
            r, g, b = map(int, rgb_str.split(","))
            self.cursor_color = QColor(r, g, b)
            self.update()
        except:
            pass

    # ------------------------------------------------------------------
    # Cursor-follow lerp
    # ------------------------------------------------------------------
    def _update_position(self):
        cursor_pos = QCursor.pos()
        self.target_pos = QPoint(cursor_pos.x() + 20, cursor_pos.y() - self.height() // 2)

        cx = self.current_pos.x() + (self.target_pos.x() - self.current_pos.x()) * self.lerp_speed
        cy = self.current_pos.y() + (self.target_pos.y() - self.current_pos.y()) * self.lerp_speed
        self.current_pos = QPoint(int(cx), int(cy))
        self.move(self.current_pos)

    # ------------------------------------------------------------------
    # State management
    # ------------------------------------------------------------------
    def set_state(self, state):
        self._state = state
        if state == "LISTENING":
            self._halo_phase = 0.0
            self._pulse_timer.start()
        else:
            self._pulse_timer.stop()
        self.update()

    def set_state_idle(self):
        self.set_state("IDLE")
        self.setWindowFlag(Qt.WindowType.WindowTransparentForInput, True)
        self.show()

    def set_state_listening(self):
        self.set_state("LISTENING")
        self.setWindowFlag(Qt.WindowType.WindowTransparentForInput, False)
        self.show()

    def set_state_thinking(self):
        self.set_state("THINKING")
        self.show()

    def set_state_responding(self, first_text=""):
        self.set_state("RESPONDING")
        self.show()

    # ------------------------------------------------------------------
    # Text (No-op now, completely auditory model)
    # ------------------------------------------------------------------
    def set_text(self, text):
        pass

    def append_response_text(self, text):
        pass

    # ------------------------------------------------------------------
    # Pulse
    # ------------------------------------------------------------------
    def _tick_pulse(self):
        self._halo_phase += 0.1
        self.update()

    # ------------------------------------------------------------------
    # Paint — the ONLY source of visible pixels
    # ------------------------------------------------------------------
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Triangle center horizontally and vertically inside 30x30 block
        tx, ty = 15, 15
        r, g, b = self.cursor_color.red(), self.cursor_color.green(), self.cursor_color.blue()

        painter.setPen(Qt.PenStyle.NoPen)

        if self._state == "LISTENING":
            pulse = 0.5 + 0.5 * math.sin(self._halo_phase * 2 * math.pi / 6)
            for radius, base_alpha in [(11, 15), (8, 30), (5, 60)]:
                path = QPainterPath()
                path.addEllipse(QPointF(tx, ty), radius + pulse * 4, radius + pulse * 4)
                painter.fillPath(path, QBrush(QColor(r, g, b, min(255, int(base_alpha + pulse * 40)))))
        elif self._state == "THINKING":
            for radius, alpha in [(10, 40), (6, 80)]:
                path = QPainterPath()
                path.addEllipse(QPointF(tx, ty), radius, radius)
                painter.fillPath(path, QBrush(QColor(r, g, b, alpha)))

        # Triangle cursor — always drawn
        tr = 6
        poly = QPolygonF([QPointF(tx - tr, ty - tr), QPointF(tx - tr, ty + tr), QPointF(tx + tr, ty)])
        painter.setBrush(QBrush(QColor(r, g, b, 255)))
        painter.drawPolygon(poly)

        painter.end()
