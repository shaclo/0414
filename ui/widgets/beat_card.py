# ============================================================
# ui/widgets/beat_card.py
# StoryBeat 卡片组件 — Phase 3 盲视变异结果展示
# ============================================================

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel,
    QRadioButton, QFrame, QSizePolicy,
)
from PySide6.QtCore import Signal


class BeatCard(QWidget):
    """
    StoryBeat 卡片。
    展示一个人格生成的 Beat 方案摘要，支持点击选中。

    信号:
        selected: 卡片被选中时发出，参数为 persona_key
    """

    selected = Signal(str)

    def __init__(self, persona_key: str, persona_name: str, beat_data: dict, parent=None):
        super().__init__(parent)
        self.persona_key = persona_key
        self.persona_name = persona_name
        self.beat_data = beat_data
        self._setup_ui()

    def _setup_ui(self):
        self.setMinimumWidth(220)
        self.setMaximumWidth(300)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)

        self._frame = QFrame(self)
        self._frame.setFrameShape(QFrame.Box)
        self._set_style(False)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        fl = QVBoxLayout(self._frame)
        fl.setContentsMargins(10, 10, 10, 10)
        fl.setSpacing(6)

        # 人格名称
        title = QLabel(self.persona_name)
        title.setStyleSheet(
            "font-weight: bold; font-size: 12px; color: #2c3e50;"
        )
        fl.addWidget(title)

        # Setting 摘要
        setting_text = self.beat_data.get("setting", "")
        if len(setting_text) > 80:
            setting_text = setting_text[:80] + "..."
        setting_label = QLabel(f"场景: {setting_text}")
        setting_label.setWordWrap(True)
        setting_label.setStyleSheet("color: #555; font-size: 11px;")
        fl.addWidget(setting_label)

        # 事件数量
        events = self.beat_data.get("causal_events", [])
        events_label = QLabel(f"事件: {len(events)} 个")
        events_label.setStyleSheet("font-size: 11px; color: #555;")
        fl.addWidget(events_label)

        # Hook 摘要
        hook_text = self.beat_data.get("hook", "")
        if len(hook_text) > 60:
            hook_text = hook_text[:60] + "..."
        if hook_text:
            hook_label = QLabel(f"钩子: {hook_text}")
            hook_label.setWordWrap(True)
            hook_label.setStyleSheet("color: #7f8c8d; font-size: 10px;")
            fl.addWidget(hook_label)

        # 创作理由
        rationale = self.beat_data.get("rationale", "")
        if rationale:
            if len(rationale) > 60:
                rationale = rationale[:60] + "..."
            rat_label = QLabel(f"依据: {rationale}")
            rat_label.setWordWrap(True)
            rat_label.setStyleSheet("color: #95a5a6; font-size: 10px; font-style: italic;")
            fl.addWidget(rat_label)

        # 选择按钮
        self._radio = QRadioButton("选择此方案")
        self._radio.toggled.connect(self._on_toggled)
        fl.addWidget(self._radio)

        outer.addWidget(self._frame)

    def _on_toggled(self, checked: bool):
        self._set_style(checked)
        if checked:
            self.selected.emit(self.persona_key)

    def _set_style(self, selected: bool):
        if selected:
            self._frame.setStyleSheet(
                "QFrame { border: 2px solid #2980b9; border-radius: 8px; "
                "background-color: #eaf4fd; }"
            )
        else:
            self._frame.setStyleSheet(
                "QFrame { border: 1px solid #dcdde1; border-radius: 8px; "
                "background-color: white; }"
            )

    def set_selected(self, selected: bool):
        self._radio.setChecked(selected)

    def is_selected(self) -> bool:
        return self._radio.isChecked()
