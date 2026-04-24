# ============================================================
# ui/widgets/formula_picker_dialog.py
# 爽感 / 钩子公式选择器对话框（tag 样式）
# 左侧: 公式列表  右侧: 选中公式的详细内容
# ============================================================

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QSplitter, QLabel,
    QPushButton, QListWidget, QListWidgetItem, QTextBrowser,
    QWidget, QGroupBox,
)
from PySide6.QtCore import Qt, Signal


class FormulaPickerDialog(QDialog):
    """
    公式选择器对话框。

    左侧显示所有可用公式列表，右侧显示选中公式的详细内容。
    用户点击「添加」将选中的公式加入已选列表。

    参数:
        title: 对话框标题
        templates: 公式列表，每个元素需有 .id, .name, .prompt_text 属性
        already_selected_ids: 已经选中的公式 ID 集合（不在列表中显示）
    """

    def __init__(self, title: str, templates: list,
                 already_selected_ids: set = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(800, 500)
        self.setWindowFlags(
            self.windowFlags()
            | Qt.WindowMaximizeButtonHint
            | Qt.WindowMinimizeButtonHint
        )

        self._templates = templates
        self._already_selected = already_selected_ids or set()
        self._chosen_id = None  # 最终选择的模板 ID

        self._setup_ui()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(6)

        splitter = QSplitter(Qt.Horizontal)

        # --- 左侧: 公式列表 ---
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.addWidget(QLabel("<b>可选公式列表</b>"))

        self._list_widget = QListWidget()
        self._list_widget.setMinimumWidth(220)
        self._list_widget.currentRowChanged.connect(self._on_row_changed)
        lv.addWidget(self._list_widget, 1)

        # 填充列表（排除已选中的）
        self._visible_templates = []
        for t in self._templates:
            if t.id in self._already_selected:
                continue
            self._visible_templates.append(t)
            # 显示名称（爽感公式额外显示等级）
            display_name = t.name
            if hasattr(t, 'level'):
                level_cn = {"small": "小爽", "medium": "中爽", "big": "大爽"}.get(
                    t.level, t.level
                )
                display_name = f"{t.name}（{level_cn}）"
            item = QListWidgetItem(display_name)
            item.setData(Qt.UserRole, t.id)
            self._list_widget.addItem(item)

        splitter.addWidget(left)

        # --- 右侧: 详情面板 ---
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.addWidget(QLabel("<b>公式详情</b>"))

        self._detail_browser = QTextBrowser()
        self._detail_browser.setOpenLinks(False)
        self._detail_browser.setStyleSheet(
            "QTextBrowser{background:#fafafa;border:1px solid #dcdde1;"
            "border-radius:4px;padding:8px;}"
        )
        rv.addWidget(self._detail_browser, 1)

        splitter.addWidget(right)
        splitter.setSizes([250, 550])
        root.addWidget(splitter, 1)

        # --- 底部按钮 ---
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self._btn_add = QPushButton("✅ 添加选中公式")
        self._btn_add.setMinimumHeight(36)
        self._btn_add.setStyleSheet(
            "QPushButton{background:#27ae60;color:white;font-weight:bold;"
            "padding:6px 20px;border-radius:4px;border:none;}"
            "QPushButton:hover{background:#229954;}"
            "QPushButton:disabled{background:#bdc3c7;color:#888;}"
        )
        self._btn_add.setEnabled(False)
        self._btn_add.clicked.connect(self._do_add)
        btn_row.addWidget(self._btn_add)

        btn_cancel = QPushButton("取消")
        btn_cancel.setMinimumHeight(36)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)

        root.addLayout(btn_row)

        # 默认选中第一个
        if self._list_widget.count() > 0:
            self._list_widget.setCurrentRow(0)

    def _on_row_changed(self, row):
        if row < 0 or row >= len(self._visible_templates):
            self._detail_browser.clear()
            self._btn_add.setEnabled(False)
            return

        t = self._visible_templates[row]
        # 构建详情 HTML
        html_parts = [f"<h3>{t.name}</h3>"]
        if hasattr(t, 'level'):
            level_cn = {"small": "小爽", "medium": "中爽", "big": "大爽"}.get(
                t.level, t.level
            )
            html_parts.append(f"<p><b>等级:</b> {level_cn}</p>")

        # 将 prompt_text 的 markdown 格式转为简单 HTML
        text = t.prompt_text
        text = text.replace("**", "<b>").replace("**", "</b>")
        # 处理换行
        text = text.replace("\n", "<br>")
        html_parts.append(f"<div style='margin-top:8px;'>{text}</div>")

        self._detail_browser.setHtml("".join(html_parts))
        self._btn_add.setEnabled(True)

    def _do_add(self):
        row = self._list_widget.currentRow()
        if row < 0 or row >= len(self._visible_templates):
            return
        self._chosen_id = self._visible_templates[row].id
        self.accept()

    def get_chosen_id(self) -> str:
        """返回选中的模板 ID，如果取消则为 None"""
        return self._chosen_id
