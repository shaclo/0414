# ============================================================
# ui/phase2_skeleton.py
# Phase 2: 骨架 — CPG 骨架生成 + 可视化编辑
# ============================================================

import json
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QSplitter, QTextEdit, QMessageBox,
    QGroupBox, QInputDialog, QSpinBox, QFrame,
)
from PySide6.QtCore import Qt, Signal, QTimer

from env import SYSTEM_PROMPT_CPG_SKELETON, USER_PROMPT_CPG_SKELETON, SUGGESTED_TEMPERATURES
from services.worker import CPGSkeletonWorker
from ui.widgets.ai_settings_panel import AISettingsPanel
from ui.widgets.prompt_viewer import PromptViewer
from ui.widgets.cpg_graph_editor import CPGGraphEditor

STAGE_NAMES = {
    1: "机会 (Opportunity)",
    2: "变点 (Change of Plans)",
    3: "无路可退 (Point of No Return)",
    4: "主攻/挫折 (Major Setback)",
    5: "高潮 (Climax)",
    6: "终局 (Aftermath)",
}
STAGE_NAMES_SHORT = {1:"机会", 2:"变点", 3:"无路可退", 4:"挫折", 5:"高潮", 6:"终局"}


# ============================================================
# Loading 遮罩层组件
# ============================================================
class LoadingOverlay(QWidget):
    """
    半透明遮罩层：显示 Loading 动画 + 提示文字 + 计时器。
    覆盖在图编辑器上方，防止用户误以为卡死。
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setVisible(False)
        self._elapsed = 0
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)

        # 背景半透明
        self.setStyleSheet("background: rgba(0, 0, 0, 0);")

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)

        # 中心卡片
        card = QFrame()
        card.setFixedSize(360, 180)
        card.setStyleSheet(
            "QFrame {"
            "  background: rgba(255, 255, 255, 230);"
            "  border: 2px solid #3498db;"
            "  border-radius: 16px;"
            "}"
        )
        cl = QVBoxLayout(card)
        cl.setAlignment(Qt.AlignCenter)
        cl.setSpacing(12)

        # 动画文字
        self._anim_label = QLabel("⏳ 正在生成骨架...")
        self._anim_label.setAlignment(Qt.AlignCenter)
        self._anim_label.setStyleSheet(
            "font-size: 18px; font-weight: bold; color: #2c3e50; background: transparent;"
        )
        cl.addWidget(self._anim_label)

        # 提示
        hint = QLabel("AI 正在规划剧本结构\n大规模生成可能需要 30-120 秒")
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet("font-size: 12px; color: #7f8c8d; background: transparent;")
        hint.setWordWrap(True)
        cl.addWidget(hint)

        # 计时器
        self._time_label = QLabel("已等待: 0 秒")
        self._time_label.setAlignment(Qt.AlignCenter)
        self._time_label.setStyleSheet(
            "font-size: 14px; color: #2980b9; font-weight: bold; background: transparent;"
        )
        cl.addWidget(self._time_label)

        layout.addWidget(card)

        # 动画帧
        self._dots = 0

    def start(self):
        """启动遮罩"""
        self._elapsed = 0
        self._dots = 0
        self._time_label.setText("已等待: 0 秒")
        self.setVisible(True)
        self.raise_()
        self._timer.start()

    def stop(self):
        """关闭遮罩"""
        self._timer.stop()
        self.setVisible(False)

    def _tick(self):
        self._elapsed += 1
        self._time_label.setText(f"已等待: {self._elapsed} 秒")
        # 简单动画：跳动点
        self._dots = (self._dots + 1) % 4
        dots_str = "." * self._dots
        self._anim_label.setText(f"⏳ 正在生成骨架{dots_str}")

    def resizeEvent(self, event):
        """跟随父控件调整大小"""
        super().resizeEvent(event)


class Phase2Skeleton(QWidget):
    """
    Phase 2: 骨架阶段。
    上方: CPG 可视化图编辑器 + Loading 遮罩
    下方: 集数/时长配置 + 节点详情 + 控制按钮

    信号:
        phase_completed: 骨架确认，进入 Phase 3
        go_back: 返回 Phase 1
        status_message: 状态栏消息
    """

    phase_completed = Signal()
    go_back         = Signal()
    status_message  = Signal(str)

    def __init__(self, project_data, parent=None):
        super().__init__(parent)
        self.project_data = project_data
        self._worker = None
        self._selected_node_id = None
        self._setup_ui()

    # ------------------------------------------------------------------ #
    # UI
    # ------------------------------------------------------------------ #
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)

        splitter = QSplitter()
        splitter.setOrientation(Qt.Vertical)

        # 图编辑器容器（叠加 Loading 遮罩）
        graph_container = QWidget()
        gc_layout = QVBoxLayout(graph_container)
        gc_layout.setContentsMargins(0, 0, 0, 0)

        self._cpg_editor = CPGGraphEditor()
        self._cpg_editor.node_selected.connect(self._on_node_selected)
        gc_layout.addWidget(self._cpg_editor)

        # Loading 遮罩（叠在图编辑器上面）
        self._loading_overlay = LoadingOverlay(graph_container)

        splitter.addWidget(graph_container)

        # 下方控制区
        bottom = QWidget()
        bl = QVBoxLayout(bottom)
        bl.setContentsMargins(0, 0, 0, 0)

        # --- 剧本结构配置 ---
        config_group = QGroupBox("📐 剧本结构配置")
        config_layout = QHBoxLayout(config_group)

        config_layout.addWidget(QLabel("总集数:"))
        self._episodes_spin = QSpinBox()
        self._episodes_spin.setRange(1, 200)
        self._episodes_spin.setValue(self.project_data.total_episodes)
        self._episodes_spin.setToolTip("整个剧本的总集数，每集对应一个 CPG 节点")
        self._episodes_spin.setMinimumWidth(80)
        self._episodes_spin.valueChanged.connect(self._on_config_changed)
        config_layout.addWidget(self._episodes_spin)

        config_layout.addWidget(QLabel("  每集时长:"))
        self._duration_spin = QSpinBox()
        self._duration_spin.setRange(1, 30)
        self._duration_spin.setValue(self.project_data.episode_duration)
        self._duration_spin.setSuffix(" 分钟")
        self._duration_spin.setToolTip("每集的目标时长（分钟），影响扩写时的字数控制")
        self._duration_spin.setMinimumWidth(100)
        self._duration_spin.valueChanged.connect(self._on_config_changed)
        config_layout.addWidget(self._duration_spin)

        config_layout.addWidget(QLabel("  ≈ 每集"))
        self._word_count_label = QLabel("")
        self._word_count_label.setStyleSheet("color: #2980b9; font-weight: bold;")
        config_layout.addWidget(self._word_count_label)
        self._update_word_count_hint()

        config_layout.addStretch()
        bl.addWidget(config_group)

        # --- 节点详情 ---
        detail_group = QGroupBox("选中节点详情 (点击图中节点)")
        dl = QVBoxLayout(detail_group)
        self._detail_text = QTextEdit()
        self._detail_text.setMaximumHeight(120)
        self._detail_text.setReadOnly(True)
        self._detail_text.setPlaceholderText("点击图中的节点查看详情...")
        dl.addWidget(self._detail_text)

        edit_row = QHBoxLayout()
        self._btn_edit_node = QPushButton("编辑标题")
        self._btn_edit_node.setEnabled(False)
        self._btn_edit_node.clicked.connect(self._on_edit_node)
        edit_row.addWidget(self._btn_edit_node)

        self._btn_delete_node = QPushButton("删除节点")
        self._btn_delete_node.setEnabled(False)
        self._btn_delete_node.clicked.connect(self._on_delete_node)
        edit_row.addWidget(self._btn_delete_node)
        edit_row.addStretch()
        dl.addLayout(edit_row)
        bl.addWidget(detail_group)

        self._ai_settings = AISettingsPanel(suggested_temp=SUGGESTED_TEMPERATURES["cpg_skeleton"])
        bl.addWidget(self._ai_settings)

        self._prompt_viewer = PromptViewer()
        self._prompt_viewer.set_prompt(SYSTEM_PROMPT_CPG_SKELETON, USER_PROMPT_CPG_SKELETON)
        bl.addWidget(self._prompt_viewer)

        splitter.addWidget(bottom)
        splitter.setSizes([450, 350])
        layout.addWidget(splitter)

        # 底部按钮
        btn_row = QHBoxLayout()
        self._btn_back = QPushButton("<- 返回创世")
        self._btn_back.clicked.connect(self.go_back.emit)
        btn_row.addWidget(self._btn_back)

        self._btn_regen = QPushButton("重新生成骨架")
        self._btn_regen.clicked.connect(self._on_generate)
        btn_row.addWidget(self._btn_regen)

        btn_row.addStretch()

        self._btn_next = QPushButton("进入血肉阶段 ->")
        self._btn_next.setMinimumHeight(36)
        self._btn_next.setStyleSheet(
            "QPushButton{background:#27ae60;color:white;font-weight:bold;"
            "border-radius:5px;border:none;}"
            "QPushButton:hover{background:#229954;}"
            "QPushButton:disabled{background:#bdc3c7;color:#888;}"
        )
        self._btn_next.clicked.connect(self._on_proceed)
        btn_row.addWidget(self._btn_next)
        layout.addLayout(btn_row)

    # ------------------------------------------------------------------ #
    # 配置变更
    # ------------------------------------------------------------------ #
    def _on_config_changed(self):
        self.project_data.total_episodes = self._episodes_spin.value()
        self.project_data.episode_duration = self._duration_spin.value()
        self._update_word_count_hint()
        self._update_dynamic_max_tokens()

    def _update_word_count_hint(self):
        duration = self._duration_spin.value()
        words = duration * 180
        self._word_count_label.setText(f"{words} 字 (≈{duration}分钟×180字/分)")

    def _update_dynamic_max_tokens(self):
        """根据集数动态调整 max_tokens，确保 AI 有足够空间输出完整 JSON"""
        episodes = self._episodes_spin.value()
        # 每集约 500 tokens 的 JSON 输出 + 6000 基础开销（边、元数据等）
        estimated_tokens = episodes * 500 + 6000
        # 下限 16384，上限 65536（Gemini 2.5 Flash 输出上限）
        target = max(16384, min(65536, estimated_tokens))
        self._ai_settings.set_max_tokens(target)

    # ------------------------------------------------------------------ #
    # 生命周期
    # ------------------------------------------------------------------ #
    def on_enter(self):
        # 同步 UI 与 project_data
        self._episodes_spin.setValue(self.project_data.total_episodes)
        self._duration_spin.setValue(self.project_data.episode_duration)
        self._update_word_count_hint()
        self._update_dynamic_max_tokens()

        if self.project_data.cpg_nodes:
            self._load_to_editor()
        else:
            # 不自动生成——让用户先调整集数和时长，然后手动点击"生成骨架"
            self.status_message.emit("请先设置总集数和每集时长，然后点击「重新生成骨架」")

    # ------------------------------------------------------------------ #
    # Loading 遮罩
    # ------------------------------------------------------------------ #
    def _show_loading(self):
        """显示 Loading 遮罩"""
        # 调整遮罩大小到图编辑器区域
        parent = self._loading_overlay.parent()
        if parent:
            self._loading_overlay.setGeometry(parent.rect())
        self._loading_overlay.start()

    def _hide_loading(self):
        """隐藏 Loading 遮罩"""
        self._loading_overlay.stop()

    def resizeEvent(self, event):
        """窗口大小变化时同步遮罩大小"""
        super().resizeEvent(event)
        parent = self._loading_overlay.parent()
        if parent and self._loading_overlay.isVisible():
            self._loading_overlay.setGeometry(parent.rect())

    # ------------------------------------------------------------------ #
    # AI-Call-3: CPG 骨架生成
    # ------------------------------------------------------------------ #
    def _on_generate(self):
        if not self.project_data.sparkle:
            QMessageBox.warning(self, "提示", "请先完成创世阶段！")
            return
        self._set_busy(True)
        self._show_loading()

        self._worker = CPGSkeletonWorker(
            sparkle=self.project_data.sparkle,
            world_variables=self.project_data.world_variables,
            finale_condition=self.project_data.finale_condition,
            ai_params=self._ai_settings.get_all_settings(),
            characters=self.project_data.characters,
            total_episodes=self._episodes_spin.value(),
            episode_duration=self._duration_spin.value(),
        )
        self._worker.progress.connect(self.status_message)
        self._worker.finished.connect(self._on_skeleton_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_skeleton_done(self, result: dict):
        self._set_busy(False)
        self._hide_loading()

        nodes = []
        for stage in result.get("hauge_stages", []):
            sid   = stage.get("stage_id", 1)
            sname = stage.get("stage_name", STAGE_NAMES.get(sid, ""))
            for n in stage.get("nodes", []):
                nodes.append({
                    "node_id":         n.get("node_id", ""),
                    "title":           n.get("title", ""),
                    "hauge_stage_id":  sid,
                    "hauge_stage_name": sname,
                    "setting":         n.get("setting", ""),
                    "characters":      n.get("characters", []),
                    "event_summaries": n.get("event_summaries", []),
                    "emotional_tone":  n.get("emotional_tone", ""),
                    "episode_hook":    n.get("episode_hook", ""),
                    "status":          "pending",
                })

        self.project_data.cpg_title  = result.get("cpg_title", "")
        self.project_data.cpg_nodes  = nodes
        self.project_data.cpg_edges  = result.get("causal_edges", [])
        self.project_data.hauge_stages = result.get("hauge_stages", [])
        self.project_data.push_history("generate_skeleton")
        self._load_to_editor()
        self.status_message.emit(
            f"CPG 骨架完成: {len(nodes)} 集/节点, {len(self.project_data.cpg_edges)} 条边"
        )

    def _load_to_editor(self):
        self._cpg_editor.load_cpg(
            self.project_data.cpg_nodes,
            self.project_data.cpg_edges,
        )

    # ------------------------------------------------------------------ #
    # 节点交互
    # ------------------------------------------------------------------ #
    def _on_node_selected(self, node_id: str):
        self._selected_node_id = node_id
        self._btn_edit_node.setEnabled(True)
        self._btn_delete_node.setEnabled(True)

        node = next((n for n in self.project_data.cpg_nodes if n["node_id"] == node_id), None)
        if not node:
            return
        stage = STAGE_NAMES_SHORT.get(node.get("hauge_stage_id", 1), "")
        events = "\n".join(
            f"  {i+1}. {e}" for i, e in enumerate(node.get("event_summaries", []))
        )
        hook = node.get("episode_hook", "")
        self._detail_text.setPlainText(
            f"节点: {node_id}   阶段: {stage}\n"
            f"标题: {node.get('title','')}\n"
            f"环境: {node.get('setting','')}\n"
            f"角色: {', '.join(node.get('characters',[]))}\n"
            f"事件:\n{events}\n"
            f"情感: {node.get('emotional_tone','')}\n"
            f"本集钩子: {hook}"
        )

    def _on_edit_node(self):
        if not self._selected_node_id:
            return
        node = next(
            (n for n in self.project_data.cpg_nodes if n["node_id"] == self._selected_node_id),
            None,
        )
        if not node:
            return
        new_title, ok = QInputDialog.getText(
            self, "编辑节点标题", "标题:", text=node.get("title", "")
        )
        if ok and new_title.strip():
            node["title"] = new_title.strip()
            self._load_to_editor()
            self.status_message.emit(f"节点 {self._selected_node_id} 已更新")

    def _on_delete_node(self):
        if not self._selected_node_id:
            return
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定删除节点 {self._selected_node_id}？相关边也会被删除。",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.No:
            return
        nid = self._selected_node_id
        self.project_data.cpg_nodes = [
            n for n in self.project_data.cpg_nodes if n["node_id"] != nid
        ]
        self.project_data.cpg_edges = [
            e for e in self.project_data.cpg_edges
            if e.get("from_node") != nid and e.get("to_node") != nid
        ]
        self._selected_node_id = None
        self._btn_edit_node.setEnabled(False)
        self._btn_delete_node.setEnabled(False)
        self._detail_text.clear()
        self._load_to_editor()

    # ------------------------------------------------------------------ #
    # 进入 Phase 3
    # ------------------------------------------------------------------ #
    def _on_proceed(self):
        if not self.project_data.cpg_nodes:
            QMessageBox.warning(self, "提示", "请先生成 CPG 骨架！")
            return
        for node in self.project_data.cpg_nodes:
            nid = node.get("node_id", "")
            if nid and nid not in self.project_data.confirmed_beats:
                self.project_data.confirmed_beats[nid] = None
        self.project_data.current_phase       = "flesh"
        self.project_data.current_node_index  = 0
        self.project_data.push_history("enter_flesh")
        self.phase_completed.emit()

    # ------------------------------------------------------------------ #
    # 工具
    # ------------------------------------------------------------------ #
    def _set_busy(self, busy: bool):
        self._btn_regen.setEnabled(not busy)
        self._btn_next.setEnabled(not busy)
        self._btn_back.setEnabled(not busy)
        self._episodes_spin.setEnabled(not busy)
        self._duration_spin.setEnabled(not busy)
        self._btn_regen.setText("处理中..." if busy else "重新生成骨架")

    def _on_error(self, msg: str):
        self._set_busy(False)
        self._hide_loading()
        QMessageBox.critical(self, "AI 调用失败", msg)
        self.status_message.emit("错误: " + msg)
