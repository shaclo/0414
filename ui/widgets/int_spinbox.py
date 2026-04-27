from PySide6.QtWidgets import QDoubleSpinBox

class IntSpinBox(QDoubleSpinBox):
    """用 QDoubleSpinBox 模拟整数输入，外观与其保持一致以解决某些平台默认 QSpinBox 箭头过小的问题。"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDecimals(0)
        self.setSingleStep(1.0)

    def value(self) -> int:  # type: ignore[override]
        return int(super().value())

    def setValue(self, v) -> None:
        super().setValue(float(v))

    def setRange(self, minimum, maximum) -> None:
        super().setRange(float(minimum), float(maximum))
