# ============================================================
# ui/widgets/world_var_table.py
# 世界观变量表 (可编辑) — Phase 1 右侧使用
# ============================================================

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTableWidget, QTableWidgetItem, QPushButton,
    QHeaderView, QAbstractItemView,
)
from PySide6.QtCore import Qt, Signal


class WorldVarTable(QWidget):
    """
    世界观变量表。
    AI-Call-2 提炼后的变量展示在此，用户可编辑/添加/删除。

    信号:
        variables_changed: 变量修改时发出
    """

    variables_changed = Signal()
    COLUMNS = ["ID", "类别", "名称", "定义", "限制"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        header = QLabel("世界观变量表")
        header.setStyleSheet("font-weight: bold; font-size: 13px; padding: 4px 0;")
        layout.addWidget(header)

        self._table = QTableWidget()
        self._table.setColumnCount(len(self.COLUMNS))
        self._table.setHorizontalHeaderLabels(self.COLUMNS)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.cellChanged.connect(lambda: self.variables_changed.emit())
        layout.addWidget(self._table)

        btn_row = QHBoxLayout()
        btn_add = QPushButton("+ 添加变量")
        btn_add.clicked.connect(self._add_empty_row)
        btn_row.addWidget(btn_add)

        btn_delete = QPushButton("- 删除选中")
        btn_delete.clicked.connect(self._delete_selected)
        btn_row.addWidget(btn_delete)

        btn_row.addStretch()

        self._conflict_label = QLabel("")
        self._conflict_label.setWordWrap(True)
        self._conflict_label.setStyleSheet("color: #c0392b; font-size: 11px;")
        layout.addLayout(btn_row)
        layout.addWidget(self._conflict_label)

    def set_variables(self, variables: list, conflicts: list = None):
        """
        填充变量表（AI-Call-2 返回后调用）。

        Args:
            variables: [{"id":"var_001","category":"...","name":"...","definition":"...","constraints":"..."}]
            conflicts: [{"var_ids":[...],"description":"..."}]
        """
        self._table.blockSignals(True)
        self._table.setRowCount(len(variables))
        for row, var in enumerate(variables):
            self._table.setItem(row, 0, QTableWidgetItem(var.get("id", "")))
            self._table.setItem(row, 1, QTableWidgetItem(var.get("category", "")))
            self._table.setItem(row, 2, QTableWidgetItem(var.get("name", "")))
            self._table.setItem(row, 3, QTableWidgetItem(var.get("definition", "")))
            self._table.setItem(row, 4, QTableWidgetItem(var.get("constraints", "")))
        self._table.blockSignals(False)

        if conflicts:
            lines = [f"[冲突] {c['description']} ({' <-> '.join(c.get('var_ids',[]))})"
                     for c in conflicts]
            self._conflict_label.setText("\n".join(lines))
        else:
            self._conflict_label.setText("")

    def get_variables(self) -> list:
        variables = []
        for row in range(self._table.rowCount()):
            var = {
                "id":          self._cell(row, 0),
                "category":    self._cell(row, 1),
                "name":        self._cell(row, 2),
                "definition":  self._cell(row, 3),
                "constraints": self._cell(row, 4),
            }
            if var["name"]:
                variables.append(var)
        return variables

    def _cell(self, row: int, col: int) -> str:
        item = self._table.item(row, col)
        return item.text().strip() if item else ""

    def _add_empty_row(self):
        row = self._table.rowCount()
        self._table.insertRow(row)
        self._table.setItem(row, 0, QTableWidgetItem(f"var_{row + 1:03d}"))

    def _delete_selected(self):
        rows = sorted(
            set(idx.row() for idx in self._table.selectedIndexes()),
            reverse=True,
        )
        for row in rows:
            self._table.removeRow(row)
        if rows:
            self.variables_changed.emit()
