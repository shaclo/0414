# ============================================================
# ui/widgets/screenplay_editor.py
# 剧本文本编辑器 — Phase 5 右侧使用
# 支持富文本编辑 + 实时字数统计 + 目标字数颜色提示
# ============================================================

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTextEdit, QPushButton, QSpinBox,
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QColor, QPalette


class ScreenplayEditor(QWidget):
    """
    剧本文本编辑器。
    内嵌实时字数统计，颜色提示是否命中目标字数范围。

    信号:
        text_changed: 内容变化时发出（带消抖）
    """

    text_changed = Signal(str)

    def __init__(self, target_min: int = 600, target_max: int = 800, parent=None):
        super().__init__(parent)
        self._target_min = target_min
        self._target_max = target_max
        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(500)
        self._debounce_timer.timeout.connect(self._emit_text_changed)
        self._setup_ui()

    # ------------------------------------------------------------------ #
    # UI
    # ------------------------------------------------------------------ #
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # 顶部工具栏
        toolbar = QHBoxLayout()

        toolbar.addWidget(QLabel("📝 剧本正文"))
        toolbar.addStretch()

        toolbar.addWidget(QLabel("目标字数:"))
        self._min_spin = QSpinBox()
        self._min_spin.setRange(100, 5000)
        self._min_spin.setSingleStep(100)
        self._min_spin.setValue(self._target_min)
        self._min_spin.setMaximumWidth(105)
        self._min_spin.valueChanged.connect(self._on_target_changed)
        toolbar.addWidget(self._min_spin)

        toolbar.addWidget(QLabel("-"))

        self._max_spin = QSpinBox()
        self._max_spin.setRange(100, 5000)
        self._max_spin.setSingleStep(100)
        self._max_spin.setValue(self._target_max)
        self._max_spin.setMaximumWidth(105)
        self._max_spin.valueChanged.connect(self._on_target_changed)
        toolbar.addWidget(self._max_spin)

        toolbar.addWidget(QLabel("字/节"))

        layout.addLayout(toolbar)

        # 主编辑区
        self._editor = QTextEdit()
        self._editor.setPlaceholderText(
            "剧本正文将在此处显示，您可以直接编辑。\n\n"
            "格式参考：\n"
            "场景 1  【内景. 地点 - 时间】\n\n"
            "（环境动作描写）\n\n"
            "角色名（状态）：\n"
            "\"对话内容\""
        )
        self._editor.setStyleSheet(
            "QTextEdit {"
            "  font-family: 'Microsoft YaHei', 'Noto Sans CJK SC', monospace;"
            ""
            "  line-height: 1.6;"
            "  background: #fafafa;"
            "  border: 1px solid #dcdde1;"
            "  border-radius: 6px;"
            "  padding: 10px;"
            "}"
        )
        self._editor.textChanged.connect(self._on_text_changed)
        layout.addWidget(self._editor, 1)

        # 底部字数统计栏
        self._status_bar = QLabel("字数: 0  |  目标: 600-800 字")
        self._status_bar.setStyleSheet(
            "QLabel {"
            ""
            "  padding: 4px 8px;"
            "  border-top: 1px solid #ecf0f1;"
            "  color: #555;"
            "}"
        )
        layout.addWidget(self._status_bar)

    # ------------------------------------------------------------------ #
    # 公开接口
    # ------------------------------------------------------------------ #
    def set_text(self, text: str):
        """设置剧本正文"""
        self._editor.blockSignals(True)
        self._editor.setPlainText(text)
        self._editor.blockSignals(False)
        self._update_word_count()

    def get_text(self) -> str:
        return self._editor.toPlainText()

    def set_target_range(self, min_words: int, max_words: int):
        """更新目标字数范围"""
        self._target_min = min_words
        self._target_max = max_words
        self._min_spin.setValue(min_words)
        self._max_spin.setValue(max_words)
        self._update_word_count()

    def get_target_range(self) -> tuple:
        return self._target_min, self._target_max

    def clear(self):
        self._editor.clear()

    # ------------------------------------------------------------------ #
    # 内部
    # ------------------------------------------------------------------ #
    def _on_target_changed(self):
        self._target_min = self._min_spin.value()
        self._target_max = self._max_spin.value()
        self._update_word_count()

    def _on_text_changed(self):
        self._update_word_count()
        self._debounce_timer.start()

    def _emit_text_changed(self):
        self.text_changed.emit(self._editor.toPlainText())

    def _update_word_count(self):
        text = self._editor.toPlainText()
        count = len(text)  # 中文按字符计数

        if count < self._target_min:
            color = "#e67e22"       # 橙色：字数不足
            status = "字数不足"
        elif count > self._target_max:
            color = "#e74c3c"       # 红色：字数超限
            status = "字数超限"
        else:
            color = "#27ae60"       # 绿色：命中目标
            status = "✅ 符合目标"

        self._status_bar.setText(
            f"字数: {count}  |  目标: {self._target_min}-{self._target_max} 字  |  {status}"
        )
        self._status_bar.setStyleSheet(
            f"QLabel {{"
            f" padding: 4px 8px;"
            f"  border-top: 1px solid #ecf0f1;"
            f"  color: {color}; font-weight: bold;"
            f"}}"
        )
