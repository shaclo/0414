# ============================================================
# ui/widgets/answer_strategy_dialog.py
# ============================================================

import re
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QSplitter,
    QListWidget, QListWidgetItem, QPushButton, QLabel,
    QLineEdit, QTextEdit, QFormLayout, QGroupBox, QWidget,
    QMessageBox,
)
from PySide6.QtCore import Qt


class AnswerStrategyDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        from services.answer_strategy_manager import answer_strategy_manager
        self._mgr = answer_strategy_manager
        self._selected_key: str = ""

        self.setWindowTitle("回答风格策略设置")
        self.setMinimumSize(900, 620)
        self.setWindowFlags(
            self.windowFlags()
            | Qt.WindowMaximizeButtonHint
            | Qt.WindowMinimizeButtonHint
        )
        self._setup_ui()
        self._refresh_list()

    def _setup_ui(self):
        root = QVBoxLayout(self)

        tip = QLabel(
            "管理 AI 自动回答的风格策略。\n"
            "每种策略通过「Prompt 指令」告知 AI 应采用何种视角和风格回答苏格拉底追问。\n"
            "修改将即时生效（下次点击「AI 自动回答」时使用新配置）。"
        )
        tip.setWordWrap(True)
        tip.setStyleSheet("color: #636e72; padding: 4px 0;")
        root.addWidget(tip)

        splitter = QSplitter(Qt.Horizontal)

        # 左侧
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 4, 0)

        lv.addWidget(QLabel("策略列表 (点击选中 / 右侧编辑):"))
        self._list = QListWidget()
        self._list.setAlternatingRowColors(True)
        self._list.currentItemChanged.connect(self._on_list_selection_changed)
        lv.addWidget(self._list)

        btn_row = QHBoxLayout()
        self._btn_new = QPushButton("新建策略")
        self._btn_new.clicked.connect(self._on_new)
        btn_row.addWidget(self._btn_new)

        self._btn_delete = QPushButton("删除")
        self._btn_delete.setEnabled(False)
        self._btn_delete.setStyleSheet("color: #e74c3c;")
        self._btn_delete.clicked.connect(self._on_delete)
        btn_row.addWidget(self._btn_delete)

        self._btn_reset = QPushButton("恢复默认")
        self._btn_reset.setToolTip("恢复为内置的 5 种默认风格策略（自定义修改将丢失）")
        self._btn_reset.clicked.connect(self._on_reset)
        btn_row.addWidget(self._btn_reset)
        lv.addLayout(btn_row)

        splitter.addWidget(left)

        # 右侧
        right = QGroupBox("策略详情")
        rv = QVBoxLayout(right)

        form = QFormLayout()

        self._key_edit = QLineEdit()
        self._key_edit.setPlaceholderText("英文唯一标识，如 humorous（新建时填写）")
        form.addRow("策略 Key:", self._key_edit)

        self._label_edit = QLineEdit()
        self._label_edit.setPlaceholderText("显示标签，如：幽默诙谐")
        form.addRow("显示标签:", self._label_edit)

        rv.addLayout(form)

        rv.addWidget(QLabel("Prompt 指令 — 完整文本，直接注入 System Prompt 的风格要求部分："))
        self._instruction_edit = QTextEdit()
        self._instruction_edit.setPlaceholderText(
            "请以…视角回答，……\n答案应……\n避免……"
        )
        rv.addWidget(self._instruction_edit, 1)

        save_row = QHBoxLayout()
        self._btn_save = QPushButton("保存修改")
        self._btn_save.setEnabled(False)
        self._btn_save.setStyleSheet(
            "QPushButton{background:#3498db;color:white;font-weight:bold;"
            "border-radius:4px;border:none;padding:6px 16px;}"
            "QPushButton:hover{background:#2980b9;}"
            "QPushButton:disabled{background:#bdc3c7;color:#888;}"
        )
        self._btn_save.clicked.connect(self._on_save)
        save_row.addWidget(self._btn_save)
        save_row.addStretch()

        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color: #27ae60; font-weight: bold;")
        save_row.addWidget(self._status_label)
        rv.addLayout(save_row)

        splitter.addWidget(right)
        splitter.setSizes([280, 620])
        root.addWidget(splitter, 1)

        bottom = QHBoxLayout()
        bottom.addStretch()
        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(self.accept)
        bottom.addWidget(btn_close)
        root.addLayout(bottom)

    def _refresh_list(self, select_key: str = ""):
        self._list.blockSignals(True)
        self._list.clear()
        for key, info in self._mgr.get_all().items():
            item = QListWidgetItem(info["label"])
            item.setData(Qt.UserRole, key)
            self._list.addItem(item)
            if key == select_key:
                self._list.setCurrentItem(item)
        self._list.blockSignals(False)

        if not select_key and self._list.count() > 0:
            self._list.setCurrentRow(0)

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

    def _load_form(self, key: str):
        info = self._mgr.get(key)
        self._key_edit.setText(key)
        self._key_edit.setEnabled(False)
        self._label_edit.setText(info.get("label", ""))
        self._instruction_edit.setPlainText(info.get("instruction", ""))
        self._status_label.setText("")

    def _clear_form(self):
        self._selected_key = ""
        self._key_edit.setText("")
        self._key_edit.setEnabled(True)
        self._label_edit.setText("")
        self._instruction_edit.clear()
        self._status_label.setText("")

    def _on_new(self):
        self._list.clearSelection()
        self._clear_form()
        self._key_edit.setEnabled(True)
        self._btn_save.setEnabled(True)
        self._btn_delete.setEnabled(False)
        self._key_edit.setFocus()
        self._status_label.setText("填写右侧表单后点击「保存修改」")

    def _on_save(self):
        key = self._key_edit.text().strip()
        label = self._label_edit.text().strip()
        instruction = self._instruction_edit.toPlainText().strip()

        if not key:
            QMessageBox.warning(self, "验证失败", "策略 Key 不能为空")
            return
        if not label:
            QMessageBox.warning(self, "验证失败", "显示标签不能为空")
            return
        if not instruction:
            QMessageBox.warning(self, "验证失败", "Prompt 指令不能为空")
            return

        if not re.match(r'^[a-zA-Z][a-zA-Z0-9_]*$', key):
            QMessageBox.warning(self, "验证失败", "Key 只能以字母开头，包含字母/数字/下划线")
            return

        try:
            self._mgr.update(key, label, instruction)
            self._selected_key = key
            self._status_label.setText(f"已保存：{label}")
            self._refresh_list(select_key=key)
        except ValueError as e:
            QMessageBox.warning(self, "保存失败", str(e))

    def _on_delete(self):
        if not self._selected_key:
            return
        info = self._mgr.get(self._selected_key)
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定删除策略「{info.get('label', self._selected_key)}」？",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            try:
                self._mgr.remove(self._selected_key)
            except ValueError as e:
                QMessageBox.warning(self, "无法删除", str(e))
                return
            self._selected_key = ""
            self._clear_form()
            self._btn_delete.setEnabled(False)
            self._btn_save.setEnabled(False)
            self._refresh_list()

    def _on_reset(self):
        reply = QMessageBox.question(
            self, "恢复默认",
            "确定恢复为内置的 5 种默认风格策略？\n所有自定义修改将丢失。",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self._mgr.reset_to_defaults()
            self._refresh_list()
            self._status_label.setText("已恢复默认策略")
