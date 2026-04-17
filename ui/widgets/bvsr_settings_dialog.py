# ============================================================
# ui/widgets/bvsr_settings_dialog.py
# BVSR 人格管理对话框
# 功能：查看/添加/删除/修改 人格定义，激活/停用
# ============================================================

import uuid
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QSplitter,
    QListWidget, QListWidgetItem, QPushButton, QLabel,
    QLineEdit, QComboBox, QTextEdit, QFormLayout,
    QGroupBox, QMessageBox, QCheckBox, QWidget, QScrollArea,
)
from PySide6.QtCore import Qt, QSize


CATEGORY_OPTIONS = [
    ("initiator",  "🚀 启动型 (Initiator)"),
    ("developer",  "⚙️ 推进型 (Developer)"),
    ("atmosphere", "🌫️ 氛围型 (Atmosphere)"),
    ("finisher",   "🏁 终结型 (Finisher)"),
]
CATEGORY_KEYS  = [c[0] for c in CATEGORY_OPTIONS]
CATEGORY_LABELS = [c[1] for c in CATEGORY_OPTIONS]


class BVSRSettingsDialog(QDialog):
    """
    BVSR 人格设置对话框。
    左侧：所有人格列表（含激活复选框）
    右侧：选中人格的详情/编辑表单
    底部：添加/保存/删除 操作按钮
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        from services.persona_engine import persona_engine
        self._engine = persona_engine
        self._selected_key: str = ""

        self.setWindowTitle("⚙️ BVSR 人格系统设置")
        self.setMinimumSize(860, 600)
        self._setup_ui()
        self._refresh_list()

    # ------------------------------------------------------------------ #
    # UI 构建
    # ------------------------------------------------------------------ #
    def _setup_ui(self):
        root = QVBoxLayout(self)

        # 顶部说明
        tip = QLabel(
            "管理 BVSR 多人格系统（Blind Variation & Selective Retention）。\n"
            "勾选人格 = 激活参与生成；每个人格独立调用 AI，生成不同视角的 Story Beat。"
        )
        tip.setWordWrap(True)
        tip.setStyleSheet("color: #636e72; font-size: 12px; padding: 4px 0;")
        root.addWidget(tip)

        splitter = QSplitter(Qt.Horizontal)

        # ---- 左侧：人格列表 ----
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 4, 0)

        lv.addWidget(QLabel("📋 人格列表 (双击选中 / 勾选启用):"))
        self._list = QListWidget()
        self._list.setAlternatingRowColors(True)
        self._list.currentItemChanged.connect(self._on_list_selection_changed)
        self._list.itemChanged.connect(self._on_item_check_changed)
        lv.addWidget(self._list)

        btn_row = QHBoxLayout()
        self._btn_new = QPushButton("➕ 新建人格")
        self._btn_new.clicked.connect(self._on_new_persona)
        btn_row.addWidget(self._btn_new)

        self._btn_delete = QPushButton("🗑 删除")
        self._btn_delete.setEnabled(False)
        self._btn_delete.setStyleSheet("color: #e74c3c;")
        self._btn_delete.clicked.connect(self._on_delete_persona)
        btn_row.addWidget(self._btn_delete)
        lv.addLayout(btn_row)

        splitter.addWidget(left)

        # ---- 右侧：编辑表单 ----
        right = QGroupBox("✏️ 人格详情")
        rv = QVBoxLayout(right)

        form = QFormLayout()

        # Key
        self._key_edit = QLineEdit()
        self._key_edit.setPlaceholderText("英文唯一标识，如 my_detective（新建时填写）")
        form.addRow("人格 Key:", self._key_edit)

        # 名称
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("显示名称，如：侦探叙述者 (Detective Narrator)")
        form.addRow("名称:", self._name_edit)

        # 类型
        self._cat_combo = QComboBox()
        self._cat_combo.addItems(CATEGORY_LABELS)
        form.addRow("类型:", self._cat_combo)
        rv.addLayout(form)

        # Identity Block
        rv.addWidget(QLabel("📝 人格身份描述 (identity_block) — 这段文字直接注入 System Prompt:"))
        self._identity_edit = QTextEdit()
        self._identity_edit.setPlaceholderText(
            "你是「xxx」。\n你的专长是……\n你偏好：……\n你排斥：……"
        )
        rv.addWidget(self._identity_edit)

        # 保存按钮
        save_row = QHBoxLayout()
        self._btn_save = QPushButton("✅ 保存修改")
        self._btn_save.setEnabled(False)
        self._btn_save.clicked.connect(self._on_save_persona)
        save_row.addWidget(self._btn_save)
        save_row.addStretch()

        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color: #27ae60; font-size: 12px;")
        save_row.addWidget(self._status_label)
        rv.addLayout(save_row)

        splitter.addWidget(right)
        splitter.setSizes([300, 560])
        root.addWidget(splitter)

        # 底部关闭
        bottom = QHBoxLayout()
        bottom.addStretch()
        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(self.accept)
        bottom.addWidget(btn_close)
        root.addLayout(bottom)

    # ------------------------------------------------------------------ #
    # 列表管理
    # ------------------------------------------------------------------ #
    def _refresh_list(self, select_key: str = ""):
        self._list.blockSignals(True)
        self._list.clear()
        personas = self._engine.get_all_personas()
        for key, p in personas.items():
            cat = p.get("category", "")
            cat_label = next((c[1] for c in CATEGORY_OPTIONS if c[0] == cat), cat)
            item = QListWidgetItem(f"{p['name']}\n  {cat_label}")
            item.setData(Qt.UserRole, key)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if self._engine.is_active(key) else Qt.Unchecked)
            self._list.addItem(item)
            if key == select_key:
                self._list.setCurrentItem(item)
        self._list.blockSignals(False)

    def _on_list_selection_changed(self, current, previous):
        if current is None:
            self._clear_form()
            self._btn_delete.setEnabled(False)
            self._btn_save.setEnabled(False)
            return
        key = current.data(Qt.UserRole)
        self._selected_key = key
        self._load_form(key)
        self._btn_delete.setEnabled(True)
        self._btn_save.setEnabled(True)

    def _on_item_check_changed(self, item: QListWidgetItem):
        key = item.data(Qt.UserRole)
        active = (item.checkState() == Qt.Checked)
        self._engine.toggle_active(key, active)

    # ------------------------------------------------------------------ #
    # 表单操作
    # ------------------------------------------------------------------ #
    def _load_form(self, key: str):
        p = self._engine.get_all_personas().get(key, {})
        self._key_edit.setText(key)
        self._key_edit.setEnabled(False)  # 已有人格不允许改 key
        self._name_edit.setText(p.get("name", ""))
        cat = p.get("category", "initiator")
        idx = CATEGORY_KEYS.index(cat) if cat in CATEGORY_KEYS else 0
        self._cat_combo.setCurrentIndex(idx)
        self._identity_edit.setPlainText(p.get("identity_block", ""))
        self._status_label.setText("")

    def _clear_form(self):
        self._selected_key = ""
        self._key_edit.setText("")
        self._key_edit.setEnabled(True)
        self._name_edit.setText("")
        self._cat_combo.setCurrentIndex(0)
        self._identity_edit.clear()
        self._status_label.setText("")

    def _on_new_persona(self):
        """新建模式：清空表单让用户填写"""
        self._list.clearSelection()
        self._clear_form()
        self._key_edit.setEnabled(True)
        self._btn_save.setEnabled(True)
        self._btn_delete.setEnabled(False)
        self._key_edit.setFocus()
        self._status_label.setText("填写右侧表单后点击「保存修改」")

    def _on_save_persona(self):
        key = self._key_edit.text().strip()
        name = self._name_edit.text().strip()
        identity = self._identity_edit.toPlainText().strip()
        cat = CATEGORY_KEYS[self._cat_combo.currentIndex()]

        if not key:
            QMessageBox.warning(self, "验证失败", "人格 Key 不能为空")
            return
        if not name:
            QMessageBox.warning(self, "验证失败", "名称不能为空")
            return
        if not identity:
            QMessageBox.warning(self, "验证失败", "人格身份描述不能为空")
            return
        # 验证 key 只含英文/数字/下划线
        import re
        if not re.match(r'^[a-zA-Z][a-zA-Z0-9_]*$', key):
            QMessageBox.warning(self, "验证失败", "Key 只能以字母开头，包含字母/数字/下划线")
            return

        try:
            if self._selected_key and self._selected_key == key:
                # 更新已有人格
                self._engine.update_persona(key, name, cat, identity)
                self._status_label.setText(f"✅ 已更新：{name}")
            else:
                # 新建人格
                self._engine.add_persona(key, name, cat, identity)
                self._selected_key = key
                self._status_label.setText(f"✅ 已添加：{name}")
            self._refresh_list(select_key=key)
        except (ValueError, KeyError) as e:
            QMessageBox.warning(self, "保存失败", str(e))

    def _on_delete_persona(self):
        if not self._selected_key:
            return
        p = self._engine.get_all_personas().get(self._selected_key, {})
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定删除人格「{p.get('name', self._selected_key)}」？",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self._engine.remove_persona(self._selected_key)
            self._selected_key = ""
            self._clear_form()
            self._btn_delete.setEnabled(False)
            self._btn_save.setEnabled(False)
            self._refresh_list()
