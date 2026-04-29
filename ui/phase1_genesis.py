# ============================================================
# ui/phase1_genesis.py
# Phase 1: 创世 — 种子输入 + 苏格拉底问答 + 世界观变量锁定
# ============================================================

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTextEdit, QPushButton, QSplitter, QMessageBox, QComboBox, QCheckBox
)
from PySide6.QtCore import Qt, Signal

from env import (
    SYSTEM_PROMPT_SOCRATIC, USER_PROMPT_SOCRATIC,
    SYSTEM_PROMPT_WORLD_EXTRACT, USER_PROMPT_WORLD_EXTRACT,
    SUGGESTED_TEMPERATURES,
)
from services.genre_manager import genre_manager
from services.worker import SocraticWorker, WorldExtractWorker, AutoAnswerWorker
from services.logger_service import app_logger
from services.rag_controller import rag_controller
from ui.widgets.ai_settings_panel import AISettingsPanel
from ui.widgets.prompt_viewer import PromptViewer
from ui.widgets.qa_panel import QAPanel
from ui.widgets.world_var_table import WorldVarTable


class Phase1Genesis(QWidget):
    """
    Phase 1: 创世阶段。

    流程:
      输入种子 -> [AI-Call-1] -> Q&A 逐一回答
      -> [AI-Call-2] 提炼世界观变量 -> 确认锁定 -> Phase 2

    信号:
        phase_completed: 世界观锁定后发出
        status_message:  状态栏消息
    """

    phase_completed = Signal(dict)
    status_message  = Signal(str)

    def __init__(self, project_data, parent=None):
        super().__init__(parent)
        self.project_data = project_data
        self._worker = None
        self._setup_ui()
        self._restore_state()

    # ------------------------------------------------------------------ #
    # UI
    # ------------------------------------------------------------------ #
    def _setup_ui(self):
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(16, 16, 16, 16)

        # ===== 画面 1-1: 种子输入 =====
        self._view_input = QWidget()
        il = QVBoxLayout(self._view_input)
        il.setSpacing(8)

        lbl = QLabel("请输入你的一句话小说:")
        lbl.setStyleSheet(" font-weight: bold;")
        il.addWidget(lbl)

        self._sparkle_input = QTextEdit()
        self._sparkle_input.setPlaceholderText(
            "例如：一个核战后的废土世界，少女意外得到了母亲留下的远古芯片……"
        )
        self._sparkle_input.setMinimumHeight(100)
        self._sparkle_input.setMaximumHeight(160)
        il.addWidget(self._sparkle_input)

        # 题材选择
        genre_row = QHBoxLayout()
        genre_row.addWidget(QLabel("题材类型:"))
        self._genre_combo = QComboBox()
        self._genre_combo.setMinimumWidth(200)
        all_genres = genre_manager.get_all()
        for key, preset in all_genres.items():
            self._genre_combo.addItem(preset.get("label", key), key)
        self._genre_combo.setCurrentIndex(max(0, len(all_genres) - 1))  # default: last (custom)
        self._genre_combo.currentIndexChanged.connect(self._on_genre_changed)
        genre_row.addWidget(self._genre_combo)
        default_desc = genre_manager.get("custom").get("description", "") if genre_manager.get("custom") else ""
        self._genre_desc = QLabel(default_desc)
        self._genre_desc.setStyleSheet("color: #7f8c8d;")
        genre_row.addWidget(self._genre_desc, 1)
        il.addLayout(genre_row)

        self._has_cp_checkbox = QCheckBox("本剧本含男女主主线（启用 CP 互动模板）")
        self._has_cp_checkbox.setChecked(False)
        il.addWidget(self._has_cp_checkbox)

        self._ai_settings_1 = AISettingsPanel(
            suggested_temp=SUGGESTED_TEMPERATURES["socratic"]
        )
        il.addWidget(self._ai_settings_1)

        self._prompt_viewer_1 = PromptViewer()
        self._prompt_viewer_1.set_prompt(SYSTEM_PROMPT_SOCRATIC, USER_PROMPT_SOCRATIC)
        il.addWidget(self._prompt_viewer_1)

        self._btn_start = QPushButton("开始苏格拉底盘问 ->")
        self._btn_start.setMinimumHeight(44)
        self._btn_start.setStyleSheet(
            "QPushButton{background:#2980b9;color:white;font-weight:bold;"
            "border-radius:5px;border:none;}"
            "QPushButton:hover{background:#1f6da8;}"
            "QPushButton:disabled{background:#bdc3c7;color:#888;}"
        )
        self._btn_start.clicked.connect(self._on_start_socratic)
        il.addWidget(self._btn_start)
        il.addStretch()

        # ===== 画面 1-2: 问答 + 变量表 =====
        self._view_qa = QWidget()
        ql = QVBoxLayout(self._view_qa)
        ql.setSpacing(8)

        splitter = QSplitter(Qt.Horizontal)
        self._qa_panel = QAPanel()
        splitter.addWidget(self._qa_panel)
        self._var_table = WorldVarTable()
        splitter.addWidget(self._var_table)
        splitter.setSizes([600, 400])
        ql.addWidget(splitter, 1)

        # 连接自动回答信号
        self._qa_panel.auto_answer_requested.connect(self._on_auto_answer)

        self._ai_settings_2 = AISettingsPanel(
            suggested_temp=SUGGESTED_TEMPERATURES["world_extract"]
        )
        ql.addWidget(self._ai_settings_2)

        self._prompt_viewer_2 = PromptViewer()
        self._prompt_viewer_2.set_prompt(SYSTEM_PROMPT_WORLD_EXTRACT, USER_PROMPT_WORLD_EXTRACT)
        ql.addWidget(self._prompt_viewer_2)

        btn_row = QHBoxLayout()
        self._btn_back = QPushButton("<- 重新输入种子")
        self._btn_back.clicked.connect(self._on_back_to_input)
        btn_row.addWidget(self._btn_back)

        self._btn_re = QPushButton("重新盘问")
        self._btn_re.clicked.connect(self._on_start_socratic)
        btn_row.addWidget(self._btn_re)

        btn_row.addStretch()

        self._btn_extract = QPushButton("AI 提炼变量")
        self._btn_extract.setToolTip("调用 AI-Call-2 自动生成世界观变量表（也可手动填写）")
        self._btn_extract.clicked.connect(self._on_extract_variables)
        btn_row.addWidget(self._btn_extract)

        self._btn_lock = QPushButton("锁定世界观 ->")
        self._btn_lock.setMinimumHeight(36)
        self._btn_lock.setStyleSheet(
            "QPushButton{background:#27ae60;color:white;font-weight:bold;"
            "border-radius:5px;border:none;}"
            "QPushButton:hover{background:#229954;}"
            "QPushButton:disabled{background:#bdc3c7;color:#888;}"
        )
        self._btn_lock.clicked.connect(self._on_lock_world)
        btn_row.addWidget(self._btn_lock)
        ql.addLayout(btn_row)

        self._view_qa.setVisible(False)
        self._root.addWidget(self._view_input)
        self._root.addWidget(self._view_qa)

    def _restore_state(self):
        if self.project_data.sparkle:
            self._sparkle_input.setPlainText(self.project_data.sparkle)
        if self.project_data.qa_pairs:
            self._qa_panel.set_qa_pairs(self.project_data.qa_pairs)
            self._switch_to_qa()
        if self.project_data.world_variables:
            self._var_table.set_variables(self.project_data.world_variables)
        # 恢复题材选择
        genre = getattr(self.project_data, 'story_genre', 'custom')
        for i in range(self._genre_combo.count()):
            if self._genre_combo.itemData(i) == genre:
                self._genre_combo.setCurrentIndex(i)
                break
        self._has_cp_checkbox.setChecked(getattr(self.project_data, "has_cp_main_line", False))

    # ------------------------------------------------------------------ #
    # 视图切换
    # ------------------------------------------------------------------ #
    def _switch_to_qa(self):
        self._view_input.setVisible(False)
        self._view_qa.setVisible(True)

    def _on_back_to_input(self):
        self._view_qa.setVisible(False)
        self._view_input.setVisible(True)

    # ------------------------------------------------------------------ #
    # AI-Call-1: 苏格拉底盘问
    # ------------------------------------------------------------------ #
    def _on_start_socratic(self):
        sparkle = self._sparkle_input.toPlainText().strip()
        if not sparkle:
            QMessageBox.warning(self, "提示", "请先输入你的一句话小说！")
            return
        self.project_data.sparkle = sparkle
        self._set_busy(self._btn_start, True, "处理中...")

        ai_params = self._ai_settings_1.get_all_settings()
        genre_key = self._genre_combo.currentData() or "custom"

        # 构建实际发送的 User Prompt（替换占位符后）
        actual_user_prompt = USER_PROMPT_SOCRATIC.replace("{sparkle}", sparkle)

        app_logger.log_ai_call(
            module="创世-苏格拉底盘问",
            action="开始苏格拉底盘问 AI 调用",
            system_prompt=SYSTEM_PROMPT_SOCRATIC,
            user_prompt=actual_user_prompt,
            extra_params={
                "用户输入": sparkle,
                "题材": genre_key,
                "温度": ai_params.get("temperature"),
                "max_tokens": ai_params.get("max_tokens"),
            },
        )

        self._worker = SocraticWorker(sparkle, ai_params)
        self._worker.progress.connect(self.status_message)
        self._worker.finished.connect(self._on_socratic_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_socratic_done(self, result: dict):
        self._set_busy(self._btn_start, False, "开始苏格拉底盘问 ->")
        questions = result.get("questions", [])
        if not questions:
            QMessageBox.warning(self, "错误", "AI 返回的问题列表为空，请重试。")
            app_logger.warning("创世-苏格拉底盘问", "AI 返回问题列表为空")
            return
        self._qa_panel.set_questions(questions)
        self._switch_to_qa()
        self.status_message.emit(f"盘问完成，共 {len(questions)} 个问题")

        import json
        questions_detail = json.dumps(questions, ensure_ascii=False, indent=2)
        app_logger.log_ai_result(
            module="创世-苏格拉底盘问",
            action="苏格拉底盘问完成",
            result_summary=f"AI 生成了 {len(questions)} 个追问问题",
            result_detail=questions_detail,
        )

    # ------------------------------------------------------------------ #
    # AI-Call-1b/1c: 自动回答
    # ------------------------------------------------------------------ #
    def _on_auto_answer(self, strategy_key: str):
        """触发 AI 自动回答（按选定策略）"""
        sparkle = self.project_data.sparkle
        if not sparkle:
            sparkle = self._sparkle_input.toPlainText().strip()
        if not sparkle:
            QMessageBox.warning(self, "提示", "请先输入故事梗概并完成苏格拉底盘问！")
            return

        questions = self._qa_panel.get_questions()
        if not questions:
            QMessageBox.warning(self, "提示", "还没有问题，请先完成苏格拉底盘问！")
            return

        self._qa_panel.set_auto_answer_busy(True)
        ai_params = self._ai_settings_1.get_all_settings()

        self._worker = AutoAnswerWorker(sparkle, questions, strategy_key, ai_params)
        self._worker.progress.connect(self.status_message)
        self._worker.finished.connect(self._on_auto_answer_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_auto_answer_done(self, result: dict):
        """自动回答完成 — 填入答案"""
        self._qa_panel.set_auto_answer_busy(False)
        answers = result.get("answers", [])
        revised_count = result.get("revised_count", 0)
        strategy_label = result.get("strategy_label", "")

        for item in answers:
            self._qa_panel.set_answer(item["id"], item["answer"])

        msg = f"自动回答完成（{strategy_label}）：{len(answers)} 个问题"
        if revised_count:
            msg += f"，其中 {revised_count} 个答案经 AI 校验后修正"
        self.status_message.emit(msg)

    def _on_extract_variables(self):
        qa_pairs = self._qa_panel.get_qa_pairs()
        if not any(p.get("answer") for p in qa_pairs):
            QMessageBox.warning(self, "提示", "请至少回答一个问题！")
            return
        self._set_busy(self._btn_extract, True, "提炼中...")

        ai_params = self._ai_settings_2.get_all_settings()

        # 构建 Q&A 格式化文本
        qa_formatted_lines = []
        for p in qa_pairs:
            qa_formatted_lines.append(
                f"Q{p['question_id']} [{p.get('dimension', '')}]: {p['question']}\n"
                f"A: {p.get('answer', '（未回答）')}"
            )
        qa_pairs_formatted = "\n\n".join(qa_formatted_lines)

        actual_user_prompt = (
            USER_PROMPT_WORLD_EXTRACT
            .replace("{sparkle}", self.project_data.sparkle)
            .replace("{qa_pairs_formatted}", qa_pairs_formatted)
        )

        app_logger.log_ai_call(
            module="创世-世界观提炼",
            action="开始 AI 提炼世界观变量",
            system_prompt=SYSTEM_PROMPT_WORLD_EXTRACT,
            user_prompt=actual_user_prompt,
            extra_params={
                "种子": self.project_data.sparkle,
                "已回答问题数": sum(1 for p in qa_pairs if p.get("answer")),
                "温度": ai_params.get("temperature"),
                "max_tokens": ai_params.get("max_tokens"),
            },
        )

        self._worker = WorldExtractWorker(
            self.project_data.sparkle, qa_pairs,
            ai_params,
        )
        self._worker.progress.connect(self.status_message)
        self._worker.finished.connect(self._on_extract_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_extract_done(self, result: dict):
        self._set_busy(self._btn_extract, False, "AI 提炼变量")
        variables = result.get("variables", [])
        conflicts = result.get("conflicts", [])
        self._var_table.set_variables(variables, conflicts)
        self.project_data.story_title = result.get("story_title_suggestion", "")
        self.project_data.finale_condition = result.get("finale_condition", "")
        self.status_message.emit(
            f"变量提炼完成: {len(variables)} 个变量"
            + (f", {len(conflicts)} 处冲突" if conflicts else "")
        )

        import json
        result_detail = (
            f"故事标题建议: {result.get('story_title_suggestion', '')}"
            f"\n终局条件: {result.get('finale_condition', '')}"
            f"\n\n世界观变量:\n{json.dumps(variables, ensure_ascii=False, indent=2)}"
        )
        if conflicts:
            result_detail += f"\n\n冲突列表:\n{json.dumps(conflicts, ensure_ascii=False, indent=2)}"

        app_logger.log_ai_result(
            module="创世-世界观提炼",
            action="世界观变量提炼完成",
            result_summary=f"提炼出 {len(variables)} 个变量" + (f"，发现 {len(conflicts)} 处冲突" if conflicts else ""),
            result_detail=result_detail,
        )

        if conflicts:
            QMessageBox.warning(
                self, "发现设定冲突",
                f"AI 发现 {len(conflicts)} 处设定冲突，请在变量表中检查。\n"
                + "\n".join(f"- {c['description']}" for c in conflicts[:3]),
            )

    # ------------------------------------------------------------------ #
    # 锁定世界观
    # ------------------------------------------------------------------ #
    def _on_lock_world(self):
        qa_pairs  = self._qa_panel.get_qa_pairs()
        variables = self._var_table.get_variables()
        self.project_data.has_cp_main_line = self._has_cp_checkbox.isChecked()

        if not variables:
            reply = QMessageBox.question(
                self, "确认",
                "世界观变量表为空，建议先点击「AI 提炼变量」。\n确定直接锁定吗？",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply == QMessageBox.No:
                return

        unanswered = []
        for p in qa_pairs:
            if not p.get("answer"):
                qid = p.get("question_id", "?")
                dim = p.get("dimension", "")
                unanswered.append(f"  Q{qid} [{dim}]")

        if unanswered:
            # 高亮未回答的问题
            self._qa_panel.highlight_unanswered()

            detail = "\n".join(unanswered[:5])
            if len(unanswered) > 5:
                detail += f"\n  ...及其余 {len(unanswered)-5} 个"
            reply = QMessageBox.question(
                self, "确认",
                f"还有 {len(unanswered)} 个问题未回答：\n{detail}\n\n"
                f"未回答的问题已用红色标记，确定跳过锁定吗？",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply == QMessageBox.No:
                return

        self.project_data.qa_pairs         = qa_pairs
        self.project_data.world_variables  = variables
        self.project_data.story_genre      = self._genre_combo.currentData() or "custom"
        self.project_data.current_phase    = "skeleton"
        self.project_data.push_history("lock_world")

        try:
            rag_controller.index_world_variables(variables)
        except Exception:
            pass

        import json
        qa_summary = "\n".join(
            f"  Q{p.get('question_id','?')} [{p.get('dimension','')}]: {p.get('question','')}\n"
            f"  A: {p.get('answer','（未回答）')}"
            for p in qa_pairs
        )
        var_summary = json.dumps(variables, ensure_ascii=False, indent=2)
        app_logger.success(
            "创世-锁定世界观",
            f"世界观已锁定：{len(variables)} 个变量，故事标题：{self.project_data.story_title or '未命名'}",
            f"种子：{self.project_data.sparkle}"
            f"\n终局条件：{self.project_data.finale_condition}"
            f"\n题材：{self.project_data.story_genre}"
            f"\n\nQ&A 完整记录：\n{qa_summary}"
            f"\n\n世界观变量：\n{var_summary}",
        )

        self.phase_completed.emit({
            "sparkle":   self.project_data.sparkle,
            "variables": variables,
            "finale":    self.project_data.finale_condition,
        })

    # ------------------------------------------------------------------ #
    # 工具
    # ------------------------------------------------------------------ #
    def _set_busy(self, btn: QPushButton, busy: bool, label: str):
        btn.setEnabled(not busy)
        btn.setText(label)

    def _on_error(self, msg: str):
        self._set_busy(self._btn_start,   False, "开始苏格拉底盘问 ->")
        self._set_busy(self._btn_extract, False, "AI 提炼变量")
        self._qa_panel.set_auto_answer_busy(False)
        QMessageBox.critical(self, "AI 调用失败", msg)
        self.status_message.emit("错误: " + msg)
        app_logger.error("创世", f"AI 调用失败: {msg}")

    def _on_genre_changed(self, index: int):
        key = self._genre_combo.itemData(index)
        preset = genre_manager.get(key)
        self._genre_desc.setText(preset.get("description", ""))
        self.project_data.story_genre = key or "custom"
