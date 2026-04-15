# ============================================================
# ui/widgets/persona_selector.py
# 人格多选面板
# 用于 Phase 3：让用户选择参与盲视变异的人格
# ============================================================

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QCheckBox, QLabel,
    QGroupBox, QPushButton,
)
from PySide6.QtCore import Signal
from typing import List, Dict

from env import PERSONA_DEFINITIONS


class PersonaSelector(QWidget):
    """
    10 人格多选面板。
    按类别（启动型/推进型/氛围型/终结型）分组展示，
    用户通过复选框选择参与生成的人格。

    信号:
        selection_changed: 选择变化时发出，参数为选中的 key 列表
    """

    selection_changed = Signal(list)

    # 类别显示顺序和中文标签
    CATEGORY_LABELS = {
        "initiator": "启动型 (Initiators)",
        "developer": "推进型 (Developers)",
        "atmosphere": "氛围型 (Atmosphere)",
        "finisher": "终结型 (Finishers)",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._checkboxes: Dict[str, QCheckBox] = {}
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        group = QGroupBox("🎭 选择参与生成的人格")
        group_layout = QVBoxLayout(group)

        # 按类别分组
        personas_by_category = {}
        for key, persona in PERSONA_DEFINITIONS.items():
            cat = persona["category"]
            if cat not in personas_by_category:
                personas_by_category[cat] = []
            personas_by_category[cat].append((key, persona))

        for cat_key, cat_label in self.CATEGORY_LABELS.items():
            if cat_key not in personas_by_category:
                continue

            row = QHBoxLayout()
            row.addWidget(QLabel(f"{cat_label}:"))

            for key, persona in personas_by_category[cat_key]:
                cb = QCheckBox(persona["name"])
                cb.setChecked(True)  # 默认全选
                cb.stateChanged.connect(self._on_changed)
                row.addWidget(cb)
                self._checkboxes[key] = cb

            row.addStretch()
            group_layout.addLayout(row)

        # 全选/全不选 按钮
        btn_row = QHBoxLayout()
        btn_select_all = QPushButton("全选")
        btn_select_all.clicked.connect(lambda: self._set_all(True))
        btn_row.addWidget(btn_select_all)

        btn_deselect_all = QPushButton("全不选")
        btn_deselect_all.clicked.connect(lambda: self._set_all(False))
        btn_row.addWidget(btn_deselect_all)

        # 选中计数
        self._count_label = QLabel("已选: 10 个人格")
        btn_row.addWidget(self._count_label)
        btn_row.addStretch()

        group_layout.addLayout(btn_row)
        layout.addWidget(group)

        self._update_count()

    def _on_changed(self):
        self._update_count()
        self.selection_changed.emit(self.get_selected_keys())

    def _set_all(self, checked: bool):
        for cb in self._checkboxes.values():
            cb.setChecked(checked)

    def _update_count(self):
        count = len(self.get_selected_keys())
        self._count_label.setText(f"已选: {count} 个人格")

    def get_selected_keys(self) -> List[str]:
        """获取当前选中的人格 key 列表"""
        return [k for k, cb in self._checkboxes.items() if cb.isChecked()]

    def set_selected_keys(self, keys: List[str]):
        """程序控制选中状态"""
        for k, cb in self._checkboxes.items():
            cb.setChecked(k in keys)
