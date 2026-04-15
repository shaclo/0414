# ============================================================
# ui/widgets/ai_settings_panel.py
# AI 参数设置面板
# 在每次 AI 调用前展示，用户可调整温度/TopP/TopK/MaxTokens
# ============================================================

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QSlider, QSpinBox, QDoubleSpinBox, QGroupBox,
)
from PySide6.QtCore import Qt, Signal

from proxyserverconfig import (
    DEFAULT_TEMPERATURE, DEFAULT_TOP_P, DEFAULT_TOP_K, DEFAULT_MAX_TOKENS,
)


class AISettingsPanel(QWidget):
    """
    AI 调用参数设置面板。
    嵌入到每个 Phase 页面底部，用户在每次 AI 调用前可调节。

    信号:
        settings_changed: 参数变化时发出
    """

    settings_changed = Signal()

    def __init__(self, suggested_temp: float = None, parent=None):
        super().__init__(parent)
        self._suggested_temp = suggested_temp or DEFAULT_TEMPERATURE
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        group = QGroupBox("⚙️ AI 调用设置")
        group_layout = QVBoxLayout(group)

        # --- 温度 ---
        temp_row = QHBoxLayout()
        temp_row.addWidget(QLabel("温度 (Temperature):"))
        self._temp_slider = QSlider(Qt.Horizontal)
        self._temp_slider.setRange(0, 200)  # 0.00 ~ 2.00，步进 0.01
        self._temp_slider.setValue(int(self._suggested_temp * 100))
        self._temp_slider.valueChanged.connect(self._on_temp_slider_changed)
        temp_row.addWidget(self._temp_slider)
        self._temp_label = QLabel(f"{self._suggested_temp:.2f}")
        self._temp_label.setMinimumWidth(40)
        temp_row.addWidget(self._temp_label)
        group_layout.addLayout(temp_row)

        # --- Top-P ---
        topp_row = QHBoxLayout()
        topp_row.addWidget(QLabel("Top-P:"))
        self._topp_spin = QDoubleSpinBox()
        self._topp_spin.setRange(0.0, 1.0)
        self._topp_spin.setSingleStep(0.05)
        self._topp_spin.setValue(DEFAULT_TOP_P)
        self._topp_spin.valueChanged.connect(self.settings_changed)
        topp_row.addWidget(self._topp_spin)

        # --- Top-K ---
        topp_row.addWidget(QLabel("Top-K:"))
        self._topk_spin = QSpinBox()
        self._topk_spin.setRange(1, 100)
        self._topk_spin.setValue(DEFAULT_TOP_K)
        self._topk_spin.valueChanged.connect(self.settings_changed)
        topp_row.addWidget(self._topk_spin)

        # --- Max Tokens ---
        topp_row.addWidget(QLabel("Max Tokens:"))
        self._max_tokens_spin = QSpinBox()
        self._max_tokens_spin.setRange(256, 65536)
        self._max_tokens_spin.setSingleStep(512)
        self._max_tokens_spin.setValue(DEFAULT_MAX_TOKENS)
        self._max_tokens_spin.valueChanged.connect(self.settings_changed)
        topp_row.addWidget(self._max_tokens_spin)

        group_layout.addLayout(topp_row)
        layout.addWidget(group)

    def _on_temp_slider_changed(self, value):
        temp = value / 100.0
        self._temp_label.setText(f"{temp:.2f}")
        self.settings_changed.emit()

    # --- 读取当前值 ---
    def get_temperature(self) -> float:
        return self._temp_slider.value() / 100.0

    def get_top_p(self) -> float:
        return self._topp_spin.value()

    def get_top_k(self) -> int:
        return self._topk_spin.value()

    def get_max_tokens(self) -> int:
        return self._max_tokens_spin.value()

    def get_all_settings(self) -> dict:
        """返回所有参数的 dict，可直接传入 ai_service 调用"""
        return {
            "temperature": self.get_temperature(),
            "top_p": self.get_top_p(),
            "top_k": self.get_top_k(),
            "max_tokens": self.get_max_tokens(),
        }

    def set_suggested_temperature(self, temp: float):
        """设置建议温度值（切换阶段时调用）"""
        self._temp_slider.setValue(int(temp * 100))
