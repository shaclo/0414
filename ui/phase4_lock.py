# ============================================================
# ui/phase4_lock.py
# Phase 4: 锁定 — 最终审阅、统计摘要、导出
# ============================================================

import json
import os
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QGroupBox, QTableWidget, QTableWidgetItem,
    QFileDialog, QMessageBox, QHeaderView, QSplitter, QDialog,
    QTextEdit,
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QColor

from ui.widgets.cpg_graph_editor import CPGGraphEditor
from services.worker import ITEWorker
from services.logger_service import app_logger
from env import SUGGESTED_TEMPERATURES


class Phase4Lock(QWidget):
    """
    Phase 4: 锁定阶段界面。

    上方: 完整 CPG 图（只读）
    下方: 统计摘要表 + ITE 评估结果 + 导出按钮

    信号:
        go_back_to_flesh: 返回 Phase 3 继续修改
        status_message: 状态栏消息
    """

    go_back_to_flesh = Signal()
    status_message = Signal(str)

    def __init__(self, project_data, parent=None):
        super().__init__(parent)
        self.project_data = project_data
        self._ite_worker = None
        self._ite_elapsed = 0
        self._ite_timer = QTimer(self)
        self._ite_timer.setInterval(1000)
        self._ite_timer.timeout.connect(self._on_ite_tick)
        self._setup_ui()

    # ------------------------------------------------------------------ #
    # UI 构建
    # ------------------------------------------------------------------ #
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)

        # ===== 顶部横幅 =====
        header_layout = QHBoxLayout()
        title = QLabel(f"🔒 锁定阶段 — 最终审阅与导出")
        title.setStyleSheet(" font-weight: bold; margin-bottom: 4px;")
        header_layout.addWidget(title)

        self._btn_view_cpg = QPushButton("🗺️ 查看完整 CPG 概览图")
        self._btn_view_cpg.setStyleSheet(
            "QPushButton{background:#16a085;color:white;font-weight:bold;"
            "border-radius:6px;border:none;padding:8px 16px;}"
            "QPushButton:hover{background:#1abc9c;}"
        )
        self._btn_view_cpg.clicked.connect(self._on_view_cpg)
        header_layout.addStretch()
        header_layout.addWidget(self._btn_view_cpg)

        layout.addLayout(header_layout)

        # ===== 下方: 统计 =====
        bottom = QWidget()
        bl = QVBoxLayout(bottom)
        bl.setContentsMargins(0, 0, 0, 0)

        # 摘要标签行
        self._summary_label = QLabel("")
        self._summary_label.setStyleSheet(
            " padding: 8px; background: #ecf0f1; "
            "border-radius: 4px; border: 1px solid #bdc3c7;"
        )
        self._summary_label.setWordWrap(True)
        bl.addWidget(self._summary_label)

        # 节点统计表
        stats_group = QGroupBox("📋 节点详情")
        slyt = QVBoxLayout(stats_group)
        self._stats_table = QTableWidget(0, 5)
        self._stats_table.setHorizontalHeaderLabels(
            ["节点 ID", "标题", "Hauge 阶段", "事件数", "ITE 平均分"]
        )
        self._stats_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._stats_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._stats_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._stats_table.cellDoubleClicked.connect(self._on_node_row_clicked)
        slyt.addWidget(self._stats_table)

        hint_label = QLabel("💡 双击表格行可查看该节点的 Beat 详情与 ITE 评分")
        hint_label.setStyleSheet("color: #7f8c8d; font-size: 11px; padding: 2px 0;")
        slyt.addWidget(hint_label)
        bl.addWidget(stats_group)

        # ===== ITE 评估结果区 =====
        self._ite_result_group = QGroupBox("📊 ITE 因果评估结果")
        ite_lyt = QVBoxLayout(self._ite_result_group)
        ite_lyt.setSpacing(6)

        self._ite_coherence_label = QLabel("故事连贯度: 未计算")
        self._ite_coherence_label.setStyleSheet(
            "font-weight: bold; padding: 4px 0;"
        )
        ite_lyt.addWidget(self._ite_coherence_label)

        self._ite_warnings_label = QLabel("")
        self._ite_warnings_label.setWordWrap(True)
        self._ite_warnings_label.setStyleSheet("color: #e67e22;")
        ite_lyt.addWidget(self._ite_warnings_label)

        self._ite_prunable_label = QLabel("")
        self._ite_prunable_label.setWordWrap(True)
        self._ite_prunable_label.setStyleSheet("color: #95a5a6;")
        ite_lyt.addWidget(self._ite_prunable_label)

        bl.addWidget(self._ite_result_group)

        layout.addWidget(bottom)

        # ===== 按钮行 =====
        btn_row = QHBoxLayout()
        self._btn_back = QPushButton("← 返回血肉阶段继续修改")
        self._btn_back.clicked.connect(self.go_back_to_flesh.emit)
        btn_row.addWidget(self._btn_back)

        # ITE 评估按钮
        self._btn_ite = QPushButton("📊 运行全局 ITE 评估")
        self._btn_ite.setMinimumHeight(36)
        self._btn_ite.setStyleSheet(
            "QPushButton{background:#e67e22;color:white;font-weight:bold;"
            "border-radius:6px;border:none;}"
            "QPushButton:hover{background:#d35400;}"
            "QPushButton:disabled{background:#bdc3c7;}"
        )
        self._btn_ite.clicked.connect(self._on_run_ite)
        btn_row.addWidget(self._btn_ite)

        # 取消按钮（仅评估中可见）
        self._btn_cancel_ite = QPushButton("⏹ 取消评估")
        self._btn_cancel_ite.setMinimumHeight(36)
        self._btn_cancel_ite.setStyleSheet(
            "QPushButton{background:#e74c3c;color:white;font-weight:bold;"
            "border:none;border-radius:6px;padding:6px 14px;}"
            "QPushButton:hover{background:#c0392b;}"
        )
        self._btn_cancel_ite.setVisible(False)
        self._btn_cancel_ite.clicked.connect(self._on_cancel_ite)
        btn_row.addWidget(self._btn_cancel_ite)

        # 耗时标签（仅评估中可见）
        self._ite_elapsed_label = QLabel("")
        self._ite_elapsed_label.setStyleSheet("color:#e67e22; font-weight:bold;")
        self._ite_elapsed_label.setVisible(False)
        btn_row.addWidget(self._ite_elapsed_label)

        btn_row.addStretch()

        self._btn_export_json = QPushButton("💾 导出为 .story.json")
        self._btn_export_json.setMinimumHeight(36)
        self._btn_export_json.setStyleSheet(
            "QPushButton{background:#3498db;color:white;font-weight:bold;"
            "border-radius:6px;border:none;}"
            "QPushButton:hover{background:#2980b9;}"
        )
        self._btn_export_json.clicked.connect(self._on_export_json)
        btn_row.addWidget(self._btn_export_json)

        self._btn_export_txt = QPushButton("📄 导出 CPG 摘要文本")
        self._btn_export_txt.setMinimumHeight(36)
        self._btn_export_txt.setStyleSheet(
            "QPushButton{background:#8e44ad;color:white;font-weight:bold;"
            "border-radius:6px;border:none;}"
            "QPushButton:hover{background:#7d3c98;}"
        )
        self._btn_export_txt.clicked.connect(self._on_export_txt)
        btn_row.addWidget(self._btn_export_txt)

        layout.addLayout(btn_row)

    # ------------------------------------------------------------------ #
    # 生命周期
    # ------------------------------------------------------------------ #
    def on_enter(self):
        """进入锁定阶段时更新数据"""
        self._update_stats()
        self._update_ite_display()
        self.status_message.emit("CPG 已锁定，可导出项目")

    def _on_view_cpg(self):
        """打开独立的 CPG 概览图窗口"""
        dialog = QDialog(self)
        dialog.setWindowTitle("完整 CPG 因果概率图概览")
        dialog.resize(1200, 800)
        dialog.setWindowFlags(dialog.windowFlags() | Qt.WindowMaximizeButtonHint | Qt.WindowMinMaxButtonsHint)
        
        lyt = QVBoxLayout(dialog)
        lyt.setContentsMargins(0, 0, 0, 0)
        
        editor = CPGGraphEditor()
        # 准备数据并加载
        nodes = []
        for n in self.project_data.cpg_nodes:
            nid = n.get("node_id", "")
            node_copy = dict(n)
            node_copy["status"] = "confirmed" if self.project_data.confirmed_beats.get(nid) else "pending"
            nodes.append(node_copy)
        editor.load_cpg(nodes, self.project_data.cpg_edges)
        
        lyt.addWidget(editor)
        dialog.exec()

    def _on_node_row_clicked(self, row: int, _col: int):
        """双击表格行 → 弹出该节点的 Beat 详情 + ITE 评分"""
        nid_item = self._stats_table.item(row, 0)
        if not nid_item:
            return
        node_id = nid_item.text()

        # 查找节点和 Beat
        node = next(
            (n for n in self.project_data.cpg_nodes if n.get("node_id") == node_id),
            None,
        )
        beat = self.project_data.confirmed_beats.get(node_id)
        if not node:
            return

        # 查找该节点的 ITE 评分
        ite_results = self.project_data.ite_results or {}
        ite_by_event = {}
        for ev in ite_results.get("event_evaluations", []):
            if ev.get("node_id") == node_id:
                ite_by_event[str(ev.get("event_id", ""))] = ev

        # 构建 HTML 内容
        STAGE_NAMES = {1:"机会",2:"变点",3:"无路可退",4:"挫折",5:"高潮",6:"终局"}
        stage = STAGE_NAMES.get(node.get("hauge_stage_id", 0), "")

        html = f"""
        <div style="font-family: 'Microsoft YaHei', sans-serif;">
        <h2 style="color:#2c3e50;">【{node_id}】{node.get('title', '')}</h2>
        <table style="margin-bottom:12px; color:#555;">
            <tr><td style="padding-right:16px;"><b>Hauge 阶段:</b></td><td>{stage}</td></tr>
            <tr><td><b>环境:</b></td><td>{node.get('setting', '—')}</td></tr>
        """

        if beat:
            entities = ", ".join(beat.get("entities", []))
            html += f"""
            <tr><td><b>选用人格:</b></td><td>{beat.get('persona_name', '—')}</td></tr>
            <tr><td><b>活跃角色:</b></td><td>{entities or '—'}</td></tr>
            <tr><td><b>环境(Beat):</b></td><td>{beat.get('setting', '—')}</td></tr>
            </table>
            """

            # 生成参数快照
            gen_params = self.project_data.flesh_generation_params.get(node_id, {})
            if gen_params:
                from env import PERSONA_DEFINITIONS
                from config.prompt_templates import prompt_template_manager as _ptm

                # 参与人格
                p_keys = gen_params.get("persona_keys", [])
                p_names = [PERSONA_DEFINITIONS.get(k, {}).get("name", k) for k in p_keys]
                confirmed_key = gen_params.get("confirmed_persona_key", "")
                confirmed_name = PERSONA_DEFINITIONS.get(confirmed_key, {}).get("name", confirmed_key) if confirmed_key else "—"

                # 爽感/钩子公式名称
                sat_ids = gen_params.get("sat_ids", [])
                hook_ids = gen_params.get("hook_ids", [])
                sat_map = {s.id: s.name for s in _ptm.get_satisfactions()}
                hook_map = {h.id: h.name for h in _ptm.get_hooks()}
                sat_names = [sat_map.get(sid, sid) for sid in sat_ids]
                hook_names = [hook_map.get(hid, hid) for hid in hook_ids]

                ts = gen_params.get("timestamp", "")

                html += f"""
                <div style="margin:8px 0; padding:10px; background:#eaf2f8; border-radius:6px;
                            border:1px solid #aed6f1;">
                    <b style="color:#2980b9;">🔧 生成参数快照</b>
                    <span style="color:#999; font-size:0.85em; margin-left:8px;">{ts}</span>
                    <table style="margin-top:6px; color:#555;">
                        <tr><td style="padding-right:12px;"><b>参与人格:</b></td>
                            <td>{', '.join(p_names) or '—'}</td></tr>
                        <tr><td><b>最终选用:</b></td>
                            <td style="color:#27ae60; font-weight:bold;">{confirmed_name}</td></tr>
                        <tr><td><b>爽感公式:</b></td>
                            <td>{', '.join(sat_names) or '—'}</td></tr>
                        <tr><td><b>钩子公式:</b></td>
                            <td>{', '.join(hook_names) or '—'}</td></tr>
                    </table>
                </div>
                """

            html += f"""
            <h3 style="color:#2c3e50; border-bottom:2px solid #3498db; padding-bottom:4px;">
                📋 事件列表（ITE 因果评分）
            </h3>
            """

            events = beat.get("causal_events", [])
            for ev in events:
                eid = str(ev.get("event_id", ""))
                ite_data = ite_by_event.get(eid, {})
                ite_score = ite_data.get("ite_score", -1)
                verdict = ite_data.get("verdict", "")
                reasoning = ite_data.get("reasoning", "")
                is_pruned = ev.get("is_pruned", False)

                # 颜色编码
                if verdict == "关键":
                    badge_color, badge_bg = "#c0392b", "#fde8e8"
                elif verdict == "重要":
                    badge_color, badge_bg = "#e67e22", "#fef5e7"
                elif verdict == "普通":
                    badge_color, badge_bg = "#27ae60", "#e8f8f0"
                elif verdict == "冗余":
                    badge_color, badge_bg = "#95a5a6", "#f0f0f0"
                else:
                    badge_color, badge_bg = "#7f8c8d", "#f9f9f9"

                pruned_tag = " <span style='color:#e74c3c;font-weight:bold;'>[已剔除]</span>" if is_pruned else ""

                ite_badge = ""
                if ite_score >= 0:
                    ite_badge = (
                        f"<span style='background:{badge_bg};color:{badge_color};"
                        f"padding:2px 8px;border-radius:3px;font-weight:bold;'>"
                        f"ITE {ite_score:.3f} — {verdict}</span>"
                    )
                else:
                    ite_badge = "<span style='color:#bdc3c7;'>未评分</span>"

                html += f"""
                <div style="margin:8px 0; padding:10px; background:#fafafa;
                            border-left:4px solid {badge_color}; border-radius:4px;">
                    <div style="margin-bottom:4px;">
                        <b style="color:#2c3e50;">事件 {eid}</b> {ite_badge}{pruned_tag}
                    </div>
                    <div style="color:#333; margin-bottom:4px;">
                        {ev.get('action', '')}
                    </div>
                    <div style="color:#666; font-size:0.9em;">
                        → <b>因果影响:</b> {ev.get('causal_impact', '')}
                    </div>
                """
                if reasoning:
                    html += f"""
                    <div style="color:#888; font-size:0.85em; margin-top:4px; font-style:italic;">
                        💬 ITE 判定理由: {reasoning}
                    </div>
                    """
                html += "</div>"

            # 悬念钩子
            hook = beat.get("hook", "")
            if hook:
                html += f"""
                <h3 style="color:#2c3e50; border-bottom:2px solid #e67e22; padding-bottom:4px;">
                    🎣 悬念钩子
                </h3>
                <p style="color:#333; padding:8px; background:#fef5e7; border-radius:4px;">
                    {hook}
                </p>
                """

            # 创作理由
            rationale = beat.get("rationale", "")
            if rationale:
                html += f"""
                <h3 style="color:#2c3e50; border-bottom:2px solid #8e44ad; padding-bottom:4px;">
                    💡 创作理由
                </h3>
                <p style="color:#555; font-style:italic; padding:8px; background:#f5eef8; border-radius:4px;">
                    {rationale}
                </p>
                """
        else:
            html += """
            </table>
            <p style="color:#e74c3c;">（该节点尚未生成 Beat）</p>
            """

        html += "</div>"

        # 弹出对话框
        dialog = QDialog(self)
        dialog.setWindowTitle(f"节点详情 — {node_id}: {node.get('title', '')}")
        dialog.resize(700, 600)
        dialog.setWindowFlags(
            dialog.windowFlags() | Qt.WindowMaximizeButtonHint | Qt.WindowMinMaxButtonsHint
        )

        dlyt = QVBoxLayout(dialog)
        dlyt.setContentsMargins(12, 12, 12, 12)

        text_view = QTextEdit()
        text_view.setReadOnly(True)
        text_view.setHtml(html)
        dlyt.addWidget(text_view)

        btn_close = QPushButton("关闭")
        btn_close.setFixedHeight(32)
        btn_close.clicked.connect(dialog.close)
        dlyt.addWidget(btn_close)

        dialog.exec()

    def _update_stats(self):
        """更新统计摘要和表格"""
        nodes = self.project_data.cpg_nodes
        beats = self.project_data.confirmed_beats
        ite_results = self.project_data.ite_results or {}

        total_nodes = len(nodes)
        confirmed_count = sum(1 for n in nodes if beats.get(n.get("node_id")))
        total_events = 0
        all_chars: set = set()
        pruned_events = 0

        # 构建每节点的 ITE 平均分表
        ite_by_node: dict = {}
        for ev in ite_results.get("event_evaluations", []):
            nid = ev.get("node_id", "")
            if nid not in ite_by_node:
                ite_by_node[nid] = []
            ite_by_node[nid].append(ev.get("ite_score", 0.0))

        coherence = ite_results.get("full_story_coherence", 0.0)

        # 更新统计表
        self._stats_table.setRowCount(len(nodes))
        STAGE_NAMES = {1:"机会",2:"变点",3:"无路可退",4:"挫折",5:"高潮",6:"终局"}

        # 按节点编号排序
        import re
        sorted_nodes = sorted(
            nodes,
            key=lambda n: int(re.search(r'(\d+)', n.get('node_id', 'N0')).group(1))
                          if re.search(r'(\d+)', n.get('node_id', '')) else 9999
        )
        for row, node in enumerate(sorted_nodes):
            nid = node.get("node_id", "")
            beat = beats.get(nid)
            events = beat.get("causal_events", []) if beat else []
            total_events += len(events)
            entities = beat.get("entities", []) if beat else []
            all_chars.update(entities)
            pruned_events += sum(1 for e in events if e.get("is_pruned"))

            avg_ite = (
                sum(ite_by_node.get(nid, [])) / len(ite_by_node[nid])
                if ite_by_node.get(nid) else -1.0
            )
            stage_id = node.get("hauge_stage_id", 0)
            stage_name = STAGE_NAMES.get(stage_id, str(stage_id))

            self._stats_table.setItem(row, 0, QTableWidgetItem(nid))
            self._stats_table.setItem(row, 1, QTableWidgetItem(node.get("title", "")))
            self._stats_table.setItem(row, 2, QTableWidgetItem(stage_name))
            self._stats_table.setItem(row, 3, QTableWidgetItem(str(len(events))))
            ite_text = f"{avg_ite:.3f}" if avg_ite >= 0 else "未计算"
            ite_item = QTableWidgetItem(ite_text)
            if avg_ite >= 0:
                ite_item.setForeground(
                    QColor("#27ae60") if avg_ite > 0.3
                    else QColor("#e67e22") if avg_ite > 0.1
                    else QColor("#e74c3c")
                )
            self._stats_table.setItem(row, 4, ite_item)

        # 摘要文字
        title = self.project_data.story_title or "未命名"
        hauge_covered = len(set(n.get("hauge_stage_id") for n in nodes if n.get("hauge_stage_id")))
        coherence_text = f"{coherence:.0%}" if coherence > 0 else "未计算"

        self._summary_label.setText(
            f"📖 故事: {title}   │   "
            f"节点: {confirmed_count}/{total_nodes} 已确认   │   "
            f"总事件: {total_events}   │   "
            f"剔除事件: {pruned_events}   │   "
            f"角色/实体: {len(all_chars)}   │   "
            f"Hauge 阶段: {hauge_covered}/6   │   "
            f"故事连贯度: {coherence_text}"
        )

    # ------------------------------------------------------------------ #
    # ITE 全局评估（按事件数动态分批）
    # ------------------------------------------------------------------ #
    MAX_EVENTS_PER_BATCH = 20  # 每批最大事件数（防止 AI 输出截断）

    def _on_run_ite(self):
        """点击运行全局 ITE 评估"""
        all_confirmed = {
            k: v for k, v in self.project_data.confirmed_beats.items() if v
        }
        if not all_confirmed:
            QMessageBox.information(
                self, "提示", "没有已确认的 Beat 节点，无法进行 ITE 评估。"
            )
            return

        total_events = sum(
            len(v.get("causal_events", [])) for v in all_confirmed.values()
        )

        # 按节点编号排序后按事件数动态分批
        import re
        sorted_keys = sorted(
            all_confirmed.keys(),
            key=lambda k: int(re.search(r'(\d+)', k).group(1)) if re.search(r'(\d+)', k) else 9999
        )

        self._ite_batches = []
        current_batch = {}
        current_event_count = 0
        for key in sorted_keys:
            beat = all_confirmed[key]
            ev_count = len(beat.get("causal_events", []))
            # 如果加入后超过上限，且当前批次不为空，则先保存当前批次
            if current_event_count + ev_count > self.MAX_EVENTS_PER_BATCH and current_batch:
                self._ite_batches.append(current_batch)
                current_batch = {}
                current_event_count = 0
            current_batch[key] = beat
            current_event_count += ev_count
        if current_batch:
            self._ite_batches.append(current_batch)

        batch_count = len(self._ite_batches)

        reply = QMessageBox.question(
            self, "运行全局 ITE 评估",
            f"将对全剧 {len(all_confirmed)} 个节点的 {total_events} 个事件\n"
            f"进行因果贡献度评估（按事件数自动分为 {batch_count} 批）。\n\n"
            f"• 使用 AI 评估每个事件对终局达成的重要性\n"
            f"• 识别冗余事件（水戏）\n"
            f"• 计算全局故事连贯度\n\n"
            f"预计耗时 {batch_count * 15}-{batch_count * 40} 秒，确认开始？",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        app_logger.info(
            "锁定-ITE评估",
            f"开始全局 ITE 评估：{len(all_confirmed)} 个节点，{total_events} 个事件，分 {batch_count} 批",
        )

        self._ite_batch_index = 0
        self._ite_merged_evals = []
        self._ite_merged_warnings = []
        self._ite_coherence_values = []
        self._ite_cancelled = False

        self._set_ite_busy(True)
        self._run_next_ite_batch()

    def _run_next_ite_batch(self):
        """运行下一批 ITE 评估"""
        if self._ite_cancelled:
            return

        if self._ite_batch_index >= len(self._ite_batches):
            # 所有批次完成 → 合并结果
            self._finalize_ite()
            return

        batch = self._ite_batches[self._ite_batch_index]
        batch_keys = list(batch.keys())
        total_batches = len(self._ite_batches)
        batch_num = self._ite_batch_index + 1

        self.status_message.emit(
            f"📊 ITE 评估中… 第 {batch_num}/{total_batches} 批 "
            f"({', '.join(batch_keys)})"
        )

        self._ite_worker = ITEWorker(
            finale_condition=self.project_data.finale_condition,
            confirmed_beats=batch,
            cpg_edges=self.project_data.cpg_edges,
            ai_params={
                "temperature": SUGGESTED_TEMPERATURES["ite"],
                "top_p": 0.9,
                "top_k": 40,
                "max_tokens": 16384,
            },
        )
        self._ite_worker.progress.connect(self.status_message)
        self._ite_worker.finished.connect(self._on_ite_batch_done)
        self._ite_worker.error.connect(self._on_ite_batch_error)
        self._ite_worker.start()

    def _on_ite_batch_done(self, result: dict):
        """单批 ITE 完成 → 累积结果并启动下一批"""
        evals = result.get("event_evaluations", [])
        warnings = result.get("structural_warnings", [])
        coherence = result.get("full_story_coherence", 0.0)

        self._ite_merged_evals.extend(evals)
        self._ite_merged_warnings.extend(warnings)
        if coherence > 0:
            self._ite_coherence_values.append(coherence)

        batch_keys = list(self._ite_batches[self._ite_batch_index].keys())
        app_logger.info(
            "锁定-ITE评估",
            f"第 {self._ite_batch_index + 1}/{len(self._ite_batches)} 批完成 "
            f"({', '.join(batch_keys)})：{len(evals)} 个事件已评分",
        )

        self._ite_batch_index += 1
        self._run_next_ite_batch()

    def _on_ite_batch_error(self, msg: str):
        """单批 ITE 失败 → 记录警告，继续下一批"""
        batch_keys = list(self._ite_batches[self._ite_batch_index].keys())
        warning_msg = f"批次 {', '.join(batch_keys)} 评估失败: {msg}"
        self._ite_merged_warnings.append(warning_msg)

        app_logger.warning(
            "锁定-ITE评估",
            f"第 {self._ite_batch_index + 1} 批失败（不中断）: {msg}",
        )

        self._ite_batch_index += 1
        self._run_next_ite_batch()

    def _finalize_ite(self):
        """所有批次完成 → 合并最终结果"""
        self._set_ite_busy(False)

        # 合并连贯度：取平均值
        avg_coherence = (
            sum(self._ite_coherence_values) / len(self._ite_coherence_values)
            if self._ite_coherence_values else 0.0
        )

        # 去重警告
        unique_warnings = list(dict.fromkeys(self._ite_merged_warnings))

        merged_result = {
            "event_evaluations": self._ite_merged_evals,
            "structural_warnings": unique_warnings,
            "full_story_coherence": avg_coherence,
            "pruning_suggestions": [],
        }

        # 保存到 project_data（持久化）
        self.project_data.ite_results = merged_result

        evals = self._ite_merged_evals
        app_logger.success(
            "锁定-ITE评估",
            f"全局 ITE 评估完成：{len(evals)} 个事件已评分，连贯度 {avg_coherence:.0%}",
            f"结构警告 {len(unique_warnings)} 条",
        )

        # 刷新表格和显示
        self._update_stats()
        self._update_ite_display()
        self.status_message.emit(
            f"✅ ITE 评估完成：{len(evals)} 个事件已评分，故事连贯度 {avg_coherence:.0%}"
        )

    def _on_ite_error(self, msg: str):
        """ITE 评估失败"""
        self._set_ite_busy(False)
        app_logger.error("锁定-ITE评估", f"ITE 评估失败: {msg}")
        QMessageBox.critical(self, "ITE 评估失败", msg)
        self.status_message.emit("❌ ITE 评估失败: " + msg)

    def _on_cancel_ite(self):
        """用户主动取消 ITE 评估"""
        self._ite_cancelled = True
        if self._ite_worker and self._ite_worker.isRunning():
            app_logger.warning("锁定-ITE评估", "用户手动取消 ITE 评估")
            self._ite_worker.terminate()
            self._ite_worker.wait(2000)
            self._ite_worker = None
        self._ite_batches = []
        self._set_ite_busy(False)
        self.status_message.emit("❌ ITE 评估已取消")

    def _set_ite_busy(self, busy: bool):
        """切换 ITE 评估的忙碌状态"""
        self._btn_ite.setEnabled(not busy)
        self._btn_ite.setText("评估中…" if busy else "📊 运行全局 ITE 评估")
        self._btn_back.setEnabled(not busy)
        self._btn_export_json.setEnabled(not busy)
        self._btn_export_txt.setEnabled(not busy)
        self._btn_cancel_ite.setVisible(busy)
        self._ite_elapsed_label.setVisible(busy)
        if busy:
            self._ite_elapsed = 0
            self._ite_elapsed_label.setText("‣ 已耗时 0s")
            self._ite_timer.start()
        else:
            self._ite_timer.stop()
            self._ite_elapsed_label.setText("")

    def _on_ite_tick(self):
        """每秒更新耗时"""
        self._ite_elapsed += 1
        secs = self._ite_elapsed
        if secs < 60:
            time_str = f"{secs}s"
        else:
            time_str = f"{secs // 60}m{secs % 60:02d}s"

        batch_info = ""
        if hasattr(self, '_ite_batches') and self._ite_batches:
            batch_num = min(self._ite_batch_index + 1, len(self._ite_batches))
            batch_info = f" 第{batch_num}/{len(self._ite_batches)}批"

        self._ite_elapsed_label.setText(f"‣ 已耗时 {time_str}{batch_info}")
        self.status_message.emit(f"📊 ITE 评估中…{batch_info} 已耗时 {time_str}")

    def _update_ite_display(self):
        """根据 project_data.ite_results 刷新 ITE 结果展示区"""
        ite_results = self.project_data.ite_results or {}

        if not ite_results:
            self._ite_coherence_label.setText("故事连贯度: 未计算")
            self._ite_coherence_label.setStyleSheet(
                "font-weight: bold; padding: 4px 0; color: #95a5a6;"
            )
            self._ite_warnings_label.setText(
                "💡 点击「运行全局 ITE 评估」按钮，AI 将分析全剧每个事件对终局的因果贡献度"
            )
            self._ite_warnings_label.setStyleSheet("color: #7f8c8d;")
            self._ite_prunable_label.setText("")
            return

        # --- 连贯度 ---
        coherence = ite_results.get("full_story_coherence", 0.0)
        if coherence >= 0.7:
            c_color = "#27ae60"
            c_icon = "🟢"
        elif coherence >= 0.5:
            c_color = "#e67e22"
            c_icon = "🟡"
        else:
            c_color = "#e74c3c"
            c_icon = "🔴"
        self._ite_coherence_label.setText(
            f"{c_icon} 全局故事连贯度: {coherence:.0%}"
        )
        self._ite_coherence_label.setStyleSheet(
            f"font-weight: bold; padding: 4px 0; color: {c_color}; font-size: 14px;"
        )

        # --- 结构性警告 ---
        warnings = ite_results.get("structural_warnings", [])
        if warnings:
            w_lines = "\n".join(f"⚠️ {w}" for w in warnings)
            self._ite_warnings_label.setText(w_lines)
            self._ite_warnings_label.setStyleSheet("color: #e67e22;")
        else:
            self._ite_warnings_label.setText("✅ 无结构性警告")
            self._ite_warnings_label.setStyleSheet("color: #27ae60;")

        # --- 冗余事件 ---
        evals = ite_results.get("event_evaluations", [])
        redundant = [e for e in evals if e.get("verdict") == "冗余"]
        critical = [e for e in evals if e.get("verdict") == "关键"]
        important = [e for e in evals if e.get("verdict") == "重要"]
        normal = [e for e in evals if e.get("verdict") == "普通"]

        summary_parts = [f"共评估 {len(evals)} 个事件"]
        if critical:
            summary_parts.append(f"🔴 关键 {len(critical)}")
        if important:
            summary_parts.append(f"🟠 重要 {len(important)}")
        if normal:
            summary_parts.append(f"🟢 普通 {len(normal)}")
        if redundant:
            summary_parts.append(f"⚫ 冗余 {len(redundant)}")

        prunable_text = "  |  ".join(summary_parts)
        if redundant:
            prunable_text += "\n\n冗余事件（建议退回血肉阶段剔除）:"
            for ev in redundant:
                nid = ev.get("node_id", "")
                eid = ev.get("event_id", "")
                reason = ev.get("reasoning", "")
                prunable_text += f"\n  • {nid}-E{eid}: {reason}"

        self._ite_prunable_label.setText(prunable_text)
        self._ite_prunable_label.setStyleSheet(
            "color: #555; padding: 4px 0;"
        )

    # ------------------------------------------------------------------ #
    # 导出
    # ------------------------------------------------------------------ #
    def _on_export_json(self):
        name = self.project_data.story_title or "untitled"
        os.makedirs("projects", exist_ok=True)
        filepath, _ = QFileDialog.getSaveFileName(
            self, "导出项目",
            f"projects/{name}.story.json",
            "Story JSON (*.story.json);;All Files (*)",
        )
        if filepath:
            try:
                self.project_data.save_to_file(filepath)
                QMessageBox.information(self, "导出成功", f"项目已保存到:\n{filepath}")
                self.status_message.emit(f"✅ 已导出: {filepath}")
                app_logger.success("锁定-导出JSON", f"导出工程文件至：{filepath}")
            except Exception as e:
                QMessageBox.critical(self, "导出失败", str(e))
                app_logger.error("锁定-导出JSON", f"导出失败: {str(e)}")

    def _on_export_txt(self):
        """导出人类可读的 CPG 摘要文本"""
        name = self.project_data.story_title or "untitled"
        os.makedirs("projects", exist_ok=True)
        filepath, _ = QFileDialog.getSaveFileName(
            self, "导出摘要文本",
            f"projects/{name}_cpg_summary.txt",
            "Text Files (*.txt);;All Files (*)",
        )
        if not filepath:
            return

        lines = [
            f"故事：{self.project_data.story_title or '未命名'}",
            f"梗概：{self.project_data.sparkle}",
            f"终局条件：{self.project_data.finale_condition}",
            "",
            "=" * 60,
            "CPG 因果概率图 — 节拍摘要",
            "=" * 60,
        ]
        STAGE_NAMES = {1:"机会",2:"变点",3:"无路可退",4:"挫折",5:"高潮",6:"终局"}

        # 按节点编号数字排序
        import re
        sorted_nodes = sorted(
            self.project_data.cpg_nodes,
            key=lambda n: int(re.search(r'(\d+)', n.get('node_id', 'N0')).group(1))
                          if re.search(r'(\d+)', n.get('node_id', '')) else 9999
        )
        for node in sorted_nodes:
            nid = node.get("node_id", "")
            beat = self.project_data.confirmed_beats.get(nid)
            stage = STAGE_NAMES.get(node.get("hauge_stage_id", 0), "")
            lines += [
                "",
                f"【{nid}】{node.get('title', '')}  [{stage}]",
                f"  环境: {node.get('setting', '')}",
            ]
            if beat:
                lines.append(f"  选用人格: {beat.get('persona_name', '')}")
                lines.append(f"  环境(Beat): {beat.get('setting', '')}")
                lines.append(f"  角色: {', '.join(beat.get('entities', []))}")
                for ev in beat.get("causal_events", []):
                    pruned = " [已剔除]" if ev.get("is_pruned") else ""
                    ite = f"  ITE={ev.get('ite_score', -1):.3f}" if ev.get("ite_score", -1) >= 0 else ""
                    lines.append(f"  事件{ev.get('event_id', '')}:{pruned}{ite} {ev.get('action', '')}")
                    lines.append(f"    → {ev.get('causal_impact', '')}")
                lines.append(f"  悬念钩子: {beat.get('hook', '')}")
            else:
                lines.append("  （未生成 Beat）")

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            QMessageBox.information(self, "导出成功", f"摘要已保存到:\n{filepath}")
            self.status_message.emit(f"✅ 摘要已导出: {filepath}")
            app_logger.success("锁定-导出文本", f"导出CPG摘要文本至：{filepath}")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", str(e))
            app_logger.error("锁定-导出文本", f"导出失败: {str(e)}")
