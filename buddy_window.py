from PyQt6.QtWidgets import QMainWindow, QApplication, QLabel, QVBoxLayout, QWidget
from PyQt6.QtCore import Qt, QPoint, QTimer, QPropertyAnimation, pyqtProperty, QEasingCurve, QRect
from PyQt6.QtGui import QCursor, QColor, QPainter, QPainterPath, QPen, QBrush

class ClippyWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setAutoFillBackground(False)
        self.setStyleSheet("background:transparent; border:none; outline:none;")
        self._state = "IDLE"  # IDLE, LISTENING, THINKING, RESPONDING
        self._border_opacity = 0.12

        from config_manager import config
        
        # Read color from config
        color_str = config.get("cursor_color", "66,133,244")
        try:
            r, g, b = map(int, color_str.split(","))
        except:
            r, g, b = 66, 133, 244
        self.cursor_color = QColor(r, g, b)

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(40, 5, 5, 5) # Margin left so text doesn't overlap the triangle
        
        self.text_label = QLabel("")
        self.text_label.setStyleSheet("color: white; font-size: 13px; font-family: 'Segoe UI Variable', 'Segoe UI'; background-color: rgba(20, 20, 30, 210); border-radius: 8px; padding: 6px;")
        self.text_label.setWordWrap(True)
        self.text_label.hide()
        self.layout.addWidget(self.text_label)
        
    @pyqtProperty(float)
    def border_opacity(self):
        return self._border_opacity

    @border_opacity.setter
    def border_opacity(self, value):
        self._border_opacity = value
        self.update()

    def set_state(self, state):
        self._state = state
        self.update()

    def set_text(self, text):
        self.text_label.setText(text)
        if text:
            self.text_label.show()
        else:
            self.text_label.hide()
        self.adjustSize()

    def append_text(self, text):
        current = self.text_label.text()
        self.text_label.setText(current + text)
        self.adjustSize()

    def paintEvent(self, event):
        from PyQt6.QtCore import QPointF
        from PyQt6.QtGui import QPolygonF
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw the triangle at the left edge
        tx = 20
        ty = 20
        
        r, g, b = self.cursor_color.red(), self.cursor_color.green(), self.cursor_color.blue()
        
        # Pulse if listening
        alpha_mult = 1.0 if self._state != "LISTENING" else 2.0
        
        # Draw halo
        painter.setPen(Qt.PenStyle.NoPen)
        for radius, alpha in [(16, int(15 * alpha_mult)), (12, int(30 * alpha_mult)), (8, int(60 * alpha_mult))]:
            path = QPainterPath()
            path.addEllipse(QPointF(tx, ty), radius, radius)
            painter.fillPath(path, QBrush(QColor(r, g, b, min(255, alpha))))
            
        # Draw right-pointing triangle
        tr = 6
        poly = QPolygonF([QPointF(tx - tr, ty - tr), QPointF(tx - tr, ty + tr), QPointF(tx + tr, ty)])
        painter.setBrush(QBrush(QColor(r, g, b, 255)))
        painter.drawPolygon(poly)

class BuddyWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        
        # Frameless, tool, always on top
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Tool |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.WindowTransparentForInput  # Click-through when idle
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("background:transparent; border:none; outline:none;")
        
        self.central_widget = ClippyWidget()
        self.setCentralWidget(self.central_widget)
        
        self.resize(240, 44)
        
        # Lerp animation timer
        self.target_pos = QPoint(0, 0)
        self.current_pos = QPoint(0, 0)
        self.lerp_speed = 0.18
        
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_position)
        self.timer.start(16) # ~60fps

    def update_position(self):
        cursor_pos = QCursor.pos()
        # Offset 20px to the right, maybe some Y offset to align nicely
        self.target_pos = QPoint(cursor_pos.x() + 20, cursor_pos.y() - self.height() // 2)
        
        # Lerp
        cur_x = self.current_pos.x()
        cur_y = self.current_pos.y()
        tgt_x = self.target_pos.x()
        tgt_y = self.target_pos.y()
        
        new_x = cur_x + (tgt_x - cur_x) * self.lerp_speed
        new_y = cur_y + (tgt_y - cur_y) * self.lerp_speed
        
        self.current_pos = QPoint(int(new_x), int(new_y))
        
        # Don't use setGeometry or it jitters, use move
        self.move(self.current_pos)

    def set_state_idle(self):
        self.central_widget.set_state("IDLE")
        self.central_widget.set_text("")
        self.resize(40, 40) # small box for triangle only
        self.setWindowFlag(Qt.WindowType.WindowTransparentForInput, True)
        self.show()

    def set_state_listening(self):
        self.central_widget.set_state("LISTENING")
        self.central_widget.set_text("")
        self.resize(40, 40)
        self.setWindowFlag(Qt.WindowType.WindowTransparentForInput, False)
        self.show()

    def set_state_thinking(self):
        self.central_widget.set_state("THINKING")
        self.central_widget.set_text("")
        self.show()

    def set_state_responding(self, first_text=""):
        self.central_widget.set_state("RESPONDING")
        self.central_widget.set_text(first_text)
        self.resize(250, 40) # expand if text appears
        self.show()
        
    def append_response_text(self, text):
        self.central_widget.append_text(text)
