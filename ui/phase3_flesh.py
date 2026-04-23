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
    QHeaderView, QAbstractItemView, QFrame, QSpinBox,
    QSizePolicy, QCheckBox,
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
from services.logger_service import app_logger
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
        self._batch_mode          = False
        self._batch_auto_confirm  = False
        self._batch_remaining     = 0
        self._batch_persona_key   = None
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
        self._progress_label.setStyleSheet(" letter-spacing: 3px;")
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
        root.addWidget(self._view_var, 1)
        root.addWidget(self._view_ana, 1)

    def _build_variation_view(self, parent: QWidget):
        vl = QVBoxLayout(parent)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(2)

        # 左右分割：左侧(控制+卡片) + 右侧(编辑视图)
        main_splitter = QSplitter(Qt.Horizontal)

        # === 左侧控制与卡片区 ===
        left_widget = QWidget()
        left_widget.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        cl = QVBoxLayout(left_widget)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(8)

        # 人格选择（直接添加，PersonaSelector 内部有自己的 QGroupBox）
        self._persona_selector = PersonaSelector()
        cl.addWidget(self._persona_selector)

        # AI 设置（直接添加，AISettingsPanel 内部有自己的 QGroupBox）
        self._ai_settings_var = AISettingsPanel(
            suggested_temp=SUGGESTED_TEMPERATURES["variation"]
        )
        cl.addWidget(self._ai_settings_var)

        # Prompt 查看器（可折叠，默认收起）
        prompt_group, prompt_inner = self._make_collapsible("📝 Prompt 模板预览", expanded=False)
        self._prompt_viewer_var = PromptViewer()
        self._prompt_viewer_var.set_prompt(SYSTEM_PROMPT_VARIATION_FRAME, USER_PROMPT_VARIATION)
        prompt_inner.addWidget(self._prompt_viewer_var)
        cl.addWidget(prompt_group)

        # 供应商多选（Beat 并行时随机分配）
        provider_group = QGroupBox("🔀 供应商分配（多选 = Beat 并行时随机分配）")
        provider_group.setStyleSheet(
            "QGroupBox{font-weight:bold;border:1px solid #dcdde1;"
            "border-radius:4px;margin-top:6px;padding-top:16px;}"
            "QGroupBox::title{subcontrol-origin:margin;left:8px;}"
        )
        self._provider_checks_layout = QHBoxLayout(provider_group)
        self._provider_checks_layout.setSpacing(12)
        self._provider_checkboxes: list = []
        self._refresh_provider_checkboxes()
        cl.addWidget(provider_group)

        # 生成按钮行
        gen_row = QHBoxLayout()
        self._btn_generate = QPushButton("开始生成变体")
        self._btn_generate.setMinimumHeight(38)
        self._btn_generate.setStyleSheet(
            "QPushButton{background:#2980b9;color:white;font-weight:bold;"
            "border-radius:5px;border:none;}"
            "QPushButton:hover{background:#1f6da8;}"
            "QPushButton:disabled{background:#bdc3c7;color:#888;}"
        )
        self._btn_generate.clicked.connect(self._on_generate)
        gen_row.addWidget(self._btn_generate)

        gen_row.addWidget(QLabel("  批量生成后续"))
        self._batch_count_spin = QSpinBox()
        self._batch_count_spin.setRange(1, 99)
        self._batch_count_spin.setValue(3)
        self._batch_count_spin.setSuffix(" 章")
        self._batch_count_spin.setToolTip("一键按当前人格配置生成后续多个章节")
        self._batch_count_spin.setMinimumWidth(80)
        gen_row.addWidget(self._batch_count_spin)

        self._btn_batch = QPushButton("🚀 一键批量生成")
        self._btn_batch.setMinimumHeight(38)
        self._btn_batch.setStyleSheet(
            "QPushButton{background:#8e44ad;color:white;font-weight:bold;"
            "border-radius:5px;border:none;}"
            "QPushButton:hover{background:#7d3c98;}"
            "QPushButton:disabled{background:#bdc3c7;color:#888;}"
        )
        self._btn_batch.clicked.connect(self._on_batch_generate)
        gen_row.addWidget(self._btn_batch)

        self._btn_autopilot = QPushButton("✈️ 全部自动生成（覆盖已有）")
        self._btn_autopilot.setMinimumHeight(38)
        self._btn_autopilot.setToolTip(
            "清空所有已生成内容后，从第1集开始全部重新生成。\n"
            "本功能只能选择一个人格！如果选择了多个人格，则默认只执行排序靠前的第一个生成。\n"
            "全程自动生成+自动确认，无需手动操作。"
        )
        self._btn_autopilot.setStyleSheet(
            "QPushButton{background:#e67e22;color:white;font-weight:bold;"
            "border-radius:5px;border:none;}"
            "QPushButton:hover{background:#d35400;}"
            "QPushButton:disabled{background:#bdc3c7;color:#888;}"
        )
        self._btn_autopilot.clicked.connect(self._on_autopilot_generate)
        gen_row.addWidget(self._btn_autopilot)

        gen_row.addStretch()
        cl.addLayout(gen_row)

        # === 卡片区 (放在左侧下方) ===
        cards_container = QWidget()
        self._cards_layout = QHBoxLayout(cards_container)
        self._cards_layout.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self._cards_layout.setSpacing(10)

        cards_scroll = QScrollArea()
        cards_scroll.setWidgetResizable(True)
        cards_scroll.setWidget(cards_container)
        cards_scroll.setMinimumHeight(150)
        cards_scroll.setFrameShape(QFrame.NoFrame)
        cl.addWidget(cards_scroll, 1)

        # === 右侧 文本与详情区 ===
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)

        # 视图切换按钮
        view_toggle_row = QHBoxLayout()
        self._btn_readable_view = QPushButton("📖 可读视图")
        self._btn_readable_view.setCheckable(True)
        self._btn_readable_view.setChecked(True)
        self._btn_readable_view.setStyleSheet(
            "QPushButton{padding:4px 12px;border:1px solid #3498db;border-radius:4px;"
            "color:#3498db;background:white;}"
            "QPushButton:checked{background:#3498db;color:white;}"
        )
        self._btn_readable_view.clicked.connect(lambda: self._switch_detail_view("readable"))
        view_toggle_row.addWidget(self._btn_readable_view)

        self._btn_json_view = QPushButton("📝 JSON 编辑")
        self._btn_json_view.setCheckable(True)
        self._btn_json_view.setChecked(False)
        self._btn_json_view.setStyleSheet(
            "QPushButton{padding:4px 12px;border:1px solid #95a5a6;border-radius:4px;"
            "color:#95a5a6;background:white;}"
            "QPushButton:checked{background:#95a5a6;color:white;}"
        )
        self._btn_json_view.clicked.connect(lambda: self._switch_detail_view("json"))
        view_toggle_row.addWidget(self._btn_json_view)

        view_toggle_row.addStretch()

        # 保存按钮
        self._btn_save_edit = QPushButton("💾 保存修改")
        self._btn_save_edit.setStyleSheet(
            "QPushButton{padding:4px 12px;border:1px solid #27ae60;border-radius:4px;"
            "color:#27ae60;background:white;}"
            "QPushButton:hover{background:#27ae60;color:white;}"
        )
        self._btn_save_edit.clicked.connect(self._on_save_edit)
        view_toggle_row.addWidget(self._btn_save_edit)

        rl.addLayout(view_toggle_row)

        # 可读视图（可编辑）
        self._readable_view = QTextEdit()
        self._readable_view.setReadOnly(False)  # 可编辑
        self._readable_view.setPlaceholderText("选择左侧卡片后，Beat 将以可读格式显示在此。可直接编辑内容，然后点击保存。")
        self._readable_view.setStyleSheet(
            "QTextEdit{font-family:'Microsoft YaHei','Noto Sans CJK SC',sans-serif;"
            "line-height:1.6;"
            "border:1px solid #dcdde1;border-radius:4px;padding:8px;"
            "background:#fafafa;}"
        )
        rl.addWidget(self._readable_view)

        # JSON 编辑视图（默认隐藏）
        self._detail_edit = QTextEdit()
        self._detail_edit.setPlaceholderText("选择左侧卡片后，完整 JSON 显示在此，可手动修改。")
        self._detail_edit.setStyleSheet(
            "QTextEdit{font-family:Consolas,monospace;"
            "border:1px solid #dcdde1;border-radius:4px;}"
        )
        self._detail_edit.setVisible(False)
        rl.addWidget(self._detail_edit)

        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setFrameShape(QScrollArea.NoFrame)
        left_scroll.setWidget(left_widget)

        main_splitter.addWidget(left_scroll)
        main_splitter.addWidget(right)
        main_splitter.setStretchFactor(0, 1)
        main_splitter.setStretchFactor(1, 1)
        main_splitter.setSizes([500, 500])

        vl.addWidget(main_splitter, 1)

        # 当前视图模式
        self._current_view_mode = "readable"

        var_btn_row = QHBoxLayout()
        
        btn_back_skel_var = QPushButton("<- 返回骨架 (整体重生)")
        btn_back_skel_var.clicked.connect(self.go_back_to_skeleton.emit)
        var_btn_row.addWidget(btn_back_skel_var)
        
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
        self._ite_warn_label.setStyleSheet("color:#c0392b;")
        itl.addWidget(self._ite_warn_label)
        self._ite_coherence_label = QLabel("")
        self._ite_coherence_label.setStyleSheet("font-weight:bold;")
        itl.addWidget(self._ite_coherence_label)
        al.addWidget(ite_group)

        # RAG 结果
        rag_group = QGroupBox("RAG 一致性审查结果 (AI-Call-6)")
        rgl = QVBoxLayout(rag_group)
        self._rag_text = QTextEdit()
        self._rag_text.setReadOnly(True)
        self._rag_text.setMaximumHeight(130)
        self._rag_text.setStyleSheet(
            "QTextEdit{font-family:Consolas,monospace;"
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
        
        btn_back_skel_ana = QPushButton("<- 返回骨架 (整体重生)")
        btn_back_skel_ana.clicked.connect(self.go_back_to_skeleton.emit)
        exec_row.addWidget(btn_back_skel_ana)
        
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
        self._readable_view.clear()
        self._selected_persona_key = None
        self._btn_confirm.setEnabled(False)
        self._variation_results = []

        # 加载已确认的 Beat 数据（如果存在）
        nid = self._get_current_node_id()
        if nid and nid in self.project_data.confirmed_beats:
            beat = self.project_data.confirmed_beats[nid]
            self._detail_edit.setPlainText(
                json.dumps(beat, ensure_ascii=False, indent=2)
            )
            # 如果有手动保存的可读文本，优先显示；否则格式化显示
            if isinstance(beat, dict) and beat.get("readable_text"):
                self._readable_view.setPlainText(beat["readable_text"])
            else:
                self._readable_view.setPlainText(
                    self._format_beat_readable(beat)
                )
            self.status_message.emit(f"节点 {nid} 已有确认的 Beat 数据（可重新生成覆盖）")

    # ------------------------------------------------------------------ #
    # 折叠面板辅助
    # ------------------------------------------------------------------ #
    @staticmethod
    def _make_collapsible(title: str, expanded: bool = True):
        group = QGroupBox(title)
        group.setCheckable(True)
        group.setChecked(expanded)
        group.setStyleSheet(
            "QGroupBox { font-weight: bold; padding-top: 16px; }"
            "QGroupBox::indicator { width: 13px; height: 13px; }"
        )
        inner_widget = QWidget()
        inner_layout = QVBoxLayout(inner_widget)
        inner_layout.setContentsMargins(4, 4, 4, 4)
        inner_layout.setSpacing(4)
        inner_widget.setVisible(expanded)
        outer_layout = QVBoxLayout(group)
        outer_layout.setContentsMargins(8, 4, 8, 8)
        outer_layout.addWidget(inner_widget)
        group.toggled.connect(inner_widget.setVisible)
        return group, inner_layout

    # ------------------------------------------------------------------ #
    # 保存编辑内容
    # ------------------------------------------------------------------ #
    def _on_save_edit(self):
        """将编辑过的可读视图/JSON视图内容保存回当前节点的 confirmed_beats"""
        nid = self._get_current_node_id()
        if not nid:
            QMessageBox.warning(self, "提示", "请先选择一个节点。")
            return

        if self._current_view_mode == "json":
            # JSON 模式：解析编辑后的 JSON
            try:
                new_data = json.loads(self._detail_edit.toPlainText())
                # 更新 beat 数据到 variation_results（如果有选中卡片）
                if self._selected_persona_key:
                    for r in self._variation_results:
                        if r.get("persona_key") == self._selected_persona_key:
                            r["beat"] = new_data
                            break
                self.project_data.confirmed_beats[nid] = new_data
                self.status_message.emit(f"✅ 节点 {nid} 的 Beat JSON 已保存")
                app_logger.info("血肉-保存编辑", f"节点 {nid} 保存用户修改的 JSON")
            except json.JSONDecodeError as e:
                QMessageBox.warning(self, "JSON 格式错误", f"无法解析 JSON：{e}")
                return
        else:
            # 可读视图模式：将文本内容保存为确认数据
            text = self._readable_view.toPlainText().strip()
            if not text:
                QMessageBox.warning(self, "提示", "文本内容为空，无法保存。")
                return
            # 如果已有 JSON 结构，尝试保留；否则存储为纯文本格式
            existing = self.project_data.confirmed_beats.get(nid)
            if existing and isinstance(existing, dict):
                existing["readable_text"] = text
                self.project_data.confirmed_beats[nid] = existing
            else:
                self.project_data.confirmed_beats[nid] = {"readable_text": text}
            self.status_message.emit(f"✅ 节点 {nid} 的可读文本已保存")
            app_logger.info("血肉-保存编辑", f"节点 {nid} 保存用户修改的可读文本")

        QMessageBox.information(self, "保存成功", "修改已保存到当前节点。")

    # ------------------------------------------------------------------ #
    # 一键批量生成
    # ------------------------------------------------------------------ #
    def _on_batch_generate(self):
        """按当前人格配置，一键生成后续 N 个章节（仍需手动选择确认）"""
        count = self._batch_count_spin.value()
        node = self._get_current_node()
        if not node:
            QMessageBox.warning(self, "提示", "请先选择要处理的节点！")
            return
        selected_keys = self._persona_selector.get_selected_keys()
        if not selected_keys:
            QMessageBox.warning(self, "提示", "请至少选择一个人格！")
            return

        # 获取当前节点索引
        current_idx = self._node_combo.currentIndex()
        remaining = self._node_combo.count() - current_idx
        actual_count = min(count, remaining)

        if actual_count <= 0:
            QMessageBox.warning(self, "提示", "没有可生成的后续章节。")
            return

        reply = QMessageBox.question(
            self, "确认批量生成",
            f"将从当前节点开始，连续生成 {actual_count} 个章节的 Beat。\n\n"
            f"注意，只能选择一个人格！每个章节会使用当前选中的第一个人格配置自动生成，\n"
            f"生成后需要逐一确认。确定开始吗？",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.No:
            return

        # 先生成当前节点
        self._batch_remaining = actual_count - 1  # 当前节点算一个
        self._batch_mode = True
        self._batch_auto_confirm = False
        app_logger.info("血肉-批量生成", f"启动批量生成流程，目标章节数：{actual_count}，使用人格：{selected_keys}")
        self._on_generate()

    def _on_autopilot_generate(self):
        """全自动模式：清空所有已有内容，从头开始全部重新生成"""
        selected_keys = self._persona_selector.get_selected_keys()
        if not selected_keys:
            QMessageBox.warning(self, "提示", "请至少选择一个人格！")
            return

        total_nodes = len(self.project_data.cpg_nodes)
        if total_nodes <= 0:
            QMessageBox.warning(self, "提示", "没有可生成的章节（骨架为空）。")
            return

        # 取第一个选中的人格作为自动确认人格
        self._batch_persona_key = selected_keys[0]

        from env import PERSONA_DEFINITIONS
        pname = PERSONA_DEFINITIONS.get(self._batch_persona_key, {}).get("name", self._batch_persona_key)

        reply = QMessageBox.question(
            self, "确认全部重新生成",
            f"⚠️ 该功能将清空所有已生成的 Beat 内容，从第 1 集开始全部重新生成！\n\n"
            f"• 使用人格：「{pname}」\n"
            f"• 总计 {total_nodes} 个章节将被重新生成\n"
            f"• 所有已确认的 Beat 数据将被清空\n\n"
            f"是否继续？",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.No:
            return

        # 清空所有已生成内容
        self.project_data.confirmed_beats.clear()

        # 刷新 UI：重置进度 + 跳到第一个节点
        self._refresh_node_combo()
        self._node_combo.setCurrentIndex(0)
        self._update_progress()
        self._clear_cards()
        self._detail_edit.clear()
        self._readable_view.clear()

        # 启动全自动批量生成
        self._batch_remaining = total_nodes - 1
        self._batch_mode = True
        self._batch_auto_confirm = True
        app_logger.info("血肉-自动生成", f"开启全自动生成流程，覆盖所有 {total_nodes} 个节点，使用首选人格：{self._batch_persona_key}")
        self._on_generate()

    # ------------------------------------------------------------------ #
    # 供应商多选
    # ------------------------------------------------------------------ #
    def _refresh_provider_checkboxes(self):
        """从 ai_service 加载供应商列表，刷新多选框"""
        from services.ai_service import ai_service
        ai_service.initialize()

        # 清除旧的 checkbox
        for cb in self._provider_checkboxes:
            self._provider_checks_layout.removeWidget(cb)
            cb.deleteLater()
        self._provider_checkboxes.clear()

        # 清除旧的 stretch（QSpacerItem）
        while self._provider_checks_layout.count() > 0:
            item = self._provider_checks_layout.takeAt(0)
            # takeAt 返回 QLayoutItem，widget 类已在上面删除

        providers = ai_service.get_all_providers()
        active_id = ai_service.get_active_provider_id()

        for pid, cfg in providers.items():
            name = cfg.get("name", pid)
            cb = QCheckBox(name)
            cb.setProperty("provider_id", pid)
            # 默认勾选当前活跃供应商
            cb.setChecked(pid == active_id)
            cb.setStyleSheet("")
            self._provider_checks_layout.addWidget(cb)
            self._provider_checkboxes.append(cb)

        self._provider_checks_layout.addStretch()

    def _get_selected_provider_pool(self) -> list:
        """获取用户勾选的供应商 ID 列表。未勾选任何则返回 None（走默认供应商）"""
        selected = []
        for cb in self._provider_checkboxes:
            if cb.isChecked():
                selected.append(cb.property("provider_id"))
        return selected if selected else None

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

        from env import DRAMA_STYLE_CONFIG
        from services.genre_manager import genre_manager
        style_key = self.project_data.drama_style or "short_drama"
        style_cfg = DRAMA_STYLE_CONFIG.get(style_key, {})

        genre_key = getattr(self.project_data, 'story_genre', 'custom')
        genre_cfg = genre_manager.get(genre_key)
        combined_var = style_cfg.get("variation_style_block", "")
        genre_var = genre_cfg.get("variation_block", "")
        if genre_var:
            combined_var = (combined_var + "\n\n" + genre_var).strip()

        self._worker = VariationWorker(
            sparkle=self.project_data.sparkle,
            world_variables=self.project_data.world_variables,
            cpg_nodes=self.project_data.cpg_nodes,
            cpg_edges=self.project_data.cpg_edges,
            target_node=node,
            confirmed_beats=self.project_data.confirmed_beats,
            selected_persona_keys=selected_keys,
            ai_params=self._ai_settings_var.get_all_settings(),
            characters=self.project_data.characters,
            drama_style_block=combined_var,
            provider_pool=self._get_selected_provider_pool(),
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

        # 全自动模式：自动选择第一个有效结果并确认
        if self._batch_auto_confirm:
            # 找第一个成功的 beat
            auto_beat = None
            auto_key = None
            for r in self._variation_results:
                if r.get("beat"):
                    auto_beat = r["beat"]
                    auto_key = r["persona_key"]
                    break
            if auto_beat:
                self._selected_persona_key = auto_key
                self._detail_edit.setPlainText(
                    json.dumps(auto_beat, ensure_ascii=False, indent=2)
                )
                nid = self._get_current_node_id()
                self.status_message.emit(
                    f"✈️ 全自动: {nid} 已自动确认 (剩余 {self._batch_remaining})"
                )
                self._on_confirm_beat()  # 自动确认
                return
            else:
                self.status_message.emit("⚠️ 全自动模式: 本节点生成失败，已停止")
                self._batch_mode = False
                self._batch_auto_confirm = False
                self._batch_remaining = 0
                return

        self.status_message.emit(
            f"变体生成完成: {summary.get('success',0)}/{summary.get('total',0)} 成功，请选择方案"
        )

    def _on_card_selected(self, persona_key: str):
        self._selected_persona_key = persona_key
        self._current_beat_data = None
        for r in self._variation_results:
            if r["persona_key"] == persona_key and r.get("beat"):
                self._current_beat_data = r["beat"]
                # 更新两个视图
                self._detail_edit.setPlainText(
                    json.dumps(r["beat"], ensure_ascii=False, indent=2)
                )
                self._readable_view.setPlainText(
                    self._format_beat_readable(r["beat"])
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
            app_logger.warning("血肉-跳过节点", f"用户跳过节点 {nid} 的血肉生成")
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

        from env import PERSONA_DEFINITIONS
        pname = PERSONA_DEFINITIONS.get(self._selected_persona_key, {}).get("name", self._selected_persona_key)
        app_logger.success(
            "血肉-确认Beat",
            f"节点 {nid} 确认采用人格方案：{pname}",
            f"Beat 内容：\n{json.dumps(beat_data, ensure_ascii=False, indent=2)}"
        )

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
            if self._batch_auto_confirm:
                # 全自动模式：直接进入扩写
                self._batch_mode = False
                self._batch_auto_confirm = False
                self._batch_remaining = 0
                self.status_message.emit("✈️ 全自动模式完成！所有节点已确认，进入扩写阶段")
                self.project_data.current_phase = "expansion"
                self.project_data.push_history("enter_expansion")
                self.phase_completed.emit()
                return

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

            # 批量模式：自动生成下一个
            if self._batch_mode and self._batch_remaining > 0:
                self._batch_remaining -= 1
                self.status_message.emit(
                    f"🚀 批量模式：还剩 {self._batch_remaining + 1} 个章节待生成..."
                )
                from PySide6.QtCore import QTimer
                QTimer.singleShot(500, self._on_generate)
            else:
                if self._batch_auto_confirm:
                    self.status_message.emit(
                        f"✈️ 全自动模式完成！共处理了 {self._batch_count_spin.value() - self._batch_remaining} 个章节"
                    )
                self._batch_mode = False
                self._batch_auto_confirm = False
                self._batch_remaining = 0

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
            f"<span style='color:{c};font-weight:bold;'>"
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

    # ------------------------------------------------------------------ #
    # 视图切换 + 可读格式化
    # ------------------------------------------------------------------ #
    def _switch_detail_view(self, mode: str):
        """切换可读视图和 JSON 编辑视图"""
        self._current_view_mode = mode
        if mode == "readable":
            self._readable_view.setVisible(True)
            self._detail_edit.setVisible(False)
            self._btn_readable_view.setChecked(True)
            self._btn_json_view.setChecked(False)
            # 同步 JSON 编辑器的内容到可读视图
            raw = self._detail_edit.toPlainText().strip()
            if raw:
                try:
                    beat = json.loads(raw)
                    self._readable_view.setPlainText(self._format_beat_readable(beat))
                except json.JSONDecodeError:
                    pass
        else:
            self._readable_view.setVisible(False)
            self._detail_edit.setVisible(True)
            self._btn_readable_view.setChecked(False)
            self._btn_json_view.setChecked(True)

    @staticmethod
    def _format_beat_readable(beat: dict) -> str:
        """将 Beat JSON 渲染为人类可读的剧本摘要格式"""
        if not beat or not isinstance(beat, dict):
            return "（无数据）"
        lines = []

        # 基本信息
        persona = beat.get("persona_name", "")
        node_id = beat.get("target_node_id", "")
        if persona or node_id:
            lines.append(f"═══ {node_id} | 人格: {persona} ═══")
            lines.append("")

        # 场景描述
        setting = beat.get("setting", "")
        if setting:
            lines.append("┌─ 场景描述 ───────────────")
            lines.append(f"│ {setting}")
            lines.append("└────────────────────────")
            lines.append("")

        # 活跃角色
        entities = beat.get("entities", [])
        if entities:
            lines.append("🎭 活跃角色")
            for e in entities:
                lines.append(f"  • {e}")
            lines.append("")

        # 因果事件链
        events = beat.get("causal_events", [])
        if events:
            lines.append("ℹ️ 因果事件链")
            lines.append("─" * 30)
            for e in events:
                eid = e.get("event_id", "?")
                action = e.get("action", "")
                impact = e.get("causal_impact", "")
                prev = e.get("connects_to_previous", "")
                # 序号图标
                num_icons = {
                    1: "❶", 2: "❷", 3: "❸", 4: "❹", 5: "❺",
                    6: "❻", 7: "❼", 8: "❽", 9: "❾"
                }
                icon = num_icons.get(eid, f"[{eid}]")
                lines.append(f"{icon} {action}")
                if impact:
                    lines.append(f"   → 导致: {impact}")
                if prev:
                    lines.append(f"   ← 前因: {prev}")
                lines.append("")

        # 悬念钩子
        hook = beat.get("hook", "")
        if hook:
            lines.append("🌟 悬念钩子")
            lines.append(f"  {hook}")
            lines.append("")

        # 创作理由
        rationale = beat.get("rationale", "")
        if rationale:
            lines.append("💡 创作理由")
            lines.append(f"  {rationale}")

        return "\n".join(lines)
