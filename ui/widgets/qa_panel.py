# ============================================================
# ui/widgets/qa_panel.py
# 苏格拉底问答面板 — Phase 1 使用
# ============================================================

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTextEdit, QScrollArea, QFrame, QPushButton,
)
from PySide6.QtCore import Qt, Signal


class QAPanel(QWidget):
    """
    苏格拉底问答面板。
    动态展示 AI 生成的问题列表，用户逐一填写回答。

    信号:
        all_answered: 所有问题都已回答时发出
    """

    all_answered = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._qa_widgets = []  # [(question_data, answer_input, frame)]
        self._scroll = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        header = QLabel("问答区 — 请逐一回答以下问题")
        header.setStyleSheet("font-weight: bold; font-size: 13px; padding: 4px 0;")
        layout.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        self._scroll_content = QWidget()
        self._scroll_layout = QVBoxLayout(self._scroll_content)
        self._scroll_layout.setSpacing(12)
        self._scroll_layout.addStretch()
        scroll.setWidget(self._scroll_content)  # 关键：将内容挂到 ScrollArea
        self._scroll = scroll
        layout.addWidget(scroll)

    def set_questions(self, questions: list):
        """
        设置问题列表（AI-Call-1 返回后调用）。

        Args:
            questions: [{"id": 1, "dimension": "...", "question": "...", "rationale": "..."}]
        """
        self._qa_widgets.clear()
        while self._scroll_layout.count() > 1:
            item = self._scroll_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for q in questions:
            q_frame = QFrame()
            q_frame.setFrameShape(QFrame.StyledPanel)
            q_frame.setStyleSheet(
                "QFrame { border: 1px solid #dcdde1; border-radius: 6px; "
                "background-color: #fafafa; }"
            )
            q_layout = QVBoxLayout(q_frame)
            q_layout.setContentsMargins(10, 8, 10, 8)
            q_layout.setSpacing(6)

            # 维度标签
            dim_label = QLabel(f"Q{q.get('id', '')}  [{q.get('dimension', '')}]")
            dim_label.setStyleSheet("font-weight: bold; color: #2980b9; font-size: 11px;")
            q_layout.addWidget(dim_label)

            # 问题内容
            question_label = QLabel(q.get("question", ""))
            question_label.setWordWrap(True)
            question_label.setStyleSheet("font-size: 13px; color: #2c3e50;")
            q_layout.addWidget(question_label)

            # 追问理由（灰色小字）
            rationale = q.get("rationale", "")
            if rationale:
                rationale_label = QLabel(f"[追问依据] {rationale}")
                rationale_label.setWordWrap(True)
                rationale_label.setStyleSheet(
                    "color: #95a5a6; font-size: 10px; font-style: italic;"
                )
                q_layout.addWidget(rationale_label)

            # 回答输入（支持多行）
            answer_input = QTextEdit()
            answer_input.setPlaceholderText("请输入你的回答...")
            answer_input.setMaximumHeight(72)
            answer_input.setMinimumHeight(48)
            answer_input.textChanged.connect(self._check_all_answered)
            q_layout.addWidget(answer_input)

            self._scroll_layout.insertWidget(self._scroll_layout.count() - 1, q_frame)
            self._qa_widgets.append((q, answer_input, q_frame))

    def _check_all_answered(self):
        all_done = all(
            w.toPlainText().strip()
            for _, w, _ in self._qa_widgets
        )
        if all_done:
            self.all_answered.emit()
            # 全部回答后清除高亮
            self.clear_highlights()

    def get_answered_count(self) -> int:
        return sum(1 for _, w, _ in self._qa_widgets if w.toPlainText().strip())

    def get_total_count(self) -> int:
        return len(self._qa_widgets)

    def get_qa_pairs(self) -> list:
        """获取问答对列表，传给 AI-Call-2"""
        pairs = []
        for q_data, answer_input, _ in self._qa_widgets:
            pairs.append({
                "question_id": q_data.get("id", ""),
                "dimension":   q_data.get("dimension", ""),
                "question":    q_data.get("question", ""),
                "rationale":   q_data.get("rationale", ""),
                "answer":      answer_input.toPlainText().strip(),
            })
        return pairs

    def highlight_unanswered(self):
        """
        将未回答的问题边框标红，并自动滚动到第一个未回答的问题。
        用户填写后边框自动恢复。
        """
        first_unanswered = None
        for q_data, answer_input, frame in self._qa_widgets:
            if not answer_input.toPlainText().strip():
                # 红色边框
                frame.setStyleSheet(
                    "QFrame { border: 2px solid #e74c3c; border-radius: 6px; "
                    "background-color: #fff5f5; }"
                )
                if first_unanswered is None:
                    first_unanswered = frame
            else:
                # 正常样式
                frame.setStyleSheet(
                    "QFrame { border: 1px solid #dcdde1; border-radius: 6px; "
                    "background-color: #fafafa; }"
                )
        # 滚动到第一个未回答的问题
        if first_unanswered and self._scroll:
            self._scroll.ensureWidgetVisible(first_unanswered, 0, 20)

    def clear_highlights(self):
        """清除所有高亮（全部回答完成时调用）"""
        for _, _, frame in self._qa_widgets:
            frame.setStyleSheet(
                "QFrame { border: 1px solid #27ae60; border-radius: 6px; "
                "background-color: #f0fff4; }"
            )

    def set_qa_pairs(self, pairs: list):
        """从保存的项目中恢复问答对（加载项目时调用）"""
        questions = []
        answers = {}
        for p in pairs:
            questions.append({
                "id":        p.get("question_id", ""),
                "dimension": p.get("dimension", ""),
                "question":  p.get("question", ""),
                "rationale": p.get("rationale", ""),
            })
            answers[p.get("question_id", "")] = p.get("answer", "")

        self.set_questions(questions)

        for q_data, answer_input, _ in self._qa_widgets:
            ans = answers.get(q_data.get("id", ""), "")
            if ans:
                answer_input.setPlainText(ans)
