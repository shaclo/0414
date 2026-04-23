# ============================================================
# ui/widgets/prompt_viewer.py
# System Prompt 折叠展示器
# 显示当前阶段使用的完整 system prompt + user prompt
# ============================================================

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QTextEdit, QLabel,
)
from PySide6.QtCore import Qt


class PromptViewer(QWidget):
    """
    折叠式 Prompt 展示器。
    默认收起，点击后展开显示当前阶段的 System Prompt。
    只读模式。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_expanded = False
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # 折叠按钮
        self._toggle_btn = QPushButton("📋 System Prompt [点击展开 ▼]")
        self._toggle_btn.setCheckable(True)
        self._toggle_btn.setFlat(True)
        self._toggle_btn.clicked.connect(self._toggle)
        layout.addWidget(self._toggle_btn)

        # Prompt 文本区域（默认隐藏）
        self._text_edit = QTextEdit()
        self._text_edit.setReadOnly(True)
        self._text_edit.setMaximumHeight(300)
        self._text_edit.setVisible(False)
        self._text_edit.setStyleSheet(
            "QTextEdit { background-color: #1e1e2e; color: #cdd6f4; "
            "font-family: 'Consolas', 'Microsoft YaHei'; "
            "border: 1px solid #45475a; border-radius: 4px; padding: 8px; }"
        )
        layout.addWidget(self._text_edit)

    def _toggle(self, checked):
        self._is_expanded = checked
        self._text_edit.setVisible(checked)
        if checked:
            self._toggle_btn.setText("📋 System Prompt [点击收起 ▲]")
        else:
            self._toggle_btn.setText("📋 System Prompt [点击展开 ▼]")

    def set_prompt(self, system_prompt: str, user_prompt: str = ""):
        """设置要展示的 prompt 内容"""
        content = f"===== SYSTEM PROMPT =====\n{system_prompt}"
        if user_prompt:
            content += f"\n\n===== USER PROMPT (模板) =====\n{user_prompt}"
        self._text_edit.setPlainText(content)

    def set_system_prompt(self, prompt: str):
        """只设置 system prompt"""
        self.set_prompt(prompt)
