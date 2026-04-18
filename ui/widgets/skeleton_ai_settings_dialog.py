# ============================================================
# ui/widgets/skeleton_ai_settings_dialog.py
# 骨架 AI 辅助修改设置对话框
# 管理: 情节方向 / 结构微调 / 级联改写 Prompt 模板
# 样式参照 BVSR 人格设置对话框（左侧列表 + 右侧编辑面板）
# ============================================================

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QTextEdit, QGroupBox, QListWidget, QListWidgetItem,
    QMessageBox, QTabWidget, QWidget, QSplitter, QFormLayout,
)
from PySide6.QtCore import Qt

from env import (
    SYSTEM_PROMPT_CASCADE_HEAD_ONLY,
    SYSTEM_PROMPT_CASCADE_FULL,
)
from ui.widgets.node_detail_dialog import DRAMA_DIRECTION_OPTIONS, STRUCTURE_OPTIONS


class SkeletonAISettingsDialog(QDialog):
    """
    骨架 AI 辅助修改设置对话框。

    Tab 1/2: 情节方向/结构微调 — 左侧列表 + 右侧 Key/Label 编辑
    Tab 3: Prompt 模板 — 两个级联改写 prompt（保留结尾 / 完整改写），可编辑
    """

    def __init__(self, project_data, parent=None):
        super().__init__(parent)
        self._pd = project_data
        self.setWindowTitle("骨架 — AI 辅助修改设置")
        self.setMinimumSize(880, 600)
        self._setup_ui()
        self._load_data()

    def _setup_ui(self):
        root = QVBoxLayout(self)

        # 顶部说明
        tip = QLabel(
            "管理骨架节点「快速重生成」和「级联改写」的选项和 Prompt 模板。\n"
            "修改后点击底部「保存设置」存储到当前项目。"
        )
        tip.setWordWrap(True)
        tip.setStyleSheet("color: #636e72; font-size: 12px; padding: 4px 0;")
        root.addWidget(tip)

        tabs = QTabWidget()

        # ---- Tab 1: 情节方向 ----
        tabs.addTab(self._build_option_tab("dir"), "📌 情节方向")
        # ---- Tab 2: 结构微调 ----
        tabs.addTab(self._build_option_tab("struct"), "📌 结构微调")
        # ---- Tab 3: Prompt 模板 ----
        tabs.addTab(self._build_prompt_tab(), "📝 Prompt 模板")

        root.addWidget(tabs, 1)

        # ---- 底部按钮 ----
        bottom = QHBoxLayout()
        bottom.addStretch()
        btn_save = QPushButton("💾 保存设置")
        btn_save.setStyleSheet(
            "QPushButton{background:#27ae60;color:white;font-weight:bold;"
            "padding:6px 20px;border-radius:4px;border:none;}"
            "QPushButton:hover{background:#229954;}"
        )
        btn_save.clicked.connect(self._do_save)
        bottom.addWidget(btn_save)
        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)
        bottom.addWidget(btn_cancel)
        root.addLayout(bottom)

    # ================================================================== #
    # Tab 1/2: 左侧列表 + 右侧编辑 (BVSR 式)
    # ================================================================== #
    def _build_option_tab(self, kind: str) -> QWidget:
        """构建选项管理 Tab（kind='dir' 或 'struct'）"""
        tab = QWidget()
        tab_layout = QVBoxLayout(tab)
        tab_layout.setContentsMargins(4, 4, 4, 4)

        label_text = "情节方向" if kind == "dir" else "结构微调"
        tab_layout.addWidget(QLabel(f"管理「快速重生成」中的{label_text}选项。点击列表项可编辑。"))

        splitter = QSplitter(Qt.Horizontal)

        # -- 左侧列表 --
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 4, 0)

        lv.addWidget(QLabel(f"{label_text}列表 (点击选中 / 右侧编辑):"))
        lst = QListWidget()
        lst.setAlternatingRowColors(True)
        lv.addWidget(lst, 1)

        btn_row = QHBoxLayout()
        btn_new = QPushButton("新建")
        btn_del = QPushButton("删除")
        btn_del.setStyleSheet("color: #e74c3c;")
        btn_reset = QPushButton("恢复默认")
        btn_row.addWidget(btn_new)
        btn_row.addWidget(btn_del)
        btn_row.addWidget(btn_reset)
        btn_row.addStretch()
        lv.addLayout(btn_row)

        splitter.addWidget(left)

        # -- 右侧编辑面板 --
        right = QGroupBox(f"{label_text}详情")
        rv = QVBoxLayout(right)

        form = QFormLayout()
        key_edit = QLineEdit()
        key_edit.setPlaceholderText("英文标识，如 aggressive")
        form.addRow("标识符 (Key):", key_edit)

        label_edit = QLineEdit()
        label_edit.setPlaceholderText("显示标签，如 🔥 更激进 — 冲突升级")
        form.addRow("显示标签:", label_edit)
        rv.addLayout(form)
        rv.addStretch()

        save_detail_row = QHBoxLayout()
        btn_save_detail = QPushButton("保存修改")
        btn_save_detail.setStyleSheet(
            "QPushButton{background:#e67e22;color:white;font-weight:bold;"
            "padding:5px 16px;border-radius:4px;border:none;}"
            "QPushButton:hover{background:#d35400;}"
        )
        save_detail_row.addWidget(btn_save_detail)
        save_detail_row.addStretch()
        status_lbl = QLabel("")
        status_lbl.setStyleSheet("color: #27ae60; font-size: 12px;")
        save_detail_row.addWidget(status_lbl)
        rv.addLayout(save_detail_row)

        splitter.addWidget(right)
        splitter.setSizes([300, 460])
        tab_layout.addWidget(splitter, 1)

        # 保存引用
        if kind == "dir":
            self._dir_list = lst
            self._dir_key = key_edit
            self._dir_label = label_edit
            self._dir_status = status_lbl
            lst.currentItemChanged.connect(self._on_dir_selected)
            btn_new.clicked.connect(self._on_dir_new)
            btn_del.clicked.connect(self._on_dir_delete)
            btn_reset.clicked.connect(self._on_dir_reset)
            btn_save_detail.clicked.connect(self._on_dir_save_detail)
        else:
            self._struct_list = lst
            self._struct_key = key_edit
            self._struct_label = label_edit
            self._struct_status = status_lbl
            lst.currentItemChanged.connect(self._on_struct_selected)
            btn_new.clicked.connect(self._on_struct_new)
            btn_del.clicked.connect(self._on_struct_delete)
            btn_reset.clicked.connect(self._on_struct_reset)
            btn_save_detail.clicked.connect(self._on_struct_save_detail)

        return tab

    # ================================================================== #
    # Tab 3: Prompt 模板
    # ================================================================== #
    def _build_prompt_tab(self) -> QWidget:
        tab = QWidget()
        v = QVBoxLayout(tab)
        v.setContentsMargins(4, 4, 4, 4)

        v.addWidget(QLabel(
            "以下是级联改写后续章节使用的两个 Prompt 模板。可直接编辑并保存。\n"
            "占位符: {drama_style_block} {source_node_json} {subsequent_nodes_json} {sparkle}"
        ))

        # ---- 保留结尾 Prompt ----
        v.addWidget(QLabel("<b>📝 保留结尾改写 Prompt</b> (仅调整开头衔接，结尾不变):"))
        self._cascade_head_edit = QTextEdit()
        self._cascade_head_edit.setStyleSheet("font-size:11px;")
        v.addWidget(self._cascade_head_edit, 1)

        # ---- 完整改写 Prompt ----
        v.addWidget(QLabel("<b>📝 完整级联改写 Prompt</b> (后续章节全面调整):"))
        self._cascade_full_edit = QTextEdit()
        self._cascade_full_edit.setStyleSheet("font-size:11px;")
        v.addWidget(self._cascade_full_edit, 1)

        btn_row = QHBoxLayout()
        btn_reset = QPushButton("↩ 恢复默认 Prompt")
        btn_reset.clicked.connect(self._reset_prompts)
        btn_row.addWidget(btn_reset)
        btn_row.addStretch()
        v.addLayout(btn_row)

        return tab

    # ================================================================== #
    # 数据加载
    # ================================================================== #
    def _load_data(self):
        # 情节方向
        dirs = self._pd.custom_drama_directions
        if dirs is None:
            dirs = list(DRAMA_DIRECTION_OPTIONS)
        self._populate_list(self._dir_list, dirs)

        # 结构微调
        structs = self._pd.custom_structure_options
        if structs is None:
            structs = list(STRUCTURE_OPTIONS)
        self._populate_list(self._struct_list, structs)

        # Prompt
        head_p = self._pd.custom_cascade_head_prompt
        if head_p is None:
            head_p = SYSTEM_PROMPT_CASCADE_HEAD_ONLY
        self._cascade_head_edit.setPlainText(head_p)

        full_p = self._pd.custom_cascade_full_prompt
        if full_p is None:
            full_p = SYSTEM_PROMPT_CASCADE_FULL
        self._cascade_full_edit.setPlainText(full_p)

    def _populate_list(self, lst: QListWidget, items: list):
        lst.clear()
        for item in items:
            key, label = item[0], item[1]
            li = QListWidgetItem(f"{key}  |  {label}")
            li.setData(Qt.UserRole, [key, label])
            lst.addItem(li)

    # ================================================================== #
    # 情节方向 操作
    # ================================================================== #
    def _on_dir_selected(self, current, previous):
        if current:
            data = current.data(Qt.UserRole)
            self._dir_key.setText(data[0] if data else "")
            self._dir_label.setText(data[1] if data else "")
            self._dir_status.setText("")
        else:
            self._dir_key.clear()
            self._dir_label.clear()

    def _on_dir_new(self):
        li = QListWidgetItem("new_key  |  新选项")
        li.setData(Qt.UserRole, ["new_key", "新选项"])
        self._dir_list.addItem(li)
        self._dir_list.setCurrentItem(li)

    def _on_dir_delete(self):
        row = self._dir_list.currentRow()
        if row >= 0:
            self._dir_list.takeItem(row)

    def _on_dir_reset(self):
        self._populate_list(self._dir_list, list(DRAMA_DIRECTION_OPTIONS))
        self._dir_key.clear()
        self._dir_label.clear()

    def _on_dir_save_detail(self):
        item = self._dir_list.currentItem()
        if not item:
            QMessageBox.information(self, "提示", "请先选中一项。")
            return
        key = self._dir_key.text().strip()
        label = self._dir_label.text().strip()
        if not key or not label:
            QMessageBox.warning(self, "提示", "Key 和标签都不能为空。")
            return
        item.setText(f"{key}  |  {label}")
        item.setData(Qt.UserRole, [key, label])
        self._dir_status.setText("✅ 已更新")

    # ================================================================== #
    # 结构微调 操作
    # ================================================================== #
    def _on_struct_selected(self, current, previous):
        if current:
            data = current.data(Qt.UserRole)
            self._struct_key.setText(data[0] if data else "")
            self._struct_label.setText(data[1] if data else "")
            self._struct_status.setText("")
        else:
            self._struct_key.clear()
            self._struct_label.clear()

    def _on_struct_new(self):
        li = QListWidgetItem("new_key  |  新选项")
        li.setData(Qt.UserRole, ["new_key", "新选项"])
        self._struct_list.addItem(li)
        self._struct_list.setCurrentItem(li)

    def _on_struct_delete(self):
        row = self._struct_list.currentRow()
        if row >= 0:
            self._struct_list.takeItem(row)

    def _on_struct_reset(self):
        self._populate_list(self._struct_list, list(STRUCTURE_OPTIONS))
        self._struct_key.clear()
        self._struct_label.clear()

    def _on_struct_save_detail(self):
        item = self._struct_list.currentItem()
        if not item:
            QMessageBox.information(self, "提示", "请先选中一项。")
            return
        key = self._struct_key.text().strip()
        label = self._struct_label.text().strip()
        if not key or not label:
            QMessageBox.warning(self, "提示", "Key 和标签都不能为空。")
            return
        item.setText(f"{key}  |  {label}")
        item.setData(Qt.UserRole, [key, label])
        self._struct_status.setText("✅ 已更新")

    # ================================================================== #
    # Prompt 操作
    # ================================================================== #
    def _reset_prompts(self):
        self._cascade_head_edit.setPlainText(SYSTEM_PROMPT_CASCADE_HEAD_ONLY)
        self._cascade_full_edit.setPlainText(SYSTEM_PROMPT_CASCADE_FULL)

    # ================================================================== #
    # 保存全部
    # ================================================================== #
    def _do_save(self):
        # 情节方向
        dirs = []
        for i in range(self._dir_list.count()):
            data = self._dir_list.item(i).data(Qt.UserRole)
            dirs.append(data)
        self._pd.custom_drama_directions = dirs

        # 结构微调
        structs = []
        for i in range(self._struct_list.count()):
            data = self._struct_list.item(i).data(Qt.UserRole)
            structs.append(data)
        self._pd.custom_structure_options = structs

        # Prompt
        self._pd.custom_cascade_head_prompt = self._cascade_head_edit.toPlainText()
        self._pd.custom_cascade_full_prompt = self._cascade_full_edit.toPlainText()

        QMessageBox.information(self, "保存成功",
            "AI 辅助修改设置已保存到项目。\n"
            "情节方向/结构微调：下次打开节点详情时生效。\n"
            "Prompt 模板：下次使用级联改写时生效。")
        self.accept()
