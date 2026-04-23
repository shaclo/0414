# ============================================================
# ui/widgets/qa_panel.py
# 苏格拉底问答面板 — Phase 1 使用
# ============================================================

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTextEdit, QScrollArea, QFrame, QPushButton, QComboBox,
    QMessageBox,
)
from PySide6.QtCore import Qt, Signal

from services.answer_strategy_manager import answer_strategy_manager


class QAPanel(QWidget):
    """
    苏格拉底问答面板。
    动态展示 AI 生成的问题列表，用户逐一填写回答。

    信号:
        all_answered:          所有问题都已回答时发出
        auto_answer_requested: 用户点击"AI 自动回答"时发出，携带选中的策略 key
    """

    all_answered = Signal()
    auto_answer_requested = Signal(str)   # strategy_key

    def __init__(self, parent=None):
        super().__init__(parent)
        self._qa_widgets = []  # [(question_data, answer_input, frame)]
        self._scroll = None
        self._questions_raw = []  # 保存原始问题列表供 Worker 使用
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # ── 标题行 ──
        header = QLabel("问答区 — 请逐一回答以下问题")
        header.setStyleSheet("font-weight: bold; padding: 4px 0;")
        layout.addWidget(header)

        # ── 工具栏 ──
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)

        # 风格策略下拉框
        toolbar.addWidget(QLabel("回答风格:"))
        self._strategy_combo = QComboBox()
        self._strategy_combo.setMinimumWidth(150)
        self._strategy_combo.setToolTip("选择 AI 自动回答的风格策略")
        self._refresh_strategy_combo()
        toolbar.addWidget(self._strategy_combo)

        # AI 自动回答按钮
        self._btn_auto = QPushButton("🤖 AI 自动回答")
        self._btn_auto.setToolTip("AI 根据梗概和风格策略自动填写所有答案（含逻辑校验）")
        self._btn_auto.setStyleSheet(
            "QPushButton{background:#2980b9;color:white;border:none;"
            "border-radius:4px;padding:4px 12px;font-weight:bold;}"
            "QPushButton:hover{background:#1f6da8;}"
            "QPushButton:disabled{background:#bdc3c7;color:#888;}"
        )
        self._btn_auto.clicked.connect(self._on_auto_answer_clicked)
        toolbar.addWidget(self._btn_auto)

        # 一键清空按钮
        self._btn_clear = QPushButton("🗑️ 清空所有答案")
        self._btn_clear.setToolTip("清空所有回答输入框")
        self._btn_clear.setStyleSheet(
            "QPushButton{background:#e74c3c;color:white;border:none;"
            "border-radius:4px;padding:4px 12px;}"
            "QPushButton:hover{background:#c0392b;}"
            "QPushButton:disabled{background:#bdc3c7;color:#888;}"
        )
        self._btn_clear.clicked.connect(self.clear_all_answers)
        toolbar.addWidget(self._btn_clear)

        toolbar.addStretch()
        layout.addLayout(toolbar)

        # ── 滚动问答区 ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        self._scroll_content = QWidget()
        self._scroll_layout = QVBoxLayout(self._scroll_content)
        self._scroll_layout.setSpacing(12)
        self._scroll_layout.addStretch()
        scroll.setWidget(self._scroll_content)
        self._scroll = scroll
        layout.addWidget(scroll)

    # ------------------------------------------------------------------ #
    # 公共接口
    # ------------------------------------------------------------------ #

    def refresh_strategies(self):
        """刷新风格下拉框（策略配置更新后调用）"""
        self._refresh_strategy_combo()

    def _refresh_strategy_combo(self):
        """从 answer_strategy_manager 重建策略下拉框"""
        current_key = self._strategy_combo.currentData() if self._strategy_combo.count() > 0 else None
        self._strategy_combo.blockSignals(True)
        self._strategy_combo.clear()
        for key, info in answer_strategy_manager.get_all().items():
            self._strategy_combo.addItem(info["label"], key)
        # 恢复之前选中的 key
        if current_key:
            for i in range(self._strategy_combo.count()):
                if self._strategy_combo.itemData(i) == current_key:
                    self._strategy_combo.setCurrentIndex(i)
                    break
        self._strategy_combo.blockSignals(False)


    def set_questions(self, questions: list):
        """
        设置问题列表（AI-Call-1 返回后调用）。

        Args:
            questions: [{id, dimension, question, rationale}, ...]
        """
        self._questions_raw = list(questions)

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
            dim_label.setStyleSheet("font-weight: bold; color: #2980b9;")
            q_layout.addWidget(dim_label)

            # 问题内容
            question_label = QLabel(q.get("question", ""))
            question_label.setWordWrap(True)
            question_label.setStyleSheet("color: #2c3e50;")
            q_layout.addWidget(question_label)

            # 追问理由（灰色小字）
            rationale = q.get("rationale", "")
            if rationale:
                rationale_label = QLabel(f"[追问依据] {rationale}")
                rationale_label.setWordWrap(True)
                rationale_label.setStyleSheet(
                    "color: #95a5a6; font-style: italic;"
                )
                q_layout.addWidget(rationale_label)

            # 回答输入框（加高：min 80, max 120）
            answer_input = QTextEdit()
            answer_input.setPlaceholderText("请输入你的回答...")
            answer_input.setMinimumHeight(80)
            answer_input.setMaximumHeight(120)
            answer_input.textChanged.connect(self._check_all_answered)
            q_layout.addWidget(answer_input)

            self._scroll_layout.insertWidget(self._scroll_layout.count() - 1, q_frame)
            self._qa_widgets.append((q, answer_input, q_frame))

        # 有问题才开放按钮
        has_q = bool(questions)
        self._btn_auto.setEnabled(has_q)
        self._btn_clear.setEnabled(has_q)

    def get_questions(self) -> list:
        """返回原始问题列表（供 AutoAnswerWorker 使用）"""
        return list(self._questions_raw)

    def set_answer(self, question_id, text: str):
        """外部设置某题的答案（自动回答结果填入）"""
        for q_data, answer_input, _ in self._qa_widgets:
            if q_data.get("id") == question_id:
                answer_input.setPlainText(text)
                break

    def clear_all_answers(self):
        """清空所有答案输入框（一键清空）"""
        if not self._qa_widgets:
            return
        reply = QMessageBox.question(
            self, "确认清空",
            "确定要清空所有答案吗？",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        for _, answer_input, frame in self._qa_widgets:
            answer_input.clear()
            frame.setStyleSheet(
                "QFrame { border: 1px solid #dcdde1; border-radius: 6px; "
                "background-color: #fafafa; }"
            )

    def set_auto_answer_busy(self, busy: bool):
        """AI 回答进行中时禁用按钮"""
        self._btn_auto.setEnabled(not busy)
        self._btn_auto.setText("⏳ 生成中…" if busy else "🤖 AI 自动回答")
        self._btn_clear.setEnabled(not busy)

    # ------------------------------------------------------------------ #
    # 内部槽
    # ------------------------------------------------------------------ #

    def _on_auto_answer_clicked(self):
        strategy_key = self._strategy_combo.currentData() or "realistic"
        self.auto_answer_requested.emit(strategy_key)

    def _check_all_answered(self):
        all_done = all(
            w.toPlainText().strip()
            for _, w, _ in self._qa_widgets
        )
        if all_done:
            self.all_answered.emit()
            self.clear_highlights()

    # ------------------------------------------------------------------ #
    # 只读统计
    # ------------------------------------------------------------------ #

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
        """将未回答的问题边框标红，并自动滚动到第一个。"""
        first_unanswered = None
        for q_data, answer_input, frame in self._qa_widgets:
            if not answer_input.toPlainText().strip():
                frame.setStyleSheet(
                    "QFrame { border: 2px solid #e74c3c; border-radius: 6px; "
                    "background-color: #fff5f5; }"
                )
                if first_unanswered is None:
                    first_unanswered = frame
            else:
                frame.setStyleSheet(
                    "QFrame { border: 1px solid #dcdde1; border-radius: 6px; "
                    "background-color: #fafafa; }"
                )
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
