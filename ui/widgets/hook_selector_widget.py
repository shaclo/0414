# ============================================================
# ui/widgets/hook_selector_widget.py
# 可复用的钩子公式多选控件（Tag 样式）
# ============================================================

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QMessageBox, QDialog, QListWidget, QListWidgetItem, QTextBrowser,
    QDialogButtonBox, QSplitter
)
from PySide6.QtCore import Signal, Qt


class _HookSelectionDialog(QDialog):
    """独立的钩子选择对话框：左侧多选列表，右侧详情预览"""
    def __init__(self, all_hooks, selected_ids, parent=None):
        super().__init__(parent)
        self.setWindowTitle("选择钩子公式")
        self.resize(700, 500)
        self.all_hooks = all_hooks
        self.selected_ids = set(selected_ids)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        splitter = QSplitter(Qt.Horizontal)
        
        # 左侧列表
        self.list_widget = QListWidget()
        for hook in self.all_hooks:
            item = QListWidgetItem(hook.name)
            item.setData(Qt.UserRole, hook)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            if hook.id in self.selected_ids:
                item.setCheckState(Qt.Checked)
            else:
                item.setCheckState(Qt.Unchecked)
            self.list_widget.addItem(item)
            
        self.list_widget.currentItemChanged.connect(self._on_item_changed)
        splitter.addWidget(self.list_widget)
        
        # 右侧详情
        self.detail_view = QTextBrowser()
        self.detail_view.setPlaceholderText("选择左侧钩子查看详情...")
        splitter.addWidget(self.detail_view)
        
        splitter.setSizes([250, 450])
        layout.addWidget(splitter, 1)
        
        # 按钮
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)
        
        # 默认选中第一项以显示详情
        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)

    def _on_item_changed(self, current, previous):
        if current:
            hook = current.data(Qt.UserRole)
            html = f"<h3>{hook.name}</h3><hr>"
            html += f"<pre style='font-family:inherit;font-size:13px;white-space:pre-wrap;'>{hook.prompt_text}</pre>"
            self.detail_view.setHtml(html)
            
    def get_selected_ids(self):
        selected = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.checkState() == Qt.Checked:
                hook = item.data(Qt.UserRole)
                selected.append(hook.id)
        return selected


class HookSelectorWidget(QWidget):
    """
    标签风格的钩子多选控件。
    类似 CPG 节点的入口/出口标签（Tag）选择 UI。
    """
    selectionChanged = Signal(list)

    def __init__(self, parent=None, collapsed=True):
        super().__init__(parent)
        self._all_hooks = []       # 所有启用的钩子 [{id, name, text}, ...]
        self._selected_ids = set() # 当前选中的钩子 ID 集合

        self._setup_ui()
        self._load_hooks()

    def _setup_ui(self):
        self.setFixedHeight(32)
        
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(6)

        # 标题标签
        lbl_title = QLabel("<b>🎣 钩子公式选择:</b>")
        lbl_title.setStyleSheet("color:#2d3436;")
        main_layout.addWidget(lbl_title)

        # 存放已选 Tag 的容器 (使用普通的水平布局即可，因数量有限)
        self._tag_container = QWidget()
        self._tag_flow = QHBoxLayout(self._tag_container)
        self._tag_flow.setContentsMargins(0, 0, 0, 0)
        self._tag_flow.setSpacing(6)
        main_layout.addWidget(self._tag_container)

        # 添加按钮
        self._btn_add = QPushButton("+")
        self._btn_add.setFixedSize(28, 24)
        self._btn_add.setAutoDefault(False)
        self._btn_add.setDefault(False)
        self._btn_add.setToolTip("管理/添加钩子")
        self._btn_add.setStyleSheet(
            "QPushButton{color:#2980b9; background:#ebf5fb; font-weight:bold; border:1px solid #bdc3c7; border-radius:3px; padding:0;}"
            "QPushButton:hover{background:#d6eaf8; border:1px solid #2980b9;}"
        )
        self._btn_add.clicked.connect(self._do_add_hook)
        main_layout.addWidget(self._btn_add)
        
        main_layout.addStretch()

    def _load_hooks(self):
        """加载所有启用的钩子"""
        from config.prompt_templates import prompt_template_manager
        hooks = prompt_template_manager.get_hooks()
        self._all_hooks = [h for h in hooks if h.enabled]
        self._refresh_tags()

    def _make_tag_widget(self, hook_id: str, hook_name: str) -> QWidget:
        tag = QWidget()
        tag.setFixedHeight(24)
        h = QHBoxLayout(tag)
        h.setContentsMargins(8, 0, 2, 0)
        h.setSpacing(4)
        
        lbl = QLabel(hook_name)
        lbl.setStyleSheet("color:#2c3e50; font-size:12px;")
        h.addWidget(lbl)
        
        btn_x = QPushButton("x")
        btn_x.setFixedSize(16, 16)
        btn_x.setStyleSheet(
            "QPushButton{border:none;color:#e74c3c;font-weight:bold;padding:0;}"
            "QPushButton:hover{color:#c0392b;background:#fadbd8;border-radius:8px;}"
        )
        btn_x.setCursor(Qt.PointingHandCursor)
        btn_x.clicked.connect(lambda _, hid=hook_id: self._do_remove_hook(hid))
        h.addWidget(btn_x)
        
        tag.setObjectName("hookTag")
        tag.setStyleSheet(
            "#hookTag{background:#fdfefe;border:1px solid #aeb6bf;border-radius:12px;}"
        )
        return tag

    def _refresh_tags(self):
        # 清空现有 tags
        while self._tag_flow.count():
            item = self._tag_flow.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        # 按照 all_hooks 的顺序来显示已选 tags，保证顺序稳定
        for h in self._all_hooks:
            if h.id in self._selected_ids:
                tag_widget = self._make_tag_widget(h.id, h.name)
                tag_widget.setToolTip(h.prompt_text)
                self._tag_flow.addWidget(tag_widget)
        
        self.selectionChanged.emit(self.selected_ids())

    def _do_remove_hook(self, hook_id: str):
        self._selected_ids.discard(hook_id)
        self._refresh_tags()

    def _do_add_hook(self):
        if not self._all_hooks:
            QMessageBox.information(self, "提示", "当前没有启用的钩子公式。")
            return
            
        dlg = _HookSelectionDialog(self._all_hooks, self._selected_ids, self)
        if dlg.exec() == QDialog.Accepted:
            self._selected_ids = set(dlg.get_selected_ids())
            self._refresh_tags()

    # ---- 公开接口 ----
    def selected_ids(self) -> list:
        return [h.id for h in self._all_hooks if h.id in self._selected_ids]

    def set_selected_ids(self, ids: list):
        self._selected_ids = set(ids or [])
        self._refresh_tags()

    def reload(self):
        self._load_hooks()

