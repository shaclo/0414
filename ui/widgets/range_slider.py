# ============================================================
# ui/widgets/range_slider.py
# 双把手 Range Slider + 数值提示
# ============================================================

from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QDoubleSpinBox, QSlider
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QMouseEvent


class RangeSlider(QWidget):
    """
    双把手 Range Slider（水平），支持 0.5 步进的浮点值。
    内部用整数 (value * 2) 映射到浮点，绘制双把手轨道。

    信号:
        rangeChanged(float, float)  — (low, high) 变化时发出
    """
    rangeChanged = Signal(float, float)

    # 颜色常量
    TRACK_COLOR = QColor("#dcdde1")
    ACTIVE_COLOR = QColor("#3498db")
    HANDLE_BORDER = QColor("#2980b9")
    HANDLE_FILL = QColor("#ffffff")
    LABEL_COLOR = QColor("#2c3e50")

    HANDLE_RADIUS = 9
    TRACK_HEIGHT = 6

    def __init__(self, minimum=0.5, maximum=30.0, step=0.5, parent=None):
        super().__init__(parent)
        self._step = step
        self._min_val = minimum
        self._max_val = maximum
        self._low = minimum
        self._high = maximum
        self._dragging = None  # "low" | "high" | None
        self._hover = None

        self.setMinimumHeight(48)
        self.setMinimumWidth(180)
        self.setMouseTracking(True)

    # ---- 公开接口 ----
    def setRange(self, minimum: float, maximum: float):
        self._min_val = minimum
        self._max_val = maximum
        self._low = max(self._low, minimum)
        self._high = min(self._high, maximum)
        self.update()

    def setLow(self, value: float):
        self._low = max(self._min_val, min(value, self._high))
        self.update()
        self.rangeChanged.emit(self._low, self._high)

    def setHigh(self, value: float):
        self._high = min(self._max_val, max(value, self._low))
        self.update()
        self.rangeChanged.emit(self._low, self._high)

    def low(self) -> float:
        return self._low

    def high(self) -> float:
        return self._high

    # ---- 坐标转换 ----
    def _margin(self):
        return self.HANDLE_RADIUS + 2

    def _track_rect(self):
        m = self._margin()
        return m, self.height() // 2 - self.TRACK_HEIGHT // 2, self.width() - 2 * m, self.TRACK_HEIGHT

    def _val_to_x(self, val: float) -> int:
        m = self._margin()
        w = self.width() - 2 * m
        if self._max_val <= self._min_val:
            return m
        ratio = (val - self._min_val) / (self._max_val - self._min_val)
        return int(m + ratio * w)

    def _x_to_val(self, x: int) -> float:
        m = self._margin()
        w = self.width() - 2 * m
        if w <= 0:
            return self._min_val
        ratio = max(0.0, min(1.0, (x - m) / w))
        raw = self._min_val + ratio * (self._max_val - self._min_val)
        # 对齐到 step
        steps = round((raw - self._min_val) / self._step)
        return self._min_val + steps * self._step

    def _handle_hit(self, pos_x: int, pos_y: int):
        cy = self.height() // 2
        r = self.HANDLE_RADIUS + 4  # 扩大点击区
        lx = self._val_to_x(self._low)
        hx = self._val_to_x(self._high)
        dist_low = abs(pos_x - lx)
        dist_high = abs(pos_x - hx)
        in_y = abs(pos_y - cy) <= r + 4

        if not in_y:
            return None
        # 优先距离近的
        if dist_low <= r and dist_high <= r:
            return "low" if dist_low <= dist_high else "high"
        if dist_low <= r:
            return "low"
        if dist_high <= r:
            return "high"
        return None

    # ---- 绘制 ----
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        tx, ty, tw, th = self._track_rect()
        cy = self.height() // 2
        lx = self._val_to_x(self._low)
        hx = self._val_to_x(self._high)

        # 背景轨道
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(self.TRACK_COLOR))
        p.drawRoundedRect(tx, ty, tw, th, th // 2, th // 2)

        # 激活范围
        p.setBrush(QBrush(self.ACTIVE_COLOR))
        active_w = max(0, hx - lx)
        p.drawRoundedRect(lx, ty, active_w, th, th // 2, th // 2)

        # 把手
        for val, handle_name in [(self._low, "low"), (self._high, "high")]:
            hx_pos = self._val_to_x(val)
            is_active = (self._dragging == handle_name or self._hover == handle_name)
            r = self.HANDLE_RADIUS + (2 if is_active else 0)

            p.setPen(QPen(self.HANDLE_BORDER, 2))
            p.setBrush(QBrush(self.HANDLE_FILL if not is_active else self.ACTIVE_COLOR.lighter(170)))
            p.drawEllipse(hx_pos - r, cy - r, 2 * r, 2 * r)

        # 数值标签
        font = QFont()
        font.setPixelSize(11)
        font.setBold(True)
        p.setFont(font)
        p.setPen(self.LABEL_COLOR)

        low_text = self._format_val(self._low)
        high_text = self._format_val(self._high)
        p.drawText(lx - 20, cy - self.HANDLE_RADIUS - 5, 40, 14,
                   Qt.AlignCenter, low_text)
        p.drawText(hx - 20, cy + self.HANDLE_RADIUS + 3, 40, 14,
                   Qt.AlignCenter, high_text)

        p.end()

    def _format_val(self, val: float) -> str:
        if val == int(val):
            return str(int(val))
        return f"{val:.1f}"

    # ---- 鼠标交互 ----
    def mousePressEvent(self, event: QMouseEvent):
        hit = self._handle_hit(int(event.position().x()), int(event.position().y()))
        if hit:
            self._dragging = hit
            self._apply_drag(int(event.position().x()))

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._dragging:
            self._apply_drag(int(event.position().x()))
        else:
            old = self._hover
            self._hover = self._handle_hit(int(event.position().x()), int(event.position().y()))
            if old != self._hover:
                self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._dragging = None
        self.update()

    def _apply_drag(self, x: int):
        val = self._x_to_val(x)
        if self._dragging == "low":
            val = min(val, self._high)
            self._low = max(self._min_val, val)
        elif self._dragging == "high":
            val = max(val, self._low)
            self._high = min(self._max_val, val)
        self.update()
        self.rangeChanged.emit(self._low, self._high)


class DurationRangeWidget(QWidget):
    """
    每集时长区间选择组件。
    包含两个 QDoubleSpinBox + 文字提示（不含滑块）。

    信号:
        rangeChanged(float, float)
    """
    rangeChanged = Signal(float, float)

    def __init__(self, min_val=0.5, max_val=30.0, low=1.5, high=5.0, parent=None):
        super().__init__(parent)
        self._min_val = min_val
        self._max_val = max_val
        self._setup_ui(min_val, max_val, low, high)

    def _setup_ui(self, min_val, max_val, low, high):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        layout.addWidget(QLabel("每集时长:"))

        # Min SpinBox
        self._min_spin = QDoubleSpinBox()
        self._min_spin.setRange(min_val, max_val)
        self._min_spin.setSingleStep(0.5)
        self._min_spin.setDecimals(1)
        self._min_spin.setValue(low)
        self._min_spin.setMinimumWidth(150)
        self._min_spin.setFixedHeight(32)
        self._min_spin.valueChanged.connect(self._on_min_spin)
        layout.addWidget(self._min_spin)

        layout.addWidget(QLabel("~"))

        # Max SpinBox
        self._max_spin = QDoubleSpinBox()
        self._max_spin.setRange(min_val, max_val)
        self._max_spin.setSingleStep(0.5)
        self._max_spin.setDecimals(1)
        self._max_spin.setValue(high)
        self._max_spin.setMinimumWidth(150)
        self._max_spin.setFixedHeight(32)
        self._max_spin.valueChanged.connect(self._on_max_spin)
        layout.addWidget(self._max_spin)

        # 提示文字
        self._hint_label = QLabel("")
        self._hint_label.setStyleSheet("color: #2980b9; font-weight: bold;")
        self._hint_label.setMinimumWidth(110)
        layout.addWidget(self._hint_label)
        self._update_hint()

    # ---- 同步 ----
    def _on_min_spin(self, val):
        if val > self._max_spin.value():
            self._max_spin.setValue(val)
        self._update_hint()
        self.rangeChanged.emit(self._min_spin.value(), self._max_spin.value())

    def _on_max_spin(self, val):
        if val < self._min_spin.value():
            self._min_spin.setValue(val)
        self._update_hint()
        self.rangeChanged.emit(self._min_spin.value(), self._max_spin.value())

    def _update_hint(self):
        lo = self._min_spin.value()
        hi = self._max_spin.value()
        lo_s = f"{lo:.1f}" if lo != int(lo) else str(int(lo))
        hi_s = f"{hi:.1f}" if hi != int(hi) else str(int(hi))
        self._hint_label.setText(f"{lo_s}到{hi_s}分钟")

    # ---- 公开接口 ----
    def setValues(self, low: float, high: float):
        self._min_spin.blockSignals(True)
        self._max_spin.blockSignals(True)
        self._min_spin.setValue(low)
        self._max_spin.setValue(high)
        self._min_spin.blockSignals(False)
        self._max_spin.blockSignals(False)
        self._update_hint()

    def low(self) -> float:
        return self._min_spin.value()

    def high(self) -> float:
        return self._max_spin.value()

    def durationString(self) -> str:
        """返回供 Prompt 使用的时长字符串，如 '1.5到5'"""
        lo = self._min_spin.value()
        hi = self._max_spin.value()
        lo_s = f"{lo:.1f}" if lo != int(lo) else str(int(lo))
        hi_s = f"{hi:.1f}" if hi != int(hi) else str(int(hi))
        return f"{lo_s}到{hi_s}"

