# ============================================================
# ui/widgets/log_viewer_dialog.py
# 日志查看对话框 — 浏览 logs/ 目录中的日志文件
# 支持：日期文件切换、关键词过滤、级别过滤、颜色高亮
# ============================================================

import os
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QListWidget, QListWidgetItem,
    QTextEdit, QLineEdit, QComboBox, QSplitter,
    QWidget, QGroupBox,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QTextCharFormat, QColor, QFont, QTextCursor

from services.logger_service import app_logger


# 各级别对应的 HTML 颜色
LEVEL_COLORS = {
    "信息":    "#2c3e50",   # 深灰
    "成功":    "#27ae60",   # 绿
    "警告":    "#e67e22",   # 橙
    "错误":    "#e74c3c",   # 红
}

LEVEL_BG_COLORS = {
    "信息":    None,
    "成功":    "#f0fff4",
    "警告":    "#fffbf0",
    "错误":    "#fff5f5",
}


class LogViewerDialog(QDialog):
    """
    日志查看对话框。

    布局:
        左侧: 日志文件列表（按日期倒序）
        右侧: 日志内容区（可过滤、可搜索）
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("查看日志")
        self.resize(1100, 700)
        self.setMinimumSize(800, 500)
        self.setWindowFlags(self.windowFlags() | Qt.WindowMaximizeButtonHint | Qt.WindowMinimizeButtonHint)

        self._current_file: str = ""
        self._all_lines: list = []   # 当前文件所有行
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(300)
        self._search_timer.timeout.connect(self._apply_filter)

        self._setup_ui()
        self._load_file_list()

        # 实时更新：连接 app_logger 的信号
        app_logger.new_log_entry.connect(self._on_new_log_entry)

    # ------------------------------------------------------------------ #
    # UI
    # ------------------------------------------------------------------ #
    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # 顶部工具栏
        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("应用日志查看器"))
        toolbar.addStretch()

        self._btn_refresh = QPushButton("刷新")
        self._btn_refresh.setFixedWidth(80)
        self._btn_refresh.clicked.connect(self._on_refresh)
        toolbar.addWidget(self._btn_refresh)

        self._btn_open_dir = QPushButton("打开日志目录")
        self._btn_open_dir.clicked.connect(self._on_open_dir)
        toolbar.addWidget(self._btn_open_dir)

        self._btn_close = QPushButton("关闭")
        self._btn_close.setFixedWidth(60)
        self._btn_close.clicked.connect(self.accept)
        toolbar.addWidget(self._btn_close)

        root.addLayout(toolbar)

        # 主分割区
        splitter = QSplitter(Qt.Horizontal)

        # 左侧：文件列表
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 4, 0)
        ll.setSpacing(4)

        file_label = QLabel("日志文件（按日期）")
        file_label.setStyleSheet("font-weight:bold;")
        ll.addWidget(file_label)

        self._file_list = QListWidget()
        self._file_list.setMaximumWidth(200)
        self._file_list.setStyleSheet(
            "QListWidget{border:1px solid #dcdde1;border-radius:4px;}"
            "QListWidget::item{padding:4px 8px;}"
            "QListWidget::item:selected{background:#3498db;color:white;}"
        )
        self._file_list.currentItemChanged.connect(self._on_file_selected)
        ll.addWidget(self._file_list, 1)

        # 统计标签
        self._stat_label = QLabel("")
        self._stat_label.setStyleSheet("color:#7f8c8d;")
        ll.addWidget(self._stat_label)

        splitter.addWidget(left)

        # 右侧：内容区
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(4, 0, 0, 0)
        rl.setSpacing(4)

        # 过滤工具栏
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("搜索:"))

        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("输入关键词过滤…")
        self._search_edit.textChanged.connect(self._on_search_changed)
        filter_row.addWidget(self._search_edit, 1)

        filter_row.addWidget(QLabel("  级别:"))
        self._level_combo = QComboBox()
        self._level_combo.addItems(["全部", "信息", "成功", "警告", "错误"])
        self._level_combo.setFixedWidth(80)
        self._level_combo.currentIndexChanged.connect(self._apply_filter)
        filter_row.addWidget(self._level_combo)

        self._btn_scroll_bottom = QPushButton("最新")
        self._btn_scroll_bottom.setFixedWidth(70)
        self._btn_scroll_bottom.clicked.connect(self._scroll_to_bottom)
        filter_row.addWidget(self._btn_scroll_bottom)

        rl.addLayout(filter_row)

        # 日志内容
        self._log_text = QTextEdit()
        self._log_text.setReadOnly(True)
        self._log_text.setStyleSheet(
            "QTextEdit{"
            "  font-family: 'Consolas','Microsoft YaHei',monospace;"
            ""
            "  background: #fafafa;"
            "  border: 1px solid #dcdde1;"
            "  border-radius: 4px;"
            "  padding: 4px;"
            "}"
        )
        rl.addWidget(self._log_text, 1)

        splitter.addWidget(right)
        splitter.setSizes([180, 880])

        root.addWidget(splitter, 1)

    # ------------------------------------------------------------------ #
    # 文件列表
    # ------------------------------------------------------------------ #
    def _load_file_list(self):
        self._file_list.clear()
        files = app_logger.get_log_files()

        today_str = self._today_str()

        for filepath in files:
            basename = os.path.basename(filepath)
            date_str = basename.replace(".log", "")
            display = f"{date_str}"
            if date_str == today_str:
                display = f"{date_str} (今日)"

            item = QListWidgetItem(display)
            item.setData(Qt.UserRole, filepath)
            self._file_list.addItem(item)

        # 默认选中今日
        if self._file_list.count() > 0:
            self._file_list.setCurrentRow(0)

    def _on_file_selected(self, current, _previous):
        if current is None:
            return
        filepath = current.data(Qt.UserRole)
        self._load_log_file(filepath)

    def _load_log_file(self, filepath: str):
        self._current_file = filepath
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            self._log_text.setPlainText(f"读取日志文件失败：{e}")
            return

        # 解析行
        self._all_lines = self._parse_log_entries(content)
        self._apply_filter()

    def _parse_log_entries(self, content: str) -> list:
        """
        将日志文本解析为条目列表，每条条目包含首行和后续详情。
        返回: list of {"header": str, "detail": str, "level": str}
        """
        entries = []
        lines = content.splitlines()
        i = 0
        while i < len(lines):
            line = lines[i]
            if line.startswith("[") and "] [" in line:
                # 尝试提取级别
                level = "信息"
                for lv in ["错误", "警告", "成功", "信息"]:
                    if f"[{lv}]" in line:
                        level = lv
                        break
                # 收集后续缩进行作为 detail
                detail_lines = []
                j = i + 1
                while j < len(lines) and (lines[j].startswith("    ") or lines[j].startswith("\t")):
                    detail_lines.append(lines[j])
                    j += 1
                entries.append({
                    "header": line,
                    "detail": "\n".join(detail_lines),
                    "level": level,
                })
                i = j
            else:
                # 孤立行（可能是旧格式）
                if entries:
                    entries[-1]["detail"] += ("\n" if entries[-1]["detail"] else "") + line
                i += 1
        return entries

    # ------------------------------------------------------------------ #
    # 过滤 & 渲染
    # ------------------------------------------------------------------ #
    def _on_search_changed(self, _text: str):
        self._search_timer.start()

    def _apply_filter(self):
        keyword = self._search_edit.text().strip().lower()
        level_filter = self._level_combo.currentText()

        filtered = []
        for entry in self._all_lines:
            # 级别过滤
            if level_filter != "全部" and entry["level"] != level_filter:
                continue
            # 关键词过滤
            if keyword:
                searchable = (entry["header"] + entry["detail"]).lower()
                if keyword not in searchable:
                    continue
            filtered.append(entry)

        self._render_entries(filtered)
        self._stat_label.setText(f"显示 {len(filtered)} / {len(self._all_lines)} 条")

    def _render_entries(self, entries: list):
        """将过滤后的条目渲染为 HTML 富文本"""
        self._log_text.clear()
        cursor = self._log_text.textCursor()

        for entry in entries:
            level = entry["level"]
            color = LEVEL_COLORS.get(level, "#2c3e50")
            bg = LEVEL_BG_COLORS.get(level)

            # 主行格式
            header_fmt = QTextCharFormat()
            header_fmt.setForeground(QColor(color))
            header_fmt.setFontWeight(QFont.Bold if level in ("成功", "错误", "警告") else QFont.Normal)
            if bg:
                header_fmt.setBackground(QColor(bg))

            cursor.setCharFormat(header_fmt)
            cursor.insertText(entry["header"] + "\n")

            # 详情行格式（缩进，稍小字号，颜色稍浅）
            if entry["detail"]:
                detail_fmt = QTextCharFormat()
                detail_fmt.setForeground(QColor("#555"))
                detail_fmt.setFontPointSize(10)
                if bg:
                    detail_fmt.setBackground(QColor(bg))
                cursor.setCharFormat(detail_fmt)
                cursor.insertText(entry["detail"] + "\n")

        self._log_text.setTextCursor(cursor)

    def _scroll_to_bottom(self):
        self._log_text.verticalScrollBar().setValue(
            self._log_text.verticalScrollBar().maximum()
        )

    # ------------------------------------------------------------------ #
    # 实时更新（当前查看的是今日文件时追加）
    # ------------------------------------------------------------------ #
    def _on_new_log_entry(self, entry_text: str):
        """有新日志写入时，如果当前显示的是今日文件则自动刷新"""
        today_path = os.path.join(
            app_logger.get_log_dir(),
            f"{self._today_str()}.log"
        )
        if self._current_file == today_path:
            # 重新解析该文件（保证完整）
            self._load_log_file(self._current_file)
            self._scroll_to_bottom()

    # ------------------------------------------------------------------ #
    # 工具
    # ------------------------------------------------------------------ #
    def _on_refresh(self):
        self._load_file_list()
        if self._current_file:
            self._load_log_file(self._current_file)

    def _on_open_dir(self):
        import subprocess
        log_dir = app_logger.get_log_dir()
        try:
            subprocess.Popen(["explorer", log_dir])
        except Exception:
            pass

    @staticmethod
    def _today_str() -> str:
        import datetime
        return datetime.datetime.now().strftime("%Y-%m-%d")
