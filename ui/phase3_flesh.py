# ============================================================
# ui/phase3_flesh.py
# Phase 3: 血肉 — 迭代核心：盲视变异 + ITE + RAG
# ============================================================

import json
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QSplitter, QComboBox, QScrollArea,
    QTextEdit, QGroupBox, QMessageBox, QRadioButton,
    QButtonGroup, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QFrame,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor

from env import (
    SYSTEM_PROMPT_VARIATION_FRAME, USER_PROMPT_VARIATION,
    SYSTEM_PROMPT_ITE, SYSTEM_PROMPT_RAG_CHECK,
    SUGGESTED_TEMPERATURES,
)
from services.worker import VariationWorker, ITEWorker, RAGWorker
from services.rag_controller import rag_controller
from ui.widgets.ai_settings_panel import AISettingsPanel
from ui.widgets.prompt_viewer import PromptViewer
from ui.widgets.persona_selector import PersonaSelector
from ui.widgets.beat_card import BeatCard


class Phase3Flesh(QWidget):
    """
    Phase 3: 血肉填充迭代界面。

    子视图 3a: 盲视变异 + Beat 卡片选择 + 详情编辑
    子视图 3b: ITE 分析 + RAG 审查 + 下一步决策

    信号:
        phase_completed: 所有节点处理完毕 -> Phase 4
        go_back_to_skeleton: 返回 Phase 2
        status_message: 状态栏消息
    """

    phase_completed     = Signal()
    go_back_to_skeleton = Signal()
    status_message      = Signal(str)

    def __init__(self, project_data, parent=None):
        super().__init__(parent)
        self.project_data         = project_data
        self._worker              = None
        self._variation_results   = []
        self._selected_persona_key = None
        self._confirmed_beat_data = None
        self._setup_ui()

    # ------------------------------------------------------------------ #
    # UI 构建
    # ------------------------------------------------------------------ #
    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(6)

        # 顶部：节点选择 + 进度
        top = QHBoxLayout()
        top.addWidget(QLabel("当前节点:"))
        self._node_combo = QComboBox()
        self._node_combo.setMinimumWidth(280)
        self._node_combo.currentIndexChanged.connect(self._on_node_changed)
        top.addWidget(self._node_combo)
        top.addWidget(QLabel("   进度:"))
        self._progress_label = QLabel("")
        self._progress_label.setStyleSheet("font-size: 13px; letter-spacing: 3px;")
        top.addWidget(self._progress_label)
        top.addStretch()
        root.addLayout(top)

        # 子视图 3a
        self._view_var = QWidget()
        self._build_variation_view(self._view_var)

        # 子视图 3b
        self._view_ana = QWidget()
        self._build_analysis_view(self._view_ana)

        self._view_var.setVisible(True)
        self._view_ana.setVisible(False)
        root.addWidget(self._view_var)
        root.addWidget(self._view_ana)

        # 底部全局回退
        back_row = QHBoxLayout()
        btn_back_skel = QPushButton("<- 返回骨架 (整体重生)")
        btn_back_skel.clicked.connect(self.go_back_to_skeleton.emit)
        back_row.addWidget(btn_back_skel)
        back_row.addStretch()
        root.addLayout(back_row)

    def _build_variation_view(self, parent: QWidget):
        vl = QVBoxLayout(parent)
        vl.setContentsMargins(0, 0, 0, 0)

        self._persona_selector = PersonaSelector()
        vl.addWidget(self._persona_selector)

        self._ai_settings_var = AISettingsPanel(
            suggested_temp=SUGGESTED_TEMPERATURES["variation"]
        )
        vl.addWidget(self._ai_settings_var)

        self._prompt_viewer_var = PromptViewer()
        self._prompt_viewer_var.set_prompt(SYSTEM_PROMPT_VARIATION_FRAME, USER_PROMPT_VARIATION)
        vl.addWidget(self._prompt_viewer_var)

        self._btn_generate = QPushButton("开始生成变体")
        self._btn_generate.setMinimumHeight(38)
        self._btn_generate.setStyleSheet(
            "QPushButton{background:#2980b9;color:white;font-weight:bold;"
            "border-radius:5px;border:none;}"
            "QPushButton:hover{background:#1f6da8;}"
            "QPushButton:disabled{background:#bdc3c7;color:#888;}"
        )
        self._btn_generate.clicked.connect(self._on_generate)
        vl.addWidget(self._btn_generate)

        # 卡片区 + 详情编辑
        result_splitter = QSplitter(Qt.Horizontal)

        cards_container = QWidget()
        self._cards_layout = QHBoxLayout(cards_container)
        self._cards_layout.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self._cards_layout.setSpacing(10)

        cards_scroll = QScrollArea()
        cards_scroll.setWidgetResizable(True)
        cards_scroll.setWidget(cards_container)
        cards_scroll.setMinimumHeight(200)
        cards_scroll.setFrameShape(QFrame.NoFrame)
        result_splitter.addWidget(cards_scroll)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(QLabel("选中方案详情 (可直接编辑 JSON):"))
        self._detail_edit = QTextEdit()
        self._detail_edit.setPlaceholderText("选择左侧卡片后，完整 JSON 显示在此，可手动修改。")
        self._detail_edit.setStyleSheet(
            "QTextEdit{font-family:Consolas,monospace;font-size:11px;"
            "border:1px solid #dcdde1;border-radius:4px;}"
        )
        rl.addWidget(self._detail_edit)
        result_splitter.addWidget(right)
        result_splitter.setSizes([460, 360])
        vl.addWidget(result_splitter, 1)

        var_btn_row = QHBoxLayout()
        self._btn_regen_node = QPushButton("重新生成本节点")
        self._btn_regen_node.clicked.connect(self._on_generate)
        var_btn_row.addWidget(self._btn_regen_node)

        self._btn_skip = QPushButton("跳过此节点")
        self._btn_skip.clicked.connect(self._on_skip_node)
        var_btn_row.addWidget(self._btn_skip)

        var_btn_row.addStretch()

        self._btn_confirm = QPushButton("确认此 Beat ->")
        self._btn_confirm.setMinimumHeight(36)
        self._btn_confirm.setEnabled(False)
        self._btn_confirm.setStyleSheet(
            "QPushButton{background:#27ae60;color:white;font-weight:bold;"
            "border-radius:5px;border:none;}"
            "QPushButton:hover{background:#229954;}"
            "QPushButton:disabled{background:#bdc3c7;color:#888;}"
        )
        self._btn_confirm.clicked.connect(self._on_confirm_beat)
        var_btn_row.addWidget(self._btn_confirm)
        vl.addLayout(var_btn_row)

    def _build_analysis_view(self, parent: QWidget):
        al = QVBoxLayout(parent)
        al.setContentsMargins(0, 0, 0, 0)

        # ITE 结果
        ite_group = QGroupBox("ITE 因果分析结果 (AI-Call-5)")
        itl = QVBoxLayout(ite_group)
        self._ite_table = QTableWidget(0, 5)
        self._ite_table.setHorizontalHeaderLabels(["节点-事件", "ITE分数", "判定", "理由", "操作"])
        self._ite_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self._ite_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._ite_table.setMaximumHeight(180)
        itl.addWidget(self._ite_table)
        self._ite_warn_label = QLabel("")
        self._ite_warn_label.setWordWrap(True)
        self._ite_warn_label.setStyleSheet("color:#c0392b; font-size:11px;")
        itl.addWidget(self._ite_warn_label)
        self._ite_coherence_label = QLabel("")
        self._ite_coherence_label.setStyleSheet("font-weight:bold; font-size:12px;")
        itl.addWidget(self._ite_coherence_label)
        al.addWidget(ite_group)

        # RAG 结果
        rag_group = QGroupBox("RAG 一致性审查结果 (AI-Call-6)")
        rgl = QVBoxLayout(rag_group)
        self._rag_text = QTextEdit()
        self._rag_text.setReadOnly(True)
        self._rag_text.setMaximumHeight(130)
        self._rag_text.setStyleSheet(
            "QTextEdit{font-family:Consolas,monospace;font-size:11px;"
            "border:1px solid #dcdde1;border-radius:4px;}"
        )
        rgl.addWidget(self._rag_text)
        al.addWidget(rag_group)

        # 下一步决策
        next_group = QGroupBox("下一步操作")
        ngl = QVBoxLayout(next_group)
        self._radio_group = QButtonGroup(self)

        self._radio_next = QRadioButton("处理下一个待确认节点")
        self._radio_next.setChecked(True)
        self._radio_group.addButton(self._radio_next, 0)
        ngl.addWidget(self._radio_next)

        modify_row = QHBoxLayout()
        self._radio_modify = QRadioButton("返回修改指定节点:")
        self._radio_group.addButton(self._radio_modify, 1)
        modify_row.addWidget(self._radio_modify)
        self._modify_combo = QComboBox()
        self._modify_combo.setMinimumWidth(220)
        modify_row.addWidget(self._modify_combo)
        modify_row.addStretch()
        ngl.addLayout(modify_row)

        self._radio_reset = QRadioButton("返回骨架阶段 (整体重新生成)")
        self._radio_group.addButton(self._radio_reset, 2)
        ngl.addWidget(self._radio_reset)

        self._radio_done = QRadioButton("全部节点已确认 -> 进入锁定阶段")
        self._radio_group.addButton(self._radio_done, 3)
        ngl.addWidget(self._radio_done)

        al.addWidget(next_group)

        exec_row = QHBoxLayout()
        self._btn_re_analysis = QPushButton("重新分析当前 Beat")
        self._btn_re_analysis.clicked.connect(self._re_run_analysis)
        exec_row.addWidget(self._btn_re_analysis)
        exec_row.addStretch()
        self._btn_execute = QPushButton("执行 ->")
        self._btn_execute.setMinimumHeight(36)
        self._btn_execute.setStyleSheet(
            "QPushButton{background:#2980b9;color:white;font-weight:bold;"
            "border-radius:5px;border:none;}"
            "QPushButton:hover{background:#1f6da8;}"
        )
        self._btn_execute.clicked.connect(self._on_execute_next)
        exec_row.addWidget(self._btn_execute)
        al.addLayout(exec_row)

    # ------------------------------------------------------------------ #
    # 生命周期
    # ------------------------------------------------------------------ #
    def on_enter(self):
        self._refresh_node_combo()
        self._refresh_modify_combo()
        self._update_progress()
        self._show_var_view()

    def _show_var_view(self):
        self._view_var.setVisible(True)
        self._view_ana.setVisible(False)

    def _show_ana_view(self):
        self._view_var.setVisible(False)
        self._view_ana.setVisible(True)

    # ------------------------------------------------------------------ #
    # 节点选择 / 进度
    # ------------------------------------------------------------------ #
    def _refresh_node_combo(self):
        self._node_combo.blockSignals(True)
        self._node_combo.clear()
        first_pending = None
        for n in self.project_data.cpg_nodes:
            nid  = n.get("node_id", "")
            done = bool(self.project_data.confirmed_beats.get(nid))
            mark = "[OK] " if done else "[ ]  "
            self._node_combo.addItem(f"{mark}{nid}: {n.get('title','')}", nid)
            if first_pending is None and not done:
                first_pending = nid
        self._node_combo.blockSignals(False)

        if first_pending:
            for i in range(self._node_combo.count()):
                if self._node_combo.itemData(i) == first_pending:
                    self._node_combo.setCurrentIndex(i)
                    break

    def _refresh_modify_combo(self):
        self._modify_combo.clear()
        for n in self.project_data.cpg_nodes:
            nid  = n.get("node_id", "")
            done = bool(self.project_data.confirmed_beats.get(nid))
            mark = "[OK] " if done else "[ ]  "
            self._modify_combo.addItem(f"{mark}{nid}: {n.get('title','')}", nid)

    def _update_progress(self):
        cur = self._get_current_node_id()
        parts = []
        for n in self.project_data.cpg_nodes:
            nid = n.get("node_id", "")
            if self.project_data.confirmed_beats.get(nid):
                parts.append("[V]")
            elif nid == cur:
                parts.append("[>]")
            else:
                parts.append("[ ]")
        self._progress_label.setText("  ".join(parts))

    def _get_current_node_id(self) -> str:
        return self._node_combo.currentData() or ""

    def _get_current_node(self) -> dict:
        nid = self._get_current_node_id()
        return next(
            (n for n in self.project_data.cpg_nodes if n.get("node_id") == nid), {}
        )

    def _on_node_changed(self, _):
        self._update_progress()
        self._clear_cards()
        self._detail_edit.clear()
        self._selected_persona_key = None
        self._btn_confirm.setEnabled(False)

    # ------------------------------------------------------------------ #
    # AI-Call-4: 盲视变异
    # ------------------------------------------------------------------ #
    def _on_generate(self):
        node = self._get_current_node()
        if not node:
            QMessageBox.warning(self, "提示", "请先选择要处理的节点！")
            return
        selected_keys = self._persona_selector.get_selected_keys()
        if not selected_keys:
            QMessageBox.warning(self, "提示", "请至少选择一个人格！")
            return

        self._clear_cards()
        self._variation_results = []
        self._selected_persona_key = None
        self._btn_confirm.setEnabled(False)
        self._set_busy_var(True)

        self._worker = VariationWorker(
            sparkle=self.project_data.sparkle,
            world_variables=self.project_data.world_variables,
            cpg_nodes=self.project_data.cpg_nodes,
            cpg_edges=self.project_data.cpg_edges,
            target_node=node,
            confirmed_beats=self.project_data.confirmed_beats,
            selected_persona_keys=selected_keys,
            ai_params=self._ai_settings_var.get_all_settings(),
            characters=self.project_data.characters,         # V2: 注入角色
        )
        self._worker.progress.connect(self.status_message)
        self._worker.beat_ready.connect(self._on_beat_ready)
        self._worker.finished.connect(self._on_all_done)
        self._worker.error.connect(self._on_error_var)
        self._worker.start()

    def _on_beat_ready(self, result: dict):
        self._variation_results.append(result)
        if result.get("beat"):
            from env import PERSONA_DEFINITIONS
            pname = PERSONA_DEFINITIONS.get(result["persona_key"], {}).get("name", result["persona_key"])
            card = BeatCard(
                persona_key=result["persona_key"],
                persona_name=pname,
                beat_data=result["beat"],
            )
            card.selected.connect(self._on_card_selected)
            self._cards_layout.addWidget(card)
        else:
            self.status_message.emit(
                f"[警告] 人格 {result['persona_key']} 生成失败: {result.get('error','')}"
            )

    def _on_all_done(self, summary: dict):
        self._set_busy_var(False)
        self.status_message.emit(
            f"变体生成完成: {summary.get('success',0)}/{summary.get('total',0)} 成功，请选择方案"
        )

    def _on_card_selected(self, persona_key: str):
        self._selected_persona_key = persona_key
        for r in self._variation_results:
            if r["persona_key"] == persona_key and r.get("beat"):
                self._detail_edit.setPlainText(
                    json.dumps(r["beat"], ensure_ascii=False, indent=2)
                )
                break
        self._btn_confirm.setEnabled(True)

    def _clear_cards(self):
        while self._cards_layout.count():
            item = self._cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _on_skip_node(self):
        nid = self._get_current_node_id()
        if nid:
            self.status_message.emit(f"已跳过节点 {nid}")
            self._refresh_node_combo()
            self._update_progress()

    # ------------------------------------------------------------------ #
    # 确认 Beat -> ITE + RAG
    # ------------------------------------------------------------------ #
    def _on_confirm_beat(self):
        if not self._selected_persona_key:
            QMessageBox.warning(self, "提示", "请先选择一个方案！")
            return
        raw = self._detail_edit.toPlainText().strip()
        try:
            beat_data = json.loads(raw)
        except json.JSONDecodeError as e:
            QMessageBox.critical(self, "JSON 格式错误", f"编辑器中的 JSON 有误:\n{e}")
            return

        nid = self._get_current_node_id()
        self._confirmed_beat_data = beat_data
        self.project_data.confirmed_beats[nid] = beat_data
        self.project_data.push_history("confirm_beat", nid)

        try:
            rag_controller.index_beat(nid, beat_data)
        except Exception:
            pass

        self._refresh_node_combo()
        self._refresh_modify_combo()
        self._update_progress()

        # V2 优化：确认 Beat 后直接跳到下一个节点，ITE/RAG 改为可选
        all_done = all(
            self.project_data.confirmed_beats.get(n.get("node_id"))
            for n in self.project_data.cpg_nodes
        )
        if all_done:
            reply = QMessageBox.question(
                self, "全部完成",
                "所有节点已确认！\n"
                "是否先运行 [ITE因果分析 + RAG一致性审查] （可选），\n"
                "还是直接进入剥本扩写阶段？",
                QMessageBox.Yes | QMessageBox.No,
                defaultButton=QMessageBox.No,
            )
            if reply == QMessageBox.Yes:
                self._show_ana_view()
                self._ite_table.setRowCount(0)
                self._ite_warn_label.clear()
                self._ite_coherence_label.clear()
                self._rag_text.clear()
                self._btn_execute.setEnabled(False)
                self._run_ite()
            else:
                self.project_data.current_phase = "expansion"
                self.project_data.push_history("enter_expansion")
                self.phase_completed.emit()
        else:
            # 还有待处理节点，直接跳到变异视图
            self._clear_cards()
            self._detail_edit.clear()
            self._selected_persona_key = None
            self._confirmed_beat_data = None
            self._btn_confirm.setEnabled(False)
            self._show_var_view()
            pending = self.project_data.get_pending_nodes()
            if pending:
                next_nid = pending[0].get("node_id", "")
                for i in range(self._node_combo.count()):
                    if self._node_combo.itemData(i) == next_nid:
                        self._node_combo.setCurrentIndex(i)
                        break
            self.status_message.emit(f"✅ {nid} 已确认，请继续处理下一个节点")

    def _run_ite(self):
        all_confirmed = {k: v for k, v in self.project_data.confirmed_beats.items() if v}
        if not all_confirmed:
            self._run_rag()
            return

        self._worker = ITEWorker(
            finale_condition=self.project_data.finale_condition,
            confirmed_beats=all_confirmed,
            cpg_edges=self.project_data.cpg_edges,
            ai_params=self._ai_settings_var.get_all_settings(),
        )
        self._worker.progress.connect(self.status_message)
        self._worker.finished.connect(self._on_ite_done)
        self._worker.error.connect(
            lambda msg: (
                self.status_message.emit("[警告] ITE 失败(不影响流程): " + msg),
                self._run_rag(),
            )
        )
        self._worker.start()

    def _on_ite_done(self, result: dict):
        self.project_data.ite_results = result
        evals = result.get("event_evaluations", [])
        self._ite_table.setRowCount(len(evals))

        VERDICT_COLOR = {"关键": "#c0392b", "重要": "#e67e22", "普通": "#27ae60", "冗余": "#95a5a6"}
        for row, ev in enumerate(evals):
            ref     = f"{ev.get('node_id','')}-E{ev.get('event_id','')}"
            score   = ev.get("ite_score", 0.0)
            verdict = ev.get("verdict", "")
            color   = VERDICT_COLOR.get(verdict, "#333")

            self._ite_table.setItem(row, 0, QTableWidgetItem(ref))
            si = QTableWidgetItem(f"{score:.3f}")
            si.setForeground(QColor(color))
            self._ite_table.setItem(row, 1, si)
            vi = QTableWidgetItem(verdict)
            vi.setForeground(QColor(color))
            self._ite_table.setItem(row, 2, vi)
            self._ite_table.setItem(row, 3, QTableWidgetItem(ev.get("reasoning", "")))

            if verdict == "冗余":
                prune_btn = QPushButton("剔除")
                prune_btn.setFixedHeight(24)
                eid = ev.get("event_id", "")
                bid = ev.get("node_id", "")
                prune_btn.clicked.connect(lambda _checked, b=bid, e=eid: self._prune_event(b, e))
                self._ite_table.setCellWidget(row, 4, prune_btn)

        warnings = result.get("structural_warnings", [])
        self._ite_warn_label.setText("\n".join(f"[警告] {w}" for w in warnings))

        coherence = result.get("full_story_coherence", 0.0)
        c = "#27ae60" if coherence >= 0.7 else "#e67e22" if coherence >= 0.5 else "#c0392b"
        self._ite_coherence_label.setText(
            f"<span style='color:{c};font-size:14px;font-weight:bold;'>"
            f"整体连贯度: {coherence:.0%}</span>"
        )
        self._ite_coherence_label.setTextFormat(Qt.RichText)
        self.status_message.emit(f"ITE 完成，{len(evals)} 个事件已评估")
        self._run_rag()

    def _prune_event(self, node_id: str, event_id):
        beat = self.project_data.confirmed_beats.get(node_id)
        if not beat:
            return
        for ev in beat.get("causal_events", []):
            if str(ev.get("event_id")) == str(event_id):
                ev["is_pruned"] = True
                break
        self.status_message.emit(f"事件 {node_id}-E{event_id} 已标记为剔除")

    def _run_rag(self):
        if not self._confirmed_beat_data:
            self._btn_execute.setEnabled(True)
            return

        self._worker = RAGWorker(
            new_beat=self._confirmed_beat_data,
            world_variables=self.project_data.world_variables,
            confirmed_beats={k: v for k, v in self.project_data.confirmed_beats.items() if v},
            ai_params={
                "temperature": SUGGESTED_TEMPERATURES["rag_check"],
                "top_p": 0.9, "top_k": 40, "max_tokens": 4096,
            },
        )
        self._worker.progress.connect(self.status_message)
        self._worker.finished.connect(self._on_rag_done)
        self._worker.error.connect(
            lambda msg: (
                self.status_message.emit("[警告] RAG 失败(不影响流程): " + msg),
                self._btn_execute.setEnabled(True),
            )
        )
        self._worker.start()

    def _on_rag_done(self, result: dict):
        nid = self._get_current_node_id()
        self.project_data.rag_results[nid] = result

        conflicts = result.get("conflicts", [])
        passed    = result.get("pass_count", 0)
        total     = result.get("total_checks", 0)
        failed    = result.get("fail_count", 0)

        if not conflicts:
            self._rag_text.setPlainText(f"通过全部 {total} 项检查，无逻辑矛盾。")
        else:
            SEV = {"critical": "[严重]", "warning": "[警告]", "info": "[提示]"}
            lines = [f"通过 {passed}/{total} 项检查，发现 {failed} 处矛盾:\n"]
            for c in conflicts:
                sev = SEV.get(c.get("severity", ""), "")
                lines.append(
                    f"{sev} [{c.get('conflict_type','')}]\n"
                    f"  问题: {c.get('new_beat_event','')}\n"
                    f"  矛盾: {c.get('contradicts_source','')}\n"
                    f"  建议: {c.get('suggestion','')}\n"
                )
            self._rag_text.setPlainText("\n".join(lines))
            if sum(1 for c in conflicts if c.get("severity") == "critical"):
                QMessageBox.warning(
                    self, "严重矛盾",
                    "RAG 审查发现严重逻辑矛盾！建议返回修改该节点。\n详情见审查结果。",
                )

        all_done = all(
            self.project_data.confirmed_beats.get(n.get("node_id"))
            for n in self.project_data.cpg_nodes
        )
        if all_done:
            self._radio_done.setChecked(True)

        self._btn_execute.setEnabled(True)
        self.status_message.emit(f"RAG 审查完成: 通过 {passed}/{total}，矛盾 {failed}")

    def _re_run_analysis(self):
        if not self._confirmed_beat_data:
            QMessageBox.warning(self, "提示", "请先确认一个 Beat！")
            return
        self._btn_execute.setEnabled(False)
        self._ite_table.setRowCount(0)
        self._rag_text.clear()
        self._run_ite()

    # ------------------------------------------------------------------ #
    # 下一步决策
    # ------------------------------------------------------------------ #
    def _on_execute_next(self):
        bid = self._radio_group.checkedId()

        if bid == 0:
            self._refresh_node_combo()
            self._update_progress()
            self._clear_cards()
            self._detail_edit.clear()
            self._selected_persona_key = None
            self._confirmed_beat_data  = None
            self._btn_confirm.setEnabled(False)
            self._show_var_view()

        elif bid == 1:
            target = self._modify_combo.currentData()
            if target:
                self.project_data.confirmed_beats[target] = None
                self.project_data.push_history("reset_beat", target)
                for i in range(self._node_combo.count()):
                    if self._node_combo.itemData(i) == target:
                        self._node_combo.setCurrentIndex(i)
                        break
            self._refresh_node_combo()
            self._refresh_modify_combo()
            self._update_progress()
            self._clear_cards()
            self._detail_edit.clear()
            self._selected_persona_key = None
            self._confirmed_beat_data  = None
            self._btn_confirm.setEnabled(False)
            self._show_var_view()

        elif bid == 2:
            self.go_back_to_skeleton.emit()

        elif bid == 3:
            self.project_data.current_phase = "expansion"
            self.project_data.push_history("enter_expansion")
            self.phase_completed.emit()

    # ------------------------------------------------------------------ #
    # 工具
    # ------------------------------------------------------------------ #
    def _set_busy_var(self, busy: bool):
        self._btn_generate.setEnabled(not busy)
        self._btn_regen_node.setEnabled(not busy)
        self._btn_skip.setEnabled(not busy)
        if self._selected_persona_key:
            self._btn_confirm.setEnabled(not busy)
        self._btn_generate.setText("处理中..." if busy else "开始生成变体")

    def _on_error_var(self, msg: str):
        self._set_busy_var(False)
        QMessageBox.critical(self, "AI 调用失败", msg)
        self.status_message.emit("错误: " + msg)
