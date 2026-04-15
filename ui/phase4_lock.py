# ============================================================
# ui/phase4_lock.py
# Phase 4: 锁定 — 最终审阅、统计摘要、导出
# ============================================================

import json
import os
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QGroupBox, QTableWidget, QTableWidgetItem,
    QFileDialog, QMessageBox, QHeaderView, QSplitter,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor

from ui.widgets.cpg_graph_editor import CPGGraphEditor


class Phase4Lock(QWidget):
    """
    Phase 4: 锁定阶段界面。

    上方: 完整 CPG 图（只读）
    下方: 统计摘要表 + 导出按钮

    信号:
        go_back_to_flesh: 返回 Phase 3 继续修改
        status_message: 状态栏消息
    """

    go_back_to_flesh = Signal()
    status_message = Signal(str)

    def __init__(self, project_data, parent=None):
        super().__init__(parent)
        self.project_data = project_data
        self._setup_ui()

    # ------------------------------------------------------------------ #
    # UI 构建
    # ------------------------------------------------------------------ #
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)

        title = QLabel(f"🔒 CPG 已完成 — 因果概率图总览")
        title.setStyleSheet("font-size: 16px; font-weight: bold; margin-bottom: 4px;")
        layout.addWidget(title)

        splitter = QSplitter(Qt.Vertical)

        # ===== 上方: CPG 图（只读） =====
        self._cpg_editor = CPGGraphEditor()
        # 禁用节点拖动（只读模式）
        splitter.addWidget(self._cpg_editor)

        # ===== 下方: 统计 =====
        bottom = QWidget()
        bl = QVBoxLayout(bottom)
        bl.setContentsMargins(0, 0, 0, 0)

        # 摘要标签行
        self._summary_label = QLabel("")
        self._summary_label.setStyleSheet(
            "font-size: 13px; padding: 8px; background: #ecf0f1; "
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
        self._stats_table.setMaximumHeight(200)
        self._stats_table.setEditTriggers(QTableWidget.NoEditTriggers)
        slyt.addWidget(self._stats_table)
        bl.addWidget(stats_group)

        splitter.addWidget(bottom)
        splitter.setSizes([450, 300])
        layout.addWidget(splitter)

        # ===== 按钮行 =====
        btn_row = QHBoxLayout()
        self._btn_back = QPushButton("← 返回血肉阶段继续修改")
        self._btn_back.clicked.connect(self.go_back_to_flesh.emit)
        btn_row.addWidget(self._btn_back)
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
        self._load_cpg()
        self._update_stats()
        self.status_message.emit("CPG 已锁定，可导出项目")

    def _load_cpg(self):
        """加载 CPG 图（标记所有已确认节点）"""
        nodes = []
        for n in self.project_data.cpg_nodes:
            nid = n.get("node_id", "")
            node_copy = dict(n)
            node_copy["status"] = "confirmed" if self.project_data.confirmed_beats.get(nid) else "pending"
            nodes.append(node_copy)
        self._cpg_editor.load_cpg(nodes, self.project_data.cpg_edges)

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

        for row, node in enumerate(nodes):
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
            except Exception as e:
                QMessageBox.critical(self, "导出失败", str(e))

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

        for node in self.project_data.cpg_nodes:
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
        except Exception as e:
            QMessageBox.critical(self, "导出失败", str(e))
