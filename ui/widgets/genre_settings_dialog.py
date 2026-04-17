# ============================================================
# ui/widgets/genre_settings_dialog.py
# 题材预设设置对话框（支持查看/新增/删除/编辑 + 持久化）
# ============================================================

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QSplitter,
    QListWidget, QListWidgetItem, QPushButton, QLabel,
    QTextEdit, QLineEdit, QFormLayout, QGroupBox, QWidget,
    QMessageBox,
)
from PySide6.QtCore import Qt

from services.genre_manager import genre_manager


class GenreSettingsDialog(QDialog):
    """
    题材预设查看/编辑对话框。
    左侧：题材列表（当前项目激活状态标记）
    右侧：选中题材的详情表单（可编辑）
    支持新增/删除/编辑/保存，数据持久化到 config/genre_presets.json
    """

    def __init__(self, project_data=None, parent=None):
        super().__init__(parent)
        self._project_data = project_data
        self._selected_key = ""
        self._is_new_mode = False

        self.setWindowTitle("题材预设设置")
        self.setMinimumSize(920, 620)
        self._setup_ui()
        self._refresh_list()

    # ------------------------------------------------------------------ #
    # UI 构建
    # ------------------------------------------------------------------ #
    def _setup_ui(self):
        root = QVBoxLayout(self)

        tip = QLabel(
            "管理写作题材预设。选择题材后，系统将自动向骨架/血肉/扩写三个阶段注入\n"
            "题材专属的节奏规则和创作纪律，与短剧/传统风格配置叠加生效。"
        )
        tip.setWordWrap(True)
        tip.setStyleSheet("color: #636e72; font-size: 12px; padding: 4px 0;")
        root.addWidget(tip)

        splitter = QSplitter(Qt.Horizontal)

        # ---- 左侧：题材列表 ----
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 4, 0)

        lv.addWidget(QLabel("题材列表 (点击查看 / 双击应用到项目):"))
        self._list = QListWidget()
        self._list.setAlternatingRowColors(True)
        self._list.currentItemChanged.connect(self._on_list_selection_changed)
        self._list.itemDoubleClicked.connect(self._on_activate)
        lv.addWidget(self._list)

        btn_row = QHBoxLayout()
        self._btn_new = QPushButton("新建题材")
        self._btn_new.clicked.connect(self._on_new)
        btn_row.addWidget(self._btn_new)

        self._btn_delete = QPushButton("删除")
        self._btn_delete.setEnabled(False)
        self._btn_delete.setStyleSheet("color: #e74c3c;")
        self._btn_delete.clicked.connect(self._on_delete)
        btn_row.addWidget(self._btn_delete)

        self._btn_reset = QPushButton("恢复默认")
        self._btn_reset.setToolTip("恢复到系统内置的默认题材预设")
        self._btn_reset.clicked.connect(self._on_reset)
        btn_row.addWidget(self._btn_reset)
        lv.addLayout(btn_row)

        self._activate_btn = QPushButton("应用到当前项目")
        self._activate_btn.setEnabled(False)
        self._activate_btn.setStyleSheet(
            "QPushButton{background:#27ae60;color:white;font-weight:bold;"
            "border-radius:4px;border:none;padding:6px 12px;}"
            "QPushButton:hover{background:#229954;}"
            "QPushButton:disabled{background:#bdc3c7;color:#888;}"
        )
        self._activate_btn.clicked.connect(self._on_activate)
        lv.addWidget(self._activate_btn)

        splitter.addWidget(left)

        # ---- 右侧：题材详情（可编辑） ----
        right = QGroupBox("题材详情")
        rv = QVBoxLayout(right)

        form = QFormLayout()
        self._key_edit = QLineEdit()
        self._key_edit.setPlaceholderText("英文唯一标识，如 military")
        form.addRow("标识符 (Key):", self._key_edit)

        self._label_edit = QLineEdit()
        self._label_edit.setPlaceholderText("显示名称，如: 军事/战争")
        form.addRow("名称:", self._label_edit)

        self._desc_edit = QLineEdit()
        self._desc_edit.setPlaceholderText("简要描述，如: 战场博弈，兄弟情义，生死抉择")
        form.addRow("描述:", self._desc_edit)

        self._active_label = QLabel("")
        self._active_label.setStyleSheet("font-weight: bold;")
        form.addRow("状态:", self._active_label)
        rv.addLayout(form)

        # 三段 block 编辑器
        for attr, label in [
            ("_skel_edit", "骨架生成规则 (skeleton_block)"),
            ("_var_edit",  "变异创作纪律 (variation_block)"),
            ("_exp_edit",  "扩写行文规则 (expansion_block)"),
        ]:
            rv.addWidget(QLabel(label + ":"))
            text = QTextEdit()
            text.setMaximumHeight(100)
            text.setStyleSheet(
                "QTextEdit{background:#f8f9fa;border:1px solid #dee2e6;"
                "border-radius:4px;font-size:11px;color:#495057;}"
            )
            text.setPlaceholderText("在此输入该阶段的注入规则（可为空）")
            setattr(self, attr, text)
            rv.addWidget(text)

        # 保存按钮
        save_row = QHBoxLayout()
        self._btn_save = QPushButton("保存修改")
        self._btn_save.setEnabled(False)
        self._btn_save.setStyleSheet(
            "QPushButton{background:#3498db;color:white;font-weight:bold;"
            "border-radius:4px;border:none;padding:6px 12px;}"
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
        splitter.setSizes([280, 640])
        root.addWidget(splitter, 1)

        # 底部关闭
        bottom = QHBoxLayout()
        bottom.addStretch()
        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(self.accept)
        bottom.addWidget(btn_close)
        root.addLayout(bottom)

    # ------------------------------------------------------------------ #
    # 列表
    # ------------------------------------------------------------------ #
    def _refresh_list(self, select_key: str = ""):
        current_genre = ""
        if self._project_data:
            current_genre = getattr(self._project_data, 'story_genre', 'custom')

        self._list.blockSignals(True)
        self._list.clear()
        for key, preset in genre_manager.get_all().items():
            label = preset.get("label", key)
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, key)
            if key == current_genre:
                font = item.font()
                font.setBold(True)
                item.setFont(font)
                item.setText(label + "  [当前]")
            self._list.addItem(item)
            if key == select_key:
                self._list.setCurrentItem(item)
        self._list.blockSignals(False)

        # 选中当前或指定项
        if not select_key and current_genre:
            select_key = current_genre
        for i in range(self._list.count()):
            if self._list.item(i).data(Qt.UserRole) == select_key:
                self._list.setCurrentRow(i)
                break

    def _on_list_selection_changed(self, current, previous):
        self._is_new_mode = False
        if current is None:
            self._clear_form()
            self._btn_delete.setEnabled(False)
            self._btn_save.setEnabled(False)
            self._activate_btn.setEnabled(False)
            return
        key = current.data(Qt.UserRole)
        self._selected_key = key
        self._load_form(key)
        self._btn_delete.setEnabled(True)
        self._btn_save.setEnabled(True)
        self._activate_btn.setEnabled(True)

    # ------------------------------------------------------------------ #
    # 表单
    # ------------------------------------------------------------------ #
    def _load_form(self, key: str):
        preset = genre_manager.get(key)
        current_genre = ""
        if self._project_data:
            current_genre = getattr(self._project_data, 'story_genre', 'custom')

        self._key_edit.setText(key)
        self._key_edit.setEnabled(False)  # 已有题材不能改 key
        self._label_edit.setText(preset.get("label", ""))
        self._desc_edit.setText(preset.get("description", ""))

        if key == current_genre:
            self._active_label.setText("已应用到当前项目")
            self._active_label.setStyleSheet("font-weight:bold; color:#27ae60;")
        else:
            self._active_label.setText("未应用")
            self._active_label.setStyleSheet("font-weight:bold; color:#7f8c8d;")

        self._skel_edit.setPlainText(preset.get("skeleton_block", ""))
        self._var_edit.setPlainText(preset.get("variation_block", ""))
        self._exp_edit.setPlainText(preset.get("expansion_block", ""))
        self._status_label.setText("")

    def _clear_form(self):
        self._selected_key = ""
        self._key_edit.setText("")
        self._key_edit.setEnabled(True)
        self._label_edit.setText("")
        self._desc_edit.setText("")
        self._active_label.setText("")
        self._skel_edit.clear()
        self._var_edit.clear()
        self._exp_edit.clear()
        self._status_label.setText("")

    # ------------------------------------------------------------------ #
    # 操作
    # ------------------------------------------------------------------ #
    def _on_new(self):
        self._list.clearSelection()
        self._clear_form()
        self._is_new_mode = True
        self._key_edit.setEnabled(True)
        self._btn_save.setEnabled(True)
        self._btn_delete.setEnabled(False)
        self._activate_btn.setEnabled(False)
        self._key_edit.setFocus()
        self._status_label.setText("填写右侧表单后点击「保存修改」")

    def _on_save(self):
        key = self._key_edit.text().strip()
        label = self._label_edit.text().strip()
        desc = self._desc_edit.text().strip()
        skel = self._skel_edit.toPlainText().strip()
        var = self._var_edit.toPlainText().strip()
        exp = self._exp_edit.toPlainText().strip()

        if not key:
            QMessageBox.warning(self, "验证失败", "标识符 (Key) 不能为空")
            return
        if not label:
            QMessageBox.warning(self, "验证失败", "名称不能为空")
            return

        import re
        if not re.match(r'^[a-zA-Z][a-zA-Z0-9_]*$', key):
            QMessageBox.warning(self, "验证失败", "Key 只能以字母开头，包含字母/数字/下划线")
            return

        try:
            if self._is_new_mode or (self._selected_key == "" and key not in genre_manager.get_all()):
                genre_manager.add(key, label, desc, skel, var, exp)
                self._selected_key = key
                self._is_new_mode = False
                self._status_label.setText(f"已添加：{label}")
            else:
                genre_manager.update(
                    self._selected_key or key,
                    label, desc, skel, var, exp
                )
                self._status_label.setText(f"已更新：{label}")
            self._refresh_list(select_key=key)
        except (ValueError, KeyError) as e:
            QMessageBox.warning(self, "保存失败", str(e))

    def _on_delete(self):
        if not self._selected_key:
            return
        preset = genre_manager.get(self._selected_key)
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定删除题材预设「{preset.get('label', self._selected_key)}」？",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            # 如果当前项目使用此题材，切换到 custom
            if self._project_data:
                if getattr(self._project_data, 'story_genre', '') == self._selected_key:
                    self._project_data.story_genre = "custom"
            genre_manager.remove(self._selected_key)
            self._selected_key = ""
            self._clear_form()
            self._btn_delete.setEnabled(False)
            self._btn_save.setEnabled(False)
            self._refresh_list()

    def _on_reset(self):
        reply = QMessageBox.question(
            self, "恢复默认",
            "确定恢复到系统内置的默认题材预设？\n所有自定义修改将丢失。",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            genre_manager.reset_to_defaults()
            self._refresh_list()
            self._status_label.setText("已恢复默认预设")

    def _on_activate(self, *_):
        if not self._selected_key:
            return
        if self._project_data is None:
            self._status_label.setText("无项目数据，无法应用")
            return
        preset = genre_manager.get(self._selected_key)
        self._project_data.story_genre = self._selected_key
        label = preset.get("label", self._selected_key)
        self._status_label.setText(f"已应用：{label}")
        self._refresh_list(select_key=self._selected_key)
        self._load_form(self._selected_key)
