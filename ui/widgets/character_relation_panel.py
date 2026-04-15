# ============================================================
# ui/widgets/character_relation_panel.py
# 人物关系管理组件 — Phase 2 下方使用
# 支持添加/删除角色间关系的简单列表
# ============================================================

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTableWidget, QTableWidgetItem, QPushButton,
    QHeaderView, QComboBox, QLineEdit, QDialog,
    QDialogButtonBox, QFormLayout, QMessageBox,
)
from PySide6.QtCore import Qt, Signal
from typing import List


class AddRelationDialog(QDialog):
    """添加关系的对话框"""

    def __init__(self, characters: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("添加人物关系")
        self.setMinimumWidth(420)
        self._characters = characters  # list of {char_id, name}

        layout = QVBoxLayout(self)
        form = QFormLayout()

        # 起点角色
        self._from_combo = QComboBox()
        for c in characters:
            self._from_combo.addItem(c["name"], c["char_id"])
        form.addRow("从：", self._from_combo)

        # 关系类型
        self._relation_edit = QLineEdit()
        self._relation_edit.setPlaceholderText(
            "如：父子/敌对、主从/信任、青梅竹马/暧昧……"
        )
        form.addRow("关系：", self._relation_edit)

        # 终点角色
        self._to_combo = QComboBox()
        for c in characters:
            self._to_combo.addItem(c["name"], c["char_id"])
        if len(characters) > 1:
            self._to_combo.setCurrentIndex(1)
        form.addRow("到：", self._to_combo)

        # 描述
        self._desc_edit = QLineEdit()
        self._desc_edit.setPlaceholderText("关系补充说明（可选）")
        form.addRow("说明：", self._desc_edit)

        layout.addLayout(form)

        tip = QLabel("关系默认单向。若需双向（如：互相信任），请添加两条关系。")
        tip.setStyleSheet("color: #7f8c8d; font-size: 11px;")
        tip.setWordWrap(True)
        layout.addWidget(tip)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def get_relation(self) -> dict:
        return {
            "from_char_id":  self._from_combo.currentData(),
            "to_char_id":    self._to_combo.currentData(),
            "relation_type": self._relation_edit.text().strip(),
            "description":   self._desc_edit.text().strip(),
        }


class CharacterRelationPanel(QWidget):
    """
    人物关系管理面板。
    表格形式展示关系列表，支持添加/删除。

    信号:
        relations_changed: 关系变化时发出
    """

    relations_changed = Signal()

    COLUMNS = ["起点角色", "关系类型", "终点角色", "说明"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._relations: List[dict] = []
        self._characters: List[dict] = []
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        header_row = QHBoxLayout()
        header_row.addWidget(QLabel("🔗 人物关系"))

        btn_add = QPushButton("+ 添加关系")
        btn_add.clicked.connect(self._on_add)
        header_row.addWidget(btn_add)

        btn_del = QPushButton("- 删除选中")
        btn_del.clicked.connect(self._on_delete)
        header_row.addWidget(btn_del)

        header_row.addStretch()
        layout.addLayout(header_row)

        self._table = QTableWidget(0, len(self.COLUMNS))
        self._table.setHorizontalHeaderLabels(self.COLUMNS)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self._table.setMaximumHeight(160)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        layout.addWidget(self._table)

        tip = QLabel("💡 人物关系将帮助 AI 理解角色互动逻辑，提高剧情逻辑性")
        tip.setStyleSheet("color: #7f8c8d; font-size: 11px;")
        layout.addWidget(tip)

    # ------------------------------------------------------------------ #
    # 公开接口
    # ------------------------------------------------------------------ #
    def set_characters(self, characters: list):
        """同步角色列表（当角色增删时调用）"""
        self._characters = [{"char_id": c.get("char_id", ""), "name": c.get("name", "")}
                            for c in characters if c.get("name")]

    def set_relations(self, relations: list):
        """从 dict 列表加载关系"""
        self._relations = list(relations)
        self._refresh_table()

    def get_relations(self) -> list:
        return list(self._relations)

    # ------------------------------------------------------------------ #
    # 内部
    # ------------------------------------------------------------------ #
    def _refresh_table(self):
        self._table.setRowCount(len(self._relations))
        char_name_map = {c["char_id"]: c["name"] for c in self._characters}

        for row, rel in enumerate(self._relations):
            from_name = char_name_map.get(rel.get("from_char_id", ""), rel.get("from_char_id", ""))
            to_name   = char_name_map.get(rel.get("to_char_id", ""), rel.get("to_char_id", ""))
            self._table.setItem(row, 0, QTableWidgetItem(from_name))
            self._table.setItem(row, 1, QTableWidgetItem(rel.get("relation_type", "")))
            self._table.setItem(row, 2, QTableWidgetItem(to_name))
            self._table.setItem(row, 3, QTableWidgetItem(rel.get("description", "")))

    def _on_add(self):
        if len(self._characters) < 2:
            QMessageBox.warning(self, "提示", "至少需要两个角色才能添加关系。")
            return
        dlg = AddRelationDialog(self._characters, self)
        if dlg.exec() == QDialog.Accepted:
            rel = dlg.get_relation()
            if not rel["relation_type"]:
                QMessageBox.warning(self, "提示", "请填写关系类型。")
                return
            if rel["from_char_id"] == rel["to_char_id"]:
                QMessageBox.warning(self, "提示", "起点和终点不能是同一个角色。")
                return
            self._relations.append(rel)
            self._refresh_table()
            self.relations_changed.emit()

    def _on_delete(self):
        rows = sorted(
            set(idx.row() for idx in self._table.selectedIndexes()),
            reverse=True,
        )
        for row in rows:
            del self._relations[row]
        self._refresh_table()
        if rows:
            self.relations_changed.emit()
