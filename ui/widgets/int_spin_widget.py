# ============================================================
# ui/widgets/int_spin_widget.py
# 自定义整数输入控件：[输入框][▲ 上按钮]
#                                [▼ 下按钮]
# 外观与标准 SpinBox 完全一致，但上下按钮是独立 QPushButton，
# 完全规避 Qt 原生箭头在横排主题下点击热区错位的问题。
# ============================================================

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QLineEdit, QSizePolicy
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QIntValidator


class IntSpinWidget(QWidget):
    """
    QSpinBox 替代品，布局：

        ┌──────────────┬───┐
        │     数字      │ ▲ │
        │              ├───┤
        │              │ ▼ │
        └──────────────┴───┘

    完全使用 QPushButton 实现加减，避免 Qt 原生 QSpinBox
    在某些平台/主题下箭头按钮点击热区错位的问题。

    API 兼容 QSpinBox 常用接口：
        value(), setValue(), setRange(), setMinimum(), setMaximum(),
        setSingleStep(), setToolTip()
    信号: valueChanged(int)
    """

    valueChanged = Signal(int)

    # 右侧上下两个小箭头按钮的样式
    _ARROW_STYLE = (
        "QPushButton {"
        "  background: #dfe6e9;"
        "  border: 1px solid #b2bec3;"
        "  min-width: 20px; max-width: 20px;"
        "  font-size: 9px;"
        "  color: #2d3436;"
        "  padding: 0px;"
        "  margin: 0px;"
        "}"
        "QPushButton:hover  { background: #b2bec3; }"
        "QPushButton:pressed{ background: #95a5a6; }"
        "QPushButton:disabled{ background: #ecf0f1; color: #b2bec3; }"
    )

    _EDIT_STYLE = (
        "QLineEdit {"
        "  border: 1px solid #b2bec3;"
        "  border-right: none;"          # 右边框由按钮列承接
        "  border-radius: 0px;"
        "  border-top-left-radius: 4px;"
        "  border-bottom-left-radius: 4px;"
        "  padding: 2px 6px;"
        "  background: #ffffff;"
        "  color: #2d3436;"
        "}"
        "QLineEdit:focus { border: 1px solid #0984e3; border-right: none; }"
        "QLineEdit:disabled { background: #ecf0f1; color: #b2bec3; }"
    )

    def __init__(self, minimum=0, maximum=100, value=0, step=1, parent=None):
        super().__init__(parent)
        self._min = minimum
        self._max = maximum
        self._step = step
        self._value = max(minimum, min(maximum, value))

        # 外层横向布局：[输入框] [按钮列]
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # 数字输入框
        self._edit = QLineEdit(str(self._value))
        self._edit.setAlignment(Qt.AlignCenter)
        self._edit.setStyleSheet(self._EDIT_STYLE)
        self._edit.setValidator(QIntValidator(minimum, maximum, self))
        self._edit.editingFinished.connect(self._on_edit_done)
        self._edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        outer.addWidget(self._edit, 1)

        # 右侧竖排按钮列
        btn_col = QVBoxLayout()
        btn_col.setContentsMargins(0, 0, 0, 0)
        btn_col.setSpacing(0)

        self._btn_inc = QPushButton("▲")
        self._btn_inc.setStyleSheet(
            self._ARROW_STYLE +
            "QPushButton {"
            "  border-top-right-radius: 4px;"
            "  border-bottom: none;"
            "}"
        )
        self._btn_inc.setFocusPolicy(Qt.NoFocus)
        self._btn_inc.clicked.connect(self._increment)
        self._btn_inc.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        btn_col.addWidget(self._btn_inc)

        self._btn_dec = QPushButton("▼")
        self._btn_dec.setStyleSheet(
            self._ARROW_STYLE +
            "QPushButton {"
            "  border-bottom-right-radius: 4px;"
            "}"
        )
        self._btn_dec.setFocusPolicy(Qt.NoFocus)
        self._btn_dec.clicked.connect(self._decrement)
        self._btn_dec.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        btn_col.addWidget(self._btn_dec)

        btn_container = QWidget()
        btn_container.setLayout(btn_col)
        btn_container.setStyleSheet(
            "QWidget { border: 1px solid #b2bec3; border-left: none;"
            " border-top-right-radius: 4px; border-bottom-right-radius: 4px; }"
        )
        outer.addWidget(btn_container)

        self._update_buttons()

    # ---- 公开接口 ----
    def value(self) -> int:
        return self._value

    def setValue(self, v: int):
        v = max(self._min, min(self._max, int(v)))
        if v != self._value:
            self._value = v
            self._edit.setText(str(v))
            self._update_buttons()
            self.valueChanged.emit(v)
        else:
            self._edit.setText(str(v))

    def setRange(self, minimum: int, maximum: int):
        self._min = minimum
        self._max = maximum
        self._edit.setValidator(QIntValidator(minimum, maximum, self))
        self.setValue(self._value)

    def setMinimum(self, minimum: int):
        self.setRange(minimum, self._max)

    def setMaximum(self, maximum: int):
        self.setRange(self._min, maximum)

    def setSingleStep(self, step: int):
        self._step = step

    def setEnabled(self, enabled: bool):
        super().setEnabled(enabled)
        self._btn_dec.setEnabled(enabled)
        self._btn_inc.setEnabled(enabled)
        self._edit.setEnabled(enabled)

    def setToolTip(self, tip: str):
        super().setToolTip(tip)
        self._edit.setToolTip(tip)

    # ---- 内部 ----
    def _increment(self):
        self.setValue(self._value + self._step)

    def _decrement(self):
        self.setValue(self._value - self._step)

    def _on_edit_done(self):
        text = self._edit.text().strip()
        try:
            v = int(text)
        except ValueError:
            v = self._value
        self.setValue(v)

    def _update_buttons(self):
        self._btn_inc.setEnabled(self._value < self._max)
        self._btn_dec.setEnabled(self._value > self._min)
