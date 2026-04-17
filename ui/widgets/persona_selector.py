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


class PersonaSelector(QWidget):
    """
    人格多选面板。
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
        self._group = None
        self._group_layout = None
        self._count_label = None
        self._setup_ui()

    def _get_personas(self) -> dict:
        """从 persona_engine 获取最新人格列表"""
        from services.persona_engine import persona_engine
        return persona_engine.get_all_personas()

    def _setup_ui(self):
        self._main_layout = QVBoxLayout(self)
        self._main_layout.setContentsMargins(0, 0, 0, 0)
        self._build_content()

    def _build_content(self):
        """构建/重建人格选择面板内容"""
        # 清理旧内容
        if self._group:
            self._main_layout.removeWidget(self._group)
            self._group.deleteLater()
            self._group = None

        self._checkboxes.clear()

        self._group = QGroupBox("🎭 选择参与生成的人格")
        self._group.setCheckable(True)
        self._group.setChecked(True)
        self._group.setStyleSheet(
            "QGroupBox { font-weight: bold; padding-top: 16px; }"
            "QGroupBox::indicator { width: 13px; height: 13px; }"
        )
        self._inner_widget = QWidget()
        self._group_layout = QVBoxLayout(self._inner_widget)
        self._group_layout.setContentsMargins(4, 4, 4, 4)
        self._group_layout.setSpacing(4)

        personas = self._get_personas()

        # 按类别分组
        personas_by_category = {}
        for key, persona in personas.items():
            cat = persona.get("category", "initiator")
            if cat not in personas_by_category:
                personas_by_category[cat] = []
            personas_by_category[cat].append((key, persona))

        for cat_key, cat_label in self.CATEGORY_LABELS.items():
            if cat_key not in personas_by_category:
                continue

            # 类别标签
            self._group_layout.addWidget(QLabel(f"{cat_label}:"))

            # 每行最多4个复选框，自动换行
            items = personas_by_category[cat_key]
            MAX_PER_ROW = 4
            for i in range(0, len(items), MAX_PER_ROW):
                row = QHBoxLayout()
                row.setContentsMargins(16, 0, 0, 0)
                for key, persona in items[i:i + MAX_PER_ROW]:
                    cb = QCheckBox(persona.get("name", key))
                    cb.setChecked(True)  # 默认全选
                    cb.stateChanged.connect(self._on_changed)
                    row.addWidget(cb)
                    self._checkboxes[key] = cb
                row.addStretch()
                self._group_layout.addLayout(row)

        # 全选/全不选 按钮
        btn_row = QHBoxLayout()
        btn_select_all = QPushButton("全选")
        btn_select_all.clicked.connect(lambda: self._set_all(True))
        btn_row.addWidget(btn_select_all)

        btn_deselect_all = QPushButton("全不选")
        btn_deselect_all.clicked.connect(lambda: self._set_all(False))
        btn_row.addWidget(btn_deselect_all)

        # 选中计数
        self._count_label = QLabel("")
        btn_row.addWidget(self._count_label)
        btn_row.addStretch()

        self._group_layout.addLayout(btn_row)

        # 将内容组件加入 GroupBox，并连接折叠
        outer_layout = QVBoxLayout(self._group)
        outer_layout.setContentsMargins(8, 4, 8, 8)
        outer_layout.addWidget(self._inner_widget)
        self._group.toggled.connect(self._inner_widget.setVisible)

        self._main_layout.addWidget(self._group)

        self._update_count()

    def refresh(self):
        """刷新人格列表（BVSR 设置修改后调用）"""
        # 记住当前选中的 keys
        prev_selected = self.get_selected_keys()
        self._build_content()
        # 恢复之前的选中状态（对仍存在的 key）
        if prev_selected:
            for k, cb in self._checkboxes.items():
                cb.setChecked(k in prev_selected)
            self._update_count()

    def _on_changed(self):
        self._update_count()
        self.selection_changed.emit(self.get_selected_keys())

    def _set_all(self, checked: bool):
        for cb in self._checkboxes.values():
            cb.setChecked(checked)

    def _update_count(self):
        count = len(self.get_selected_keys())
        if self._count_label:
            self._count_label.setText(f"已选: {count} 个人格")

    def get_selected_keys(self) -> List[str]:
        """获取当前选中的人格 key 列表"""
        return [k for k, cb in self._checkboxes.items() if cb.isChecked()]

    def set_selected_keys(self, keys: List[str]):
        """程序控制选中状态"""
        for k, cb in self._checkboxes.items():
            cb.setChecked(k in keys)
