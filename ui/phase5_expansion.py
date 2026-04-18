# ============================================================
# ui/phase5_expansion.py
# Phase 5: 剧本扩写 — 将每个已确认Beat扩写为标准短剧剧本格式
# ============================================================

import json
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QSplitter, QComboBox, QTextEdit,
    QGroupBox, QMessageBox, QFileDialog,
)
from PySide6.QtCore import Qt, Signal

from env import (
    SYSTEM_PROMPT_EXPANSION, USER_PROMPT_EXPANSION,
    TEMPERATURE_EXPANSION,
)
from services.worker import ExpansionWorker
from ui.widgets.screenplay_editor import ScreenplayEditor
from ui.widgets.ai_settings_panel import AISettingsPanel
from ui.widgets.prompt_viewer import PromptViewer


class Phase5Expansion(QWidget):
    """
    Phase 5: 剧本扩写阶段。

    功能:
      - 逐节点（或批量）将确认的 Beat 扩写为 600-800字标准短剧剧本
      - 实时编辑、字数统计
      - 支持"批量扩写全部"批次执行

    信号:
        phase_completed: 扩写完成进入锁定
        go_back_to_flesh: 返回血肉阶段
        status_message: 状态栏消息
    """

    phase_completed    = Signal()
    go_back_to_flesh   = Signal()
    status_message     = Signal(str)

    def __init__(self, project_data, parent=None):
        super().__init__(parent)
        self.project_data = project_data
        self._worker = None
        self._current_node_id: str = ""
        self._batch_queue: list = []     # 批量扩写队列（节点ID列表）
        self._setup_ui()

    # ------------------------------------------------------------------ #
    # UI
    # ------------------------------------------------------------------ #
    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(6)

        # 标题 + 进度行
        top_row = QHBoxLayout()
        self._title_label = QLabel("📽️ 剧本扩写")
        self._title_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        top_row.addWidget(self._title_label)
        top_row.addStretch()

        top_row.addWidget(QLabel("当前节点："))
        self._node_combo = QComboBox()
        self._node_combo.setMinimumWidth(220)
        self._node_combo.currentIndexChanged.connect(self._on_node_changed)
        top_row.addWidget(self._node_combo)

        root.addLayout(top_row)

        # 进度指示
        self._progress_label = QLabel("进度: ...")
        self._progress_label.setStyleSheet("font-size: 12px; color: #555;")
        root.addWidget(self._progress_label)

        # 主内容：左右分割
        h_splitter = QSplitter(Qt.Horizontal)

        # 左侧：Beat 摘要（只读参考）
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(4)

        beat_label = QLabel("📋 Beat 摘要（参考）")
        beat_label.setStyleSheet("font-weight: bold; font-size: 13px;")
        ll.addWidget(beat_label)

        self._beat_summary = QTextEdit()
        self._beat_summary.setReadOnly(True)
        self._beat_summary.setStyleSheet(
            "QTextEdit {"
            "  background:#f8f9fa; border:1px solid #dcdde1;"
            "  border-radius:6px; padding:8px; font-size:12px;"
            "}"
        )
        ll.addWidget(self._beat_summary, 1)

        # 角色摘要
        char_label = QLabel("👤 角色性格参考")
        char_label.setStyleSheet("font-weight: bold; font-size: 12px; margin-top:6px;")
        ll.addWidget(char_label)

        self._char_summary = QTextEdit()
        self._char_summary.setReadOnly(True)
        self._char_summary.setMaximumHeight(100)
        self._char_summary.setStyleSheet(
            "QTextEdit {"
            "  background:#fdf6e3; border:1px solid #f0d9a0;"
            "  border-radius:6px; padding:8px; font-size:11px;"
            "}"
        )
        ll.addWidget(self._char_summary)

        # AI参数
        self._ai_settings = AISettingsPanel(suggested_temp=TEMPERATURE_EXPANSION)
        ll.addWidget(self._ai_settings)

        self._prompt_viewer = PromptViewer()
        self._prompt_viewer.set_prompt(SYSTEM_PROMPT_EXPANSION, USER_PROMPT_EXPANSION)
        ll.addWidget(self._prompt_viewer)

        h_splitter.addWidget(left)

        # 右侧：剧本编辑器
        self._screenplay_editor = ScreenplayEditor(target_min=600, target_max=800)
        self._screenplay_editor.text_changed.connect(self._on_screenplay_text_changed)
        h_splitter.addWidget(self._screenplay_editor)

        h_splitter.setSizes([340, 580])
        root.addWidget(h_splitter, 1)

        # === 按钮行 1 ===
        btn_row1 = QHBoxLayout()

        self._btn_back = QPushButton("← 返回血肉修改 Beat")
        self._btn_back.clicked.connect(self.go_back_to_flesh.emit)
        btn_row1.addWidget(self._btn_back)

        self._btn_save = QPushButton("💾 保存当前编辑")
        self._btn_save.clicked.connect(self._on_save_current)
        btn_row1.addWidget(self._btn_save)

        self._btn_rewrite = QPushButton("🔄 重新扩写当前节点")
        self._btn_rewrite.clicked.connect(self._on_expand_current)
        btn_row1.addWidget(self._btn_rewrite)

        # 重新生成当前 + 后续 N 章
        btn_row1.addWidget(QLabel("  从当前起重生:"))
        from PySide6.QtWidgets import QSpinBox
        self._regen_spin = QSpinBox()
        self._regen_spin.setRange(1, 20)
        self._regen_spin.setValue(1)
        self._regen_spin.setSuffix(" 章")
        self._regen_spin.setFixedWidth(80)
        btn_row1.addWidget(self._regen_spin)

        self._btn_regen_subsequent = QPushButton("🔄 重新生成")
        self._btn_regen_subsequent.setStyleSheet(
            "QPushButton{background:#e67e22;color:white;border:none;"
            "border-radius:4px;padding:6px 14px;}"
            "QPushButton:hover{background:#d35400;}"
            "QPushButton:disabled{background:#bdc3c7;}"
        )
        self._btn_regen_subsequent.clicked.connect(self._on_regen_subsequent)
        btn_row1.addWidget(self._btn_regen_subsequent)

        btn_row1.addStretch()
        root.addLayout(btn_row1)

        # === 按钮行 2 ===
        btn_row2 = QHBoxLayout()

        self._btn_batch = QPushButton("🚀 批量扩写全部节点")
        self._btn_batch.setStyleSheet(
            "QPushButton{background:#2980b9;color:white;border:none;"
            "border-radius:4px;padding:6px 14px;}"
            "QPushButton:hover{background:#1f6da8;}"
            "QPushButton:disabled{background:#bdc3c7;}"
        )
        self._btn_batch.clicked.connect(self._on_expand_all)
        btn_row2.addWidget(self._btn_batch)

        btn_row2.addStretch()

        self._btn_export = QPushButton("📄 导出全部剧本")
        self._btn_export.clicked.connect(self._on_export)
        btn_row2.addWidget(self._btn_export)

        self._btn_next = QPushButton("完成扩写，进入锁定 →")
        self._btn_next.setMinimumHeight(36)
        self._btn_next.setStyleSheet(
            "QPushButton{background:#27ae60;color:white;font-weight:bold;"
            "border-radius:5px;border:none;}"
            "QPushButton:hover{background:#229954;}"
        )
        self._btn_next.clicked.connect(self._on_proceed)
        btn_row2.addWidget(self._btn_next)

        root.addLayout(btn_row2)

    # ------------------------------------------------------------------ #
    # 生命周期
    # ------------------------------------------------------------------ #
    def on_enter(self):
        """进入扩写阶段时刷新节点列表，并根据每集时长自动计算目标字数"""
        # 根据 episode_duration 自动设置目标字数范围
        duration = self.project_data.episode_duration
        target_center = duration * 180  # 每分钟约 180 字
        target_min = int(target_center * 0.9)  # -10%
        target_max = int(target_center * 1.1)  # +10%
        self._screenplay_editor.set_target_range(target_min, target_max)

        # 检测骨架结构变更：清理已不存在节点的陈旧数据
        current_nids = {n.get("node_id") for n in self.project_data.cpg_nodes}
        stale_texts = [k for k in self.project_data.screenplay_texts
                       if k not in current_nids]
        stale_beats = [k for k in self.project_data.confirmed_beats
                       if k not in current_nids]
        if stale_texts or stale_beats:
            for k in stale_texts:
                del self.project_data.screenplay_texts[k]
            for k in stale_beats:
                del self.project_data.confirmed_beats[k]

        self._refresh_node_combo()
        if self._node_combo.count() > 0:
            self._node_combo.setCurrentIndex(0)
            self._load_node(self._node_combo.currentData())

    # ------------------------------------------------------------------ #
    # 节点选择
    # ------------------------------------------------------------------ #
    def _refresh_node_combo(self):
        self._node_combo.blockSignals(True)
        self._node_combo.clear()
        confirmed = self.project_data.confirmed_beats
        texts_dict = self.project_data.screenplay_texts

        done = sum(1 for k, v in texts_dict.items() if v and v.strip())
        total = len([n for n in self.project_data.cpg_nodes
                     if confirmed.get(n.get("node_id"))])

        self._progress_label.setText(f"进度: {done}/{total} 个节点已扩写")

        # 按节点编号数字排序显示
        import re
        sorted_nodes = sorted(
            self.project_data.cpg_nodes,
            key=lambda n: tuple(int(x) for x in re.findall(r'\d+', n.get('node_id', 'Ep0')))
                          if re.search(r'\d+', n.get('node_id', '')) else (9999,)
        )
        for node in sorted_nodes:
            nid = node.get("node_id", "")
            if not confirmed.get(nid):
                continue  # 只列出已确认Beat的节点
            has_text = bool(texts_dict.get(nid, "").strip())
            icon = "✅" if has_text else "⬜"
            ep_num = self._extract_episode_number(nid)
            label = f"{icon} Ep_{ep_num} ({nid}): {node.get('title', '')}"
            self._node_combo.addItem(label, nid)

        self._node_combo.blockSignals(False)

    def _on_node_changed(self, idx):
        if idx < 0:
            return
        nid = self._node_combo.currentData()
        if nid:
            self._load_node(nid)

    def _load_node(self, node_id: str):
        self._current_node_id = node_id
        node = next((n for n in self.project_data.cpg_nodes
                     if n.get("node_id") == node_id), None)
        beat = self.project_data.confirmed_beats.get(node_id, {}) or {}

        # 填充 Beat 摘要
        if node and beat:
            events = beat.get("causal_events", [])
            events_text = "\n".join(
                f"  {e.get('event_id','')}: {e.get('action', '')}"
                for e in events
            )
            summary = (
                f"节点: {node_id} — {node.get('title','')}\n"
                f"阶段: {node.get('hauge_stage_name','')}\n"
                f"场景: {beat.get('setting','')}\n"
                f"角色: {', '.join(beat.get('entities', []))}\n\n"
                f"因果事件:\n{events_text}\n\n"
                f"悬念钩子: {beat.get('hook','')}"
            )
        else:
            summary = "(此节点尚未确认 Beat)"
        self._beat_summary.setPlainText(summary)

        # 填充角色摘要
        chars_in_scene = set(beat.get("entities", []))
        char_lines = []
        for c in self.project_data.characters:
            if c.get("name") in chars_in_scene or not chars_in_scene:
                line = f"• {c.get('name','')} [{c.get('role_type','')}]"
                if c.get("personality"):
                    line += f" — {c.get('personality','')}"
                char_lines.append(line)
        self._char_summary.setPlainText("\n".join(char_lines) or "（未设定角色）")

        # 填充剧本编辑器
        existing = self.project_data.screenplay_texts.get(node_id, "")
        self._screenplay_editor.set_text(existing)

    # ------------------------------------------------------------------ #
    # AI 扩写（单节点）
    # ------------------------------------------------------------------ #
    def _on_expand_current(self):
        if not self._current_node_id:
            return
        self._expand_node(self._current_node_id)

    def _on_save_current(self):
        """显式保存当前编辑内容"""
        if self._current_node_id:
            text = self._screenplay_editor.get_text()
            self.project_data.screenplay_texts[self._current_node_id] = text
            self._refresh_node_combo()
            self.status_message.emit(f"💾 已保存 {self._current_node_id} 的编辑内容")

    def _on_regen_subsequent(self):
        """从当前节点起重新生成 N 章"""
        if not self._current_node_id:
            return
        count = self._regen_spin.value()
        sorted_nodes = self._get_sorted_confirmed_nodes()
        # 找到当前节点在排序列表中的位置
        start_idx = -1
        for i, n in enumerate(sorted_nodes):
            if n.get("node_id") == self._current_node_id:
                start_idx = i
                break
        if start_idx < 0:
            return
        target_nids = [n.get("node_id") for n in sorted_nodes[start_idx:start_idx + count]]
        if not target_nids:
            return
        reply = QMessageBox.question(
            self, "重新生成",
            f"将重新扩写从 {target_nids[0]} 起的 {len(target_nids)} 个节点。\n"
            "已有的扩写内容会被覆盖。确定吗？",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.No:
            return
        self._batch_queue = list(target_nids[1:])
        first_nid = target_nids[0]
        for i in range(self._node_combo.count()):
            if self._node_combo.itemData(i) == first_nid:
                self._node_combo.setCurrentIndex(i)
                break
        self._expand_node(first_nid)

    def _expand_node(self, node_id: str):
        node = next((n for n in self.project_data.cpg_nodes
                     if n.get("node_id") == node_id), None)
        beat = self.project_data.confirmed_beats.get(node_id, {}) or {}

        if not beat:
            QMessageBox.warning(self, "提示", f"节点 {node_id} 尚未确认 Beat，无法扩写。")
            return

        # 组装角色摘要（含重要性等级）
        chars_summary = "\n".join(
            f"[{c.get('importance_level','C')}] {c.get('name', '')}：{c.get('personality', '')}；动机：{c.get('motivation', '')}"
            for c in self.project_data.characters
        ) or "（未设定角色）"

        # 集编号（从节点 ID 提取数字）
        episode_number = self._extract_episode_number(node_id)

        # 因果图入边：获取入边信息和前情摘要
        incoming_edges_context, previous_screenplay_excerpt = self._get_incoming_context(node_id)

        # 因果事件文本
        events = beat.get("causal_events", [])
        causal_events_text = "\n".join(
            f"  事件{e.get('event_id','')}: {e.get('action','')}"
            f" → {e.get('causal_impact','')}"
            for e in events
        )

        target_min, target_max = self._screenplay_editor.get_target_range()
        target_word_count = f"{target_min}-{target_max}"

        self._set_busy(True)
        self.status_message.emit(f"🎬 正在扩写 {node_id}：{node.get('title','')}…")

        from env import DRAMA_STYLE_CONFIG
        from services.genre_manager import genre_manager
        style_key = self.project_data.drama_style or "short_drama"
        style_cfg = DRAMA_STYLE_CONFIG.get(style_key, {})
        expansion_block = (
            style_cfg.get("expansion_style_block", "")
            .replace("{scenes_per_episode}", self.project_data.scenes_per_episode or "1-2")
            .replace("{target_word_count}", target_word_count)
        )

        genre_key = getattr(self.project_data, 'story_genre', 'custom')
        genre_cfg = genre_manager.get(genre_key)
        genre_exp = genre_cfg.get("expansion_block", "")
        if genre_exp:
            expansion_block = (expansion_block + "\n\n" + genre_exp).strip()

        self._worker = ExpansionWorker(
            sparkle=self.project_data.sparkle,
            finale_condition=self.project_data.finale_condition,
            characters_summary=chars_summary,
            episode_number=episode_number,
            incoming_edges_context=incoming_edges_context,
            previous_screenplay_excerpt=previous_screenplay_excerpt,
            node_id=node_id,
            node_title=node.get("title", ""),
            hauge_stage_name=node.get("hauge_stage_name", ""),
            setting=beat.get("setting", ""),
            entities=", ".join(beat.get("entities", [])),
            causal_events_text=causal_events_text,
            hook=beat.get("hook", ""),
            target_word_count=target_word_count,
            ai_params=self._ai_settings.get_all_settings(),
            episode_duration=self.project_data.episode_duration,
            drama_style_block=expansion_block,
        )
        self._worker.progress.connect(self.status_message)
        self._worker.finished.connect(self._on_expand_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _extract_episode_number(self, node_id: str) -> int:
        """从节点 ID（如 N3）提取集编号数字"""
        import re
        m = re.search(r'(\d+)', node_id)
        return int(m.group(1)) if m else 1

    def _get_incoming_context(self, current_node_id: str):
        """
        从因果图的入边获取前情上下文（而非按列表顺序）。
        返回 (incoming_edges_context, previous_screenplay_excerpt)
        """
        edges = self.project_data.cpg_edges
        node_title_map = {n["node_id"]: n.get("title", "") for n in self.project_data.cpg_nodes}

        # 收集所有指向当前节点的入边
        incoming = [e for e in edges if e.get("to_node") == current_node_id]

        if not incoming:
            return "（本节点无入边，为故事起点）", "（故事开篇，无前情）"

        # 构建入边关系描述
        edge_lines = []
        for e in incoming:
            from_id = e.get("from_node", "")
            from_title = node_title_map.get(from_id, "")
            ct = e.get("causal_type", "直接因果")
            desc = e.get("description", "")
            line = f"← {from_id}({from_title}) --[{ct}]--> 本节点"
            if desc:
                line += f"  说明: {desc}"
            edge_lines.append(line)
        incoming_edges_context = "\n".join(edge_lines)

        # 从入边节点获取已扩写文本（取最后 500 字作为前情摘要）
        excerpts = []
        for e in incoming:
            from_id = e.get("from_node", "")
            existing_text = self.project_data.screenplay_texts.get(from_id, "").strip()
            if existing_text:
                # 取最后500字作为场景衔接参考
                tail = existing_text[-500:] if len(existing_text) > 500 else existing_text
                excerpts.append(f"[来自 {from_id} 的结尾片段]\n{tail}")
            else:
                # 没有扩写文本，用 Beat 的 hook
                prev_beat = self.project_data.confirmed_beats.get(from_id, {}) or {}
                hook = prev_beat.get("hook", "")
                if hook:
                    excerpts.append(f"[来自 {from_id} 的悬念钩子]\n{hook}")

        previous_screenplay_excerpt = "\n\n".join(excerpts) if excerpts else "（前序节点尚未扩写）"

        return incoming_edges_context, previous_screenplay_excerpt
    def _on_expand_done(self, result: dict):
        self._set_busy(False)
        text = result.get("text", "")
        if not text:
            self.status_message.emit("扩写结果为空，请重试")
            return

        # 保存到 project_data
        self.project_data.screenplay_texts[self._current_node_id] = text
        self._screenplay_editor.set_text(text)

        # 刷新下拉进度显示
        self._refresh_node_combo()

        # 如果有批量队列，处理下一个
        if self._batch_queue:
            next_nid = self._batch_queue.pop(0)
            # 切换到下一节点
            for i in range(self._node_combo.count()):
                if self._node_combo.itemData(i) == next_nid:
                    self._node_combo.setCurrentIndex(i)
                    break
            self._expand_node(next_nid)
        else:
            self.status_message.emit(
                f"✅ {self._current_node_id} 扩写完成 "
                f"({len(text)}字)"
            )

    # ------------------------------------------------------------------ #
    # 批量扩写
    # ------------------------------------------------------------------ #
    def _on_expand_all(self):
        """批量扩写全部节点 — 重置所有已扩写状态后全部重新扩写"""
        confirmed = self.project_data.confirmed_beats
        target = [
            n.get("node_id") for n in self.project_data.cpg_nodes
            if confirmed.get(n.get("node_id"))
        ]

        if not target:
            QMessageBox.information(self, "提示", "没有可扩写的节点（至少需确认一个Beat）。")
            return

        # 统计已有扩写文本的节点数
        texts = self.project_data.screenplay_texts
        existing_count = sum(1 for nid in target if texts.get(nid, "").strip())

        warn_msg = (
            f"⚠️ 将对全部 {len(target)} 个已确认节点进行完整重写。\n"
        )
        if existing_count > 0:
            warn_msg += f"其中 {existing_count} 个节点已有扩写文本，将被覆盖！\n"
        warn_msg += (
            f"\n预计耗时 {len(target) * 20}-{len(target) * 40} 秒。\n"
            "扩写期间可以继续操作其他内容。\n\n确认开始全部重写？"
        )

        reply = QMessageBox.warning(
            self, "批量全部重写",
            warn_msg,
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.No:
            return

        # 清除所有已扩写文本
        for nid in target:
            self.project_data.screenplay_texts[nid] = ""

        self.status_message.emit(
            f"🔄 已重置 {len(target)} 个节点的扩写状态，开始全部重写..."
        )

        # 刷新当前面板显示
        self._refresh_node_combo()

        self._batch_queue = list(target[1:])  # 剩余队列
        first_nid = target[0]
        for i in range(self._node_combo.count()):
            if self._node_combo.itemData(i) == first_nid:
                self._node_combo.setCurrentIndex(i)
                break
        self._expand_node(first_nid)

    # ------------------------------------------------------------------ #
    # 文本变化 → 即时保存
    # ------------------------------------------------------------------ #
    def _on_screenplay_text_changed(self, text: str):
        if self._current_node_id:
            self.project_data.screenplay_texts[self._current_node_id] = text

    # ------------------------------------------------------------------ #
    # 导出全部剧本
    # ------------------------------------------------------------------ #
    def _get_sorted_confirmed_nodes(self) -> list:
        """按节点编号数字排序，只返回已确认 Beat 的节点"""
        import re
        confirmed = self.project_data.confirmed_beats
        nodes = [n for n in self.project_data.cpg_nodes
                 if confirmed.get(n.get("node_id"))]
        def sort_key(n):
            m = re.search(r'(\d+)', n.get("node_id", ""))
            return int(m.group(1)) if m else 9999
        return sorted(nodes, key=sort_key)

    def _on_export(self):
        import os
        name = self.project_data.story_title or "untitled"
        os.makedirs("projects", exist_ok=True)
        filepath, _ = QFileDialog.getSaveFileName(
            self, "导出剧本正文",
            f"projects/{name}_screenplay.txt",
            "Text Files (*.txt);;All Files (*)",
        )
        if not filepath:
            return

        lines = [
            f"剧本：{self.project_data.story_title or '未命名'}",
            f"梗概：{self.project_data.sparkle}",
            f"终局：{self.project_data.finale_condition}",
            "",
            "=" * 60,
            "",
        ]
        # 按节点编号数字排序导出
        sorted_nodes = self._get_sorted_confirmed_nodes()
        # 加上未确认但存在的节点
        confirmed_ids = {n.get("node_id") for n in sorted_nodes}
        import re
        all_sorted = sorted(
            self.project_data.cpg_nodes,
            key=lambda n: tuple(int(x) for x in re.findall(r'\d+', n.get('node_id', 'Ep0')))
                          if re.search(r'\d+', n.get('node_id', '')) else (9999,)
        )
        for node in all_sorted:
            nid = node.get("node_id", "")
            text = self.project_data.screenplay_texts.get(nid, "")
            if text and text.strip():
                lines.append(text.strip())
                lines.append("")
            else:
                ep_num = self._extract_episode_number(nid)
                lines.append(f"--- Ep_{ep_num} ---")
                lines.append(f"（{nid}: {node.get('title', '')} — 尚未扩写）")
                lines.append("")
                lines.append("==========================================")
                lines.append("")

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            QMessageBox.information(self, "导出成功", f"剧本已保存到：\n{filepath}")
            self.status_message.emit(f"✅ 剧本已导出: {filepath}")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", str(e))

    # ------------------------------------------------------------------ #
    # 进入 Phase 6: 锁定
    # ------------------------------------------------------------------ #
    def _on_proceed(self):
        texts = self.project_data.screenplay_texts
        written = sum(1 for v in texts.values() if v and v.strip())
        total = sum(1 for n in self.project_data.cpg_nodes
                    if self.project_data.confirmed_beats.get(n.get("node_id")))
        if written < total:
            reply = QMessageBox.question(
                self, "确认",
                f"还有 {total - written} 个节点尚未扩写（共 {total} 个）。\n"
                "确定进入锁定阶段吗？",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply == QMessageBox.No:
                return

        self.project_data.current_phase = "locked"
        self.project_data.push_history("enter_lock")
        self.phase_completed.emit()

    # ------------------------------------------------------------------ #
    # 工具
    # ------------------------------------------------------------------ #
    def _set_busy(self, busy: bool):
        self._btn_rewrite.setEnabled(not busy)
        self._btn_batch.setEnabled(not busy)
        self._btn_next.setEnabled(not busy)
        self._btn_save.setEnabled(not busy)
        self._btn_regen_subsequent.setEnabled(not busy)
        self._btn_rewrite.setText("生成中…" if busy else "🔄 重新扩写当前节点")

    def _on_error(self, msg: str):
        self._set_busy(False)
        self._batch_queue.clear()   # 批量队列清空
        QMessageBox.critical(self, "AI 调用失败", msg)
        self.status_message.emit("错误: " + msg)
