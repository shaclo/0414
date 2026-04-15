# ============================================================
# ui/widgets/character_relation_panel.py
# 人物关系管理组件 — Phase 2 下方使用
# 支持添加/删除/编辑角色间关系，列宽可拖动
# ============================================================

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTableWidget, QTableWidgetItem, QPushButton,
    QHeaderView, QComboBox, QLineEdit, QTextEdit, QDialog,
    QDialogButtonBox, QFormLayout, QMessageBox,
)
from PySide6.QtCore import Qt, Signal
from typing import List


class RelationDialog(QDialog):
    """添加/编辑关系的对话框"""

    def __init__(self, characters: list, parent=None, initial: dict = None):
        """
        Args:
            characters: [{char_id, name}, ...]
            initial: 如果是编辑模式，传入已有关系 dict
        """
        super().__init__(parent)
        self._is_edit = initial is not None
        self.setWindowTitle("编辑人物关系" if self._is_edit else "添加人物关系")
        self.setMinimumWidth(480)
        self._characters = characters

        layout = QVBoxLayout(self)
        form = QFormLayout()

        # 起点角色
        self._from_combo = QComboBox()
        for c in characters:
            self._from_combo.addItem(c["name"], c["char_id"])
        if initial:
            from_idx = self._find_char_index(initial.get("from_char_id", ""))
            self._from_combo.setCurrentIndex(from_idx)
        form.addRow("从：", self._from_combo)

        # 关系类型
        self._relation_edit = QLineEdit()
        self._relation_edit.setPlaceholderText(
            "如：父子/敌对、主从/信任、青梅竹马/暧昧……"
        )
        if initial:
            self._relation_edit.setText(initial.get("relation_type", ""))
        form.addRow("关系：", self._relation_edit)

        # 终点角色
        self._to_combo = QComboBox()
        for c in characters:
            self._to_combo.addItem(c["name"], c["char_id"])
        if initial:
            to_idx = self._find_char_index(initial.get("to_char_id", ""))
            self._to_combo.setCurrentIndex(to_idx)
        elif len(characters) > 1:
            self._to_combo.setCurrentIndex(1)
        form.addRow("到：", self._to_combo)

        # 描述（多行文本框，约 5 行高度）
        self._desc_edit = QTextEdit()
        self._desc_edit.setPlaceholderText("关系补充说明（可选）")
        self._desc_edit.setMinimumHeight(100)
        self._desc_edit.setMaximumHeight(140)
        if initial:
            self._desc_edit.setPlainText(initial.get("description", ""))
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

    def _find_char_index(self, char_id: str) -> int:
        """
        根据 char_id 在角色列表中查找索引。
        支持多种匹配策略：
          1. 精确匹配 char_id
          2. char_NNN 格式 → 按序号匹配
          3. 按名称匹配（char_id 可能就是人名）
        找不到默认返回 0。
        """
        if not char_id:
            return 0

        # 策略 1：精确匹配 char_id
        for i, c in enumerate(self._characters):
            if c["char_id"] == char_id:
                return i

        # 策略 2：char_NNN 格式 → 尝试取序号作为索引
        if char_id.startswith("char_"):
            try:
                idx = int(char_id.split("_")[1]) - 1  # char_001 → index 0
                if 0 <= idx < len(self._characters):
                    return idx
            except (ValueError, IndexError):
                pass

        # 策略 3：按名称匹配
        for i, c in enumerate(self._characters):
            if c["name"] == char_id:
                return i

        return 0

    def get_relation(self) -> dict:
        return {
            "from_char_id":  self._from_combo.currentData(),
            "to_char_id":    self._to_combo.currentData(),
            "relation_type": self._relation_edit.text().strip(),
            "description":   self._desc_edit.toPlainText().strip(),
        }


class CharacterRelationPanel(QWidget):
    """
    人物关系管理面板。
    表格形式展示关系列表，支持添加/删除/双击编辑。
    列宽可自由拖动。

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

        # 列宽可自由拖动
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(True)
        # 设置合理的默认列宽
        self._table.setColumnWidth(0, 120)  # 起点角色
        self._table.setColumnWidth(1, 140)  # 关系类型
        self._table.setColumnWidth(2, 120)  # 终点角色
        # 第4列（说明）自动拉伸填满

        self._table.setMaximumHeight(180)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)

        # 双击编辑
        self._table.doubleClicked.connect(self._on_double_click)

        layout.addWidget(self._table)

        tip = QLabel("💡 双击某行可编辑关系 | 拖动列头边缘可调整列宽")
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
    def _get_char_name(self, char_id: str) -> str:
        """
        根据 char_id 获取人名。
        支持多种匹配策略：精确 → 序号 → 名称匹配。
        """
        if not char_id:
            return "（未知）"

        # 策略 1：精确匹配 char_id
        for c in self._characters:
            if c["char_id"] == char_id:
                return c["name"]

        # 策略 2：char_NNN → 按序号匹配（char_001 = 第1个角色）
        if char_id.startswith("char_"):
            try:
                idx = int(char_id.split("_")[1]) - 1
                if 0 <= idx < len(self._characters):
                    return self._characters[idx]["name"]
            except (ValueError, IndexError):
                pass

        # 策略 3：char_id 可能本身就是人名
        for c in self._characters:
            if c["name"] == char_id:
                return c["name"]

        return char_id  # 最终 fallback

    def _refresh_table(self):
        self._table.setRowCount(len(self._relations))
        for row, rel in enumerate(self._relations):
            from_name = self._get_char_name(rel.get("from_char_id", ""))
            to_name = self._get_char_name(rel.get("to_char_id", ""))

            item_from = QTableWidgetItem(from_name)
            item_from.setToolTip(f"ID: {rel.get('from_char_id', '')}")
            self._table.setItem(row, 0, item_from)

            self._table.setItem(row, 1, QTableWidgetItem(rel.get("relation_type", "")))

            item_to = QTableWidgetItem(to_name)
            item_to.setToolTip(f"ID: {rel.get('to_char_id', '')}")
            self._table.setItem(row, 2, item_to)

            self._table.setItem(row, 3, QTableWidgetItem(rel.get("description", "")))

    def _on_add(self):
        if len(self._characters) < 2:
            QMessageBox.warning(self, "提示", "至少需要两个角色才能添加关系。")
            return
        dlg = RelationDialog(self._characters, self)
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

    def _on_double_click(self, index):
        """双击行 → 弹出编辑对话框"""
        row = index.row()
        if row < 0 or row >= len(self._relations):
            return
        if len(self._characters) < 2:
            return

        current_rel = self._relations[row]
        dlg = RelationDialog(self._characters, self, initial=current_rel)
        if dlg.exec() == QDialog.Accepted:
            new_rel = dlg.get_relation()
            if not new_rel["relation_type"]:
                QMessageBox.warning(self, "提示", "请填写关系类型。")
                return
            if new_rel["from_char_id"] == new_rel["to_char_id"]:
                QMessageBox.warning(self, "提示", "起点和终点不能是同一个角色。")
                return
            self._relations[row] = new_rel
            self._refresh_table()
            self.relations_changed.emit()
