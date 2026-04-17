# ============================================================
# ui/widgets/split_dialog.py
# 节点拆分对话框
# 支持: 无限层级拆分 / 用户分配事件 / 拆分后 AI 补全或扩写
# ============================================================

import json
import copy
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QListWidget, QListWidgetItem, QWidget, QGroupBox,
    QRadioButton, QButtonGroup, QSplitter, QMessageBox, QScrollArea,
)
from PySide6.QtCore import Qt

from models.project_state import add_version, make_node_snapshot


class SplitDialog(QDialog):
    """
    节点拆分对话框。

    1. 选择拆分数量（2~5）
    2. 每个事件通过下拉框分配到目标片段
    3. 显示片段预览
    4. 选择拆分后处理: 仅拆分 / 补全 / 扩写
    5. 执行拆分 → 修改 project_data.cpg_nodes / cpg_edges
    """

    def __init__(self, node: dict, project_data, parent=None):
        super().__init__(parent)
        self._node = node
        self._pd   = project_data
        self._worker = None

        nid = node.get("node_id", "")
        self.setWindowTitle(f"✂️ 拆分 {nid} — {node.get('title','')}")
        self.setMinimumSize(700, 500)
        self._setup_ui()

    # ------------------------------------------------------------------ #
    # UI 构建
    # ------------------------------------------------------------------ #
    def _setup_ui(self):
        root = QVBoxLayout(self)

        # 拆分数量
        cnt_row = QHBoxLayout()
        cnt_row.addWidget(QLabel("拆分数量:"))
        self._cnt_combo = QComboBox()
        for i in range(2, 6):
            self._cnt_combo.addItem(str(i), i)
        self._cnt_combo.currentIndexChanged.connect(self._on_count_changed)
        cnt_row.addWidget(self._cnt_combo)
        cnt_row.addStretch()
        root.addLayout(cnt_row)

        # 事件分配
        root.addWidget(QLabel("📌 将每个事件分配到目标片段 (双击某片段列表可改变分配):"))
        self._events_area = self._build_events_assign()
        root.addWidget(self._events_area)

        # 片段预览
        root.addWidget(QLabel("📌 片段预览 (每列为一个子集):"))
        self._preview_area = QWidget()
        self._preview_layout = QHBoxLayout(self._preview_area)
        root.addWidget(self._preview_area)
        self._refresh_preview()

        # 处理模式
        root.addWidget(QLabel("📌 拆分后处理:"))
        mode_widget = QWidget()
        mode_layout = QHBoxLayout(mode_widget)
        self._rb_split_only = QRadioButton("仅拆分 — 只分配事件，其余字段手动填写")
        self._rb_fill       = QRadioButton("补全  — AI 补全标题/钩子/情感（不改事件）")
        self._rb_expand     = QRadioButton("扩写  — AI 充实事件细节（保持风格）")
        self._rb_split_only.setChecked(True)
        for rb in (self._rb_split_only, self._rb_fill, self._rb_expand):
            mode_layout.addWidget(rb)
        mode_layout.addStretch()
        root.addWidget(mode_widget)

        # 按钮
        btn_row = QHBoxLayout()
        btn_exec = QPushButton("✂️ 执行拆分")
        btn_exec.clicked.connect(self._do_split)
        btn_row.addWidget(btn_exec)
        btn_row.addStretch()
        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)
        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color:#27ae60;")
        btn_row.addWidget(self._status_label)
        root.addLayout(btn_row)

    def _build_events_assign(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        events = self._node.get("event_summaries", [])
        self._event_combos = []   # list of QComboBox, one per event

        for i, ev in enumerate(events):
            row = QHBoxLayout()
            row.addWidget(QLabel(f"事件 {i+1}: {ev[:40]}…" if len(ev) > 40 else f"事件 {i+1}: {ev}"))
            combo = QComboBox()
            self._populate_frag_combo(combo)
            combo.currentIndexChanged.connect(self._refresh_preview)
            self._event_combos.append(combo)
            row.addStretch()
            row.addWidget(QLabel("→ 分配到片段"))
            row.addWidget(combo)
            layout.addLayout(row)

        if not events:
            layout.addWidget(QLabel("（本节点没有事件摘要）"))
        return widget

    def _populate_frag_combo(self, combo: QComboBox):
        combo.clear()
        cnt = self._cnt_combo.currentData() or 2
        for i in range(1, cnt + 1):
            combo.addItem(f"片段 {i}", i)

    def _on_count_changed(self):
        for combo in self._event_combos:
            cur = combo.currentData()
            self._populate_frag_combo(combo)
            # 保留原分配（若超出范围则归到最后一片段）
            cnt = self._cnt_combo.currentData() or 2
            target = min(cur or 1, cnt)
            combo.setCurrentIndex(target - 1)
        self._refresh_preview()

    def _refresh_preview(self):
        # 清空预览区
        while self._preview_layout.count():
            item = self._preview_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        cnt = self._cnt_combo.currentData() or 2
        events = self._node.get("event_summaries", [])
        frag_events = {i: [] for i in range(1, cnt + 1)}
        for idx, combo in enumerate(self._event_combos):
            frag_idx = combo.currentData() or 1
            if idx < len(events):
                frag_events[frag_idx].append(events[idx])

        nid = self._node.get("node_id", "")
        for frag_i in range(1, cnt + 1):
            group = QGroupBox(f"{nid}.{frag_i}")
            gv = QVBoxLayout(group)
            fev = frag_events[frag_i]
            if fev:
                for ev in fev:
                    lbl = QLabel(f"• {ev[:30]}…" if len(ev) > 30 else f"• {ev}")
                    lbl.setWordWrap(True)
                    gv.addWidget(lbl)
            else:
                gv.addWidget(QLabel("（无事件）"))
            self._preview_layout.addWidget(group)

    # ------------------------------------------------------------------ #
    # 执行拆分
    # ------------------------------------------------------------------ #
    def _do_split(self):
        cnt = self._cnt_combo.currentData() or 2
        events = self._node.get("event_summaries", [])
        frag_events = {i: [] for i in range(1, cnt + 1)}
        for idx, combo in enumerate(self._event_combos):
            frag_idx = combo.currentData() or 1
            if idx < len(events):
                frag_events[frag_idx].append(events[idx])

        # 保存全局结构快照
        self._pd.push_history("split_node", self._node.get("node_id", ""))

        if self._rb_split_only.isChecked():
            self._apply_split(frag_events, cnt, None)
        else:
            mode = "fill" if self._rb_fill.isChecked() else "expand"
            self._launch_split_refine(frag_events, cnt, mode)

    def _apply_split(self, frag_events: dict, cnt: int, refined_nodes: list | None):
        """将拆分结果写入 project_data"""
        parent_id = self._node.get("node_id", "")
        original_snap = make_node_snapshot(self._node)

        new_nodes = []
        for frag_i in range(1, cnt + 1):
            child_id = f"{parent_id}.{frag_i}"
            if refined_nodes and frag_i - 1 < len(refined_nodes):
                snap = refined_nodes[frag_i - 1]
            else:
                # 默认: 继承原节点基本属性，事件按分配
                snap = copy.deepcopy(original_snap)
                snap["event_summaries"] = frag_events.get(frag_i, [])
                if frag_i < cnt:
                    snap["episode_hook"] = f"（待填写：{child_id} 的悬念钩子）"
                snap["title"] = f"{original_snap.get('title','')} ({frag_i}/{cnt})"

            child_node = {
                "node_id":          child_id,
                "hauge_stage_id":   self._node.get("hauge_stage_id", 1),
                "hauge_stage_name": self._node.get("hauge_stage_name", ""),
                "status":           "pending",
                "origin":           f"split_from:{parent_id}",
            }
            # 应用快照字段
            for k, v in snap.items():
                child_node[k] = v
            # 创建 v0 版本
            add_version(child_node, "split", f"拆分自 {parent_id}")
            new_nodes.append(child_node)

        # 原节点的入口边 → 第一个子节点
        # 原节点的出口边 → 最后一个子节点
        # 子节点之间创建顺序边
        edges = self._pd.cpg_edges
        in_edges  = [e for e in edges if e.get("to_node")   == parent_id]
        out_edges = [e for e in edges if e.get("from_node") == parent_id]

        # 移除原节点的所有边
        edges[:] = [e for e in edges
                    if e.get("to_node") != parent_id and e.get("from_node") != parent_id]

        first_id = new_nodes[0]["node_id"]
        last_id  = new_nodes[-1]["node_id"]

        # 入口边 → 第一个子节点
        for e in in_edges:
            edges.append({"from_node": e["from_node"], "to_node": first_id,
                          "relation": e.get("relation", "causal")})
        # 出口边 → 最后一个子节点
        for e in out_edges:
            edges.append({"from_node": last_id, "to_node": e["to_node"],
                          "relation": e.get("relation", "causal")})
        # 子节点之间顺序边
        for i in range(len(new_nodes) - 1):
            edges.append({"from_node": new_nodes[i]["node_id"],
                          "to_node":   new_nodes[i+1]["node_id"],
                          "relation":  "causal"})

        # 替换 cpg_nodes 中的原节点
        nodes = self._pd.cpg_nodes
        idx = next((i for i, n in enumerate(nodes) if n.get("node_id") == parent_id), -1)
        if idx >= 0:
            nodes[idx:idx+1] = new_nodes
        else:
            nodes.extend(new_nodes)

        self.accept()

    def _launch_split_refine(self, frag_events: dict, cnt: int, mode: str):
        """调用 AI 补全/扩写拆分后的片段"""
        from env import SYSTEM_PROMPT_NODE_SPLIT_REFINE, USER_PROMPT_NODE_SPLIT_REFINE
        from services.worker import NodeRefineWorker

        fragments = [
            {"fragment": i, "event_summaries": frag_events.get(i, [])}
            for i in range(1, cnt + 1)
        ]
        sys_p = (SYSTEM_PROMPT_NODE_SPLIT_REFINE
                 .replace("{split_count}", str(cnt))
                 .replace("{process_mode}", mode)
                 .replace("{original_node_json}",
                          json.dumps(make_node_snapshot(self._node), ensure_ascii=False, indent=2))
                 .replace("{split_fragments_json}",
                          json.dumps(fragments, ensure_ascii=False, indent=2)))
        usr_p = USER_PROMPT_NODE_SPLIT_REFINE

        self._status_label.setText("⏳ AI 正在处理拆分方案…")
        self._worker = NodeRefineWorker("split_refine", sys_p, usr_p,
                                        {"temperature": 0.7, "max_tokens": 4096})
        self._worker.finished.connect(
            lambda r: self._on_split_refine_done(r, frag_events, cnt)
        )
        self._worker.error.connect(
            lambda e: (setattr(self, '_worker', None),
                       self._status_label.setText(f"❌ {e}"),
                       QMessageBox.warning(self, "AI 处理失败", e))
        )
        self._worker.start()

    def _on_split_refine_done(self, result: dict, frag_events: dict, cnt: int):
        self._worker = None
        nodes = result.get("nodes", [])
        if not nodes:
            QMessageBox.warning(self, "AI 处理失败",
                                "AI 未返回有效的拆分内容，将使用基础拆分。")
            self._apply_split(frag_events, cnt, None)
        else:
            self._apply_split(frag_events, cnt, nodes)
