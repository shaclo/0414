# ============================================================
# ui/widgets/prompt_template_dialog.py
# 扩写设置对话框 — 爽感公式 & 钩子公式 管理
# UI 风格参考 bvsr_settings_dialog.py
# ============================================================

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QSplitter, QTabWidget,
    QListWidget, QListWidgetItem, QPushButton, QLabel,
    QLineEdit, QComboBox, QTextEdit, QFormLayout,
    QGroupBox, QMessageBox, QWidget,
)
from PySide6.QtCore import Qt

from config.prompt_templates import (
    prompt_template_manager, SatisfactionTemplate, HookTemplate,
)

LEVEL_OPTIONS = [
    ("small",  "小爽"),
    ("medium", "中爽"),
    ("big",    "大爽"),
]
LEVEL_KEYS = [x[0] for x in LEVEL_OPTIONS]
LEVEL_LABELS = [x[1] for x in LEVEL_OPTIONS]


class _TemplateTab(QWidget):
    """单个 Tab 的基类逻辑 — 左列表 + 右编辑面板"""

    def __init__(self, kind: str, parent=None):
        super().__init__(parent)
        self._kind = kind  # "satisfaction" | "hook"
        self._selected_idx: int = -1
        self._mgr = prompt_template_manager
        self._setup_ui()
        self._refresh_list()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        splitter = QSplitter(Qt.Horizontal)

        # ---- 左侧列表 ----
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 4, 0)
        lv.addWidget(QLabel("公式列表 (勾选=启用):"))
        self._list = QListWidget()
        self._list.setAlternatingRowColors(True)
        self._list.currentItemChanged.connect(self._on_selection)
        self._list.itemChanged.connect(self._on_check)
        lv.addWidget(self._list)

        btn_row = QHBoxLayout()
        btn_new = QPushButton("新建")
        btn_new.clicked.connect(self._on_new)
        btn_row.addWidget(btn_new)
        self._btn_del = QPushButton("删除")
        self._btn_del.setEnabled(False)
        self._btn_del.setStyleSheet("color: #e74c3c;")
        self._btn_del.clicked.connect(self._on_delete)
        btn_row.addWidget(self._btn_del)
        lv.addLayout(btn_row)
        splitter.addWidget(left)

        # ---- 右侧编辑 ----
        right = QGroupBox("公式详情")
        rv = QVBoxLayout(right)
        form = QFormLayout()

        self._id_edit = QLineEdit()
        self._id_edit.setPlaceholderText("英文标识如 face_slap")
        form.addRow("ID:", self._id_edit)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("显示名称如 打脸反杀")
        form.addRow("名称:", self._name_edit)

        if self._kind == "satisfaction":
            self._level_combo = QComboBox()
            self._level_combo.addItems(LEVEL_LABELS)
            form.addRow("爽感等级:", self._level_combo)

        rv.addLayout(form)

        rv.addWidget(QLabel("完整 Prompt 文本 (含公式+示例+禁忌):"))
        self._prompt_edit = QTextEdit()
        self._prompt_edit.setPlaceholderText(
            "**情绪弧线**: ...\n**四步行文**:\n  第1步...\n**禁忌**: ..."
        )
        rv.addWidget(self._prompt_edit)

        save_row = QHBoxLayout()
        self._btn_save = QPushButton("保存修改")
        self._btn_save.setEnabled(False)
        self._btn_save.clicked.connect(self._on_save)
        save_row.addWidget(self._btn_save)

        btn_preview = QPushButton("模拟抽样预览")
        btn_preview.clicked.connect(self._on_preview)
        save_row.addWidget(btn_preview)

        save_row.addStretch()
        self._status = QLabel("")
        self._status.setStyleSheet("color:#27ae60;")
        save_row.addWidget(self._status)
        rv.addLayout(save_row)

        splitter.addWidget(right)
        splitter.setSizes([280, 560])
        root.addWidget(splitter)

    # ---- 数据访问 ----
    def _items(self):
        if self._kind == "satisfaction":
            return self._mgr.get_satisfactions()
        return self._mgr.get_hooks()

    # ---- 列表 ----
    def _refresh_list(self, select_idx=-1):
        self._list.blockSignals(True)
        self._list.clear()
        for i, t in enumerate(self._items()):
            if self._kind == "satisfaction":
                lbl = {"small": "小爽", "medium": "中爽", "big": "大爽"}.get(t.level, t.level)
                item = QListWidgetItem(f"{t.name}\n  [{lbl}] {t.id}")
            else:
                item = QListWidgetItem(f"{t.name}\n  {t.id}")
            item.setData(Qt.UserRole, i)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if t.enabled else Qt.Unchecked)
            self._list.addItem(item)
            if i == select_idx:
                self._list.setCurrentItem(item)
        self._list.blockSignals(False)

    def _on_selection(self, current, _prev):
        if current is None:
            self._clear_form()
            return
        idx = current.data(Qt.UserRole)
        self._selected_idx = idx
        self._load_form(idx)
        self._btn_del.setEnabled(True)
        self._btn_save.setEnabled(True)

    def _on_check(self, item):
        idx = item.data(Qt.UserRole)
        enabled = (item.checkState() == Qt.Checked)
        if self._kind == "satisfaction":
            self._mgr.toggle_satisfaction(idx, enabled)
        else:
            self._mgr.toggle_hook(idx, enabled)

    # ---- 表单 ----
    def _load_form(self, idx):
        t = self._items()[idx]
        self._id_edit.setText(t.id)
        self._id_edit.setEnabled(False)
        self._name_edit.setText(t.name)
        self._prompt_edit.setPlainText(t.prompt_text)
        if self._kind == "satisfaction":
            li = LEVEL_KEYS.index(t.level) if t.level in LEVEL_KEYS else 0
            self._level_combo.setCurrentIndex(li)
        self._status.setText("")

    def _clear_form(self):
        self._selected_idx = -1
        self._id_edit.setText("")
        self._id_edit.setEnabled(True)
        self._name_edit.setText("")
        self._prompt_edit.clear()
        if self._kind == "satisfaction":
            self._level_combo.setCurrentIndex(0)
        self._btn_del.setEnabled(False)
        self._btn_save.setEnabled(False)
        self._status.setText("")

    def _on_new(self):
        self._list.clearSelection()
        self._clear_form()
        self._id_edit.setEnabled(True)
        self._btn_save.setEnabled(True)
        self._id_edit.setFocus()
        self._status.setText("填写后点击保存")

    def _on_save(self):
        tid = self._id_edit.text().strip()
        name = self._name_edit.text().strip()
        prompt = self._prompt_edit.toPlainText().strip()
        if not tid or not name or not prompt:
            QMessageBox.warning(self, "验证失败", "ID、名称、Prompt 均不能为空")
            return
        import re
        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', tid):
            QMessageBox.warning(self, "验证失败", "ID 只能含字母/数字/下划线")
            return

        if self._kind == "satisfaction":
            level = LEVEL_KEYS[self._level_combo.currentIndex()]
            t = SatisfactionTemplate(id=tid, name=name, level=level, prompt_text=prompt)
            if self._selected_idx >= 0:
                self._mgr.update_satisfaction(self._selected_idx, t)
                self._status.setText(f"已更新: {name}")
            else:
                self._mgr.add_satisfaction(t)
                self._status.setText(f"已添加: {name}")
        else:
            t = HookTemplate(id=tid, name=name, prompt_text=prompt)
            if self._selected_idx >= 0:
                self._mgr.update_hook(self._selected_idx, t)
                self._status.setText(f"已更新: {name}")
            else:
                self._mgr.add_hook(t)
                self._status.setText(f"已添加: {name}")

        self._refresh_list(select_idx=self._selected_idx if self._selected_idx >= 0 else len(self._items())-1)

    def _on_delete(self):
        if self._selected_idx < 0:
            return
        t = self._items()[self._selected_idx]
        if QMessageBox.question(self, "确认删除", f"删除公式「{t.name}」？") != QMessageBox.Yes:
            return
        if self._kind == "satisfaction":
            self._mgr.remove_satisfaction(self._selected_idx)
        else:
            self._mgr.remove_hook(self._selected_idx)
        self._clear_form()
        self._refresh_list()

    def _on_preview(self):
        if self._kind == "satisfaction":
            text = self._mgr.sample_satisfaction_prompt(3)
        else:
            text = self._mgr.sample_hook_prompt(2)
        dlg = QDialog(self)
        dlg.setWindowTitle("模拟抽样预览")
        dlg.resize(700, 500)
        lv = QVBoxLayout(dlg)
        lv.addWidget(QLabel("以下是随机抽取的候选（每次点击结果不同）:"))
        te = QTextEdit()
        te.setReadOnly(True)
        te.setPlainText(text if text else "(没有启用的公式)")
        lv.addWidget(te)
        btn = QPushButton("关闭")
        btn.clicked.connect(dlg.accept)
        lv.addWidget(btn)
        dlg.exec()


class PromptTemplateDialog(QDialog):
    """扩写设置对话框 — 系统菜单入口"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("扩写设置 — 爽感公式 & 钩子公式")
        self.setMinimumSize(900, 640)

        root = QVBoxLayout(self)

        tip = QLabel(
            "管理爽感公式和钩子公式。勾选 = 启用（参与随机抽样注入到 Prompt）。\n"
            "每次生成时，系统从启用的公式池中随机抽 2-3 个候选，让 AI 选择最有冲击力的来写。"
        )
        tip.setWordWrap(True)
        tip.setStyleSheet("color:#636e72;padding:4px 0;")
        root.addWidget(tip)

        tabs = QTabWidget()
        tabs.addTab(_TemplateTab("satisfaction"), "爽感公式")
        tabs.addTab(_TemplateTab("hook"), "钩子公式")
        root.addWidget(tabs)

        bottom = QHBoxLayout()
        bottom.addStretch()
        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(self.accept)
        bottom.addWidget(btn_close)
        root.addLayout(bottom)
