# ============================================================
# ui/phase2_skeleton.py
# Phase 2: 骨架 — CPG 骨架生成 + 可视化编辑
# ============================================================

import json
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QSplitter, QTextEdit, QMessageBox,
    QGroupBox, QInputDialog, QSpinBox, QFrame, QComboBox, QLineEdit,
    QListWidget, QListWidgetItem, QDialog, QDialogButtonBox, QFormLayout, QCheckBox,
    QSlider,
)
from PySide6.QtCore import Qt, Signal, QTimer, QSize
from PySide6.QtGui import QColor

from ui.widgets.range_slider import DurationRangeWidget

from env import SYSTEM_PROMPT_CPG_SKELETON, USER_PROMPT_CPG_SKELETON, SUGGESTED_TEMPERATURES
from services.worker import CPGSkeletonWorker
from services.logger_service import app_logger
from ui.widgets.ai_settings_panel import AISettingsPanel
from ui.widgets.prompt_viewer import PromptViewer

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
            " font-weight: bold; color: #2c3e50; background: transparent;"
        )
        cl.addWidget(self._anim_label)

        # 提示
        hint = QLabel("AI 正在规划剧本结构\n大规模生成可能需要 30-120 秒")
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet(" color: #7f8c8d; background: transparent;")
        hint.setWordWrap(True)
        cl.addWidget(hint)

        # 计时器
        self._time_label = QLabel("已等待: 0 秒")
        self._time_label.setAlignment(Qt.AlignCenter)
        self._time_label.setStyleSheet(
            " color: #2980b9; font-weight: bold; background: transparent;"
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

        # 卡片式节点列表（轻量高性能，替代 CPGGraphEditor）
        graph_container = QWidget()
        gc_layout = QVBoxLayout(graph_container)
        gc_layout.setContentsMargins(0, 0, 0, 0)

        self._node_list = QListWidget()
        self._node_list.setViewMode(QListWidget.IconMode)
        self._node_list.setResizeMode(QListWidget.Adjust)
        self._node_list.setWrapping(True)
        self._node_list.setSpacing(6)
        self._node_list.setSelectionMode(QListWidget.SingleSelection)
        self._node_list.setWordWrap(True)
        self._node_list.setIconSize(QSize(0, 0))
        self._node_list.setGridSize(QSize(200, 72))
        self._node_list.setStyleSheet("""
            QListWidget { background: #f5f6fa; border: 1px solid #dcdde1; border-radius: 6px; }
            QListWidget::item {
                background: #ffffff; border: 1px solid #dcdde1; border-radius: 6px;
                padding: 6px 8px; margin: 2px;
            }
            QListWidget::item:selected {
                background: #dfe6e9; border: 2px solid #0984e3;
            }
            QListWidget::item:hover {
                background: #f0f3f8; border: 1px solid #74b9ff;
            }
        """)
        self._node_list.itemDoubleClicked.connect(self._on_card_double_clicked)
        gc_layout.addWidget(self._node_list)

        # Loading 遮罩
        self._loading_overlay = LoadingOverlay(graph_container)

        splitter.addWidget(graph_container)

        # 下方控制区（使用 ScrollArea 避免挤压）
        bottom = QWidget()
        bl = QVBoxLayout(bottom)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(2)

        # --- 剧本结构配置（默认展开） ---
        config_group, config_inner = self._make_collapsible("📐 剧本结构配置", expanded=True)
        config_layout = QHBoxLayout()

        config_layout.addWidget(QLabel("总集数:"))
        self._episodes_spin = QSpinBox()
        self._episodes_spin.setRange(1, 200)
        self._episodes_spin.setValue(self.project_data.total_episodes)
        self._episodes_spin.setToolTip("整个剧本的总集数，每集对应一个 CPG 节点")
        self._episodes_spin.setMinimumWidth(80)
        self._episodes_spin.valueChanged.connect(self._on_config_changed)
        config_layout.addWidget(self._episodes_spin)

        # 每集时长区间 (Range Slider)
        self._duration_range = DurationRangeWidget(
            min_val=0.5, max_val=30.0,
            low=self.project_data.episode_duration_min,
            high=self.project_data.episode_duration_max,
        )
        self._duration_range.rangeChanged.connect(self._on_config_changed)
        config_layout.addWidget(self._duration_range)

        config_layout.addWidget(QLabel("  ≈ 每集"))
        self._word_count_label = QLabel("")
        self._word_count_label.setStyleSheet("color: #2980b9; font-weight: bold;")
        config_layout.addWidget(self._word_count_label)
        self._update_word_count_hint()

        config_layout.addStretch()
        config_inner.addLayout(config_layout)

        bl.addWidget(config_group)

        # 节点详情已改为双击卡片弹窗，不再需要内嵌面板

        # --- AI 设置（默认折叠） ---
        ai_group, ai_inner = self._make_collapsible("⚙️ AI 调用设置", expanded=False)
        self._ai_settings = AISettingsPanel(suggested_temp=SUGGESTED_TEMPERATURES["cpg_skeleton"])
        ai_inner.addWidget(self._ai_settings)
        bl.addWidget(ai_group)

        # --- Prompt 查看器（默认折叠） ---
        prompt_group, prompt_inner = self._make_collapsible("📝 Prompt 模板预览", expanded=False)
        self._prompt_viewer = PromptViewer()
        self._prompt_viewer.set_prompt(SYSTEM_PROMPT_CPG_SKELETON, USER_PROMPT_CPG_SKELETON)
        prompt_inner.addWidget(self._prompt_viewer)
        bl.addWidget(prompt_group)

        bl.addStretch()
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
    # 折叠面板辅助
    # ------------------------------------------------------------------ #
    @staticmethod
    def _make_collapsible(title: str, expanded: bool = True):
        """
        创建可折叠的 QGroupBox。
        返回 (group_box, inner_layout)。
        点击标题栏的勾选框来展开/折叠。
        """
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

        # 勾选框控制展开/折叠
        group.toggled.connect(inner_widget.setVisible)

        return group, inner_layout

    # ------------------------------------------------------------------ #
    # 配置变更
    # ------------------------------------------------------------------ #
    def _on_config_changed(self, *_args):
        self.project_data.total_episodes = self._episodes_spin.value()
        # 时长区间
        dur_min = self._duration_range.low()
        dur_max = self._duration_range.high()
        self.project_data.episode_duration_min = dur_min
        self.project_data.episode_duration_max = dur_max
        self.project_data.episode_duration = int((dur_min + dur_max) / 2)  # 向后兼容
        self._update_word_count_hint()
        self._update_dynamic_max_tokens()

    def _update_word_count_hint(self):
        dur_min = self._duration_range.low()
        dur_max = self._duration_range.high()
        words_min = int(dur_min * 180)
        words_max = int(dur_max * 180)
        self._word_count_label.setText(f"{words_min}-{words_max} 字")

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
        self._duration_range.setValues(
            self.project_data.episode_duration_min,
            self.project_data.episode_duration_max,
        )
        self._update_word_count_hint()
        self._update_dynamic_max_tokens()

        if self.project_data.cpg_nodes:
            self._load_to_editor()
        else:
            self.status_message.emit("请先设置总集数和每集时长，然后点击「重新生成骨架」")

    # ------------------------------------------------------------------ #
    # 卡片列表
    # ------------------------------------------------------------------ #
    def _load_to_editor(self):
        """将 cpg_nodes 渲染到卡片网格"""
        self._node_list.clear()
        sorted_nodes = sorted(
            self.project_data.cpg_nodes,
            key=lambda n: self._parse_ep_num(n.get("node_id", ""))
        )
        for node in sorted_nodes:
            nid = node.get("node_id", "")
            title = node.get("title", "")
            stage = STAGE_NAMES_SHORT.get(node.get("hauge_stage_id", 1), "")
            # 版本标记：显示激活版本号
            versions = node.get("versions", [])
            if versions:
                active_v = node.get("active_version", 0)
                ver_tag = f"  v{active_v}"
            else:
                ver_tag = ""
            # 精简卡片：Ep号 + 阶段\n标题 + 版本
            label = f"{nid}  {stage}\n{title[:12]}{ver_tag}"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, nid)
            item.setSizeHint(QSize(190, 62))
            item.setToolTip(
                f"节点: {nid}\n阶段: {stage}\n标题: {title}\n"
                f"版本: v{node.get('active_version', 0)}\n"
                f"钩子: {node.get('episode_hook','')}"
            )
            sid = node.get("hauge_stage_id", 1)
            colors = {1:"#dfe6e9", 2:"#ffeaa7", 3:"#fab1a0", 4:"#ff7675", 5:"#fd79a8", 6:"#a29bfe"}
            item.setBackground(QColor(colors.get(sid, "#ffffff")))
            self._node_list.addItem(item)

    @staticmethod
    def _parse_ep_num(ep_id: str) -> tuple:
        """Ep3.1.2 → (3, 1, 2) 用于层级排序"""
        import re
        nums = re.findall(r'\d+', ep_id or '')
        return tuple(int(n) for n in nums) if nums else (0,)

    # Keep backward compat alias
    @staticmethod
    def _parse_node_num(ep_id: str) -> tuple:
        import re
        nums = re.findall(r'\d+', ep_id or '')
        return tuple(int(n) for n in nums) if nums else (0,)

    def _on_card_double_clicked(self, item: QListWidgetItem):
        """双击卡片弹出节点详情对话框"""
        node_id = item.data(Qt.UserRole)
        node = next((n for n in self.project_data.cpg_nodes if n.get("node_id") == node_id), None)
        if not node:
            return
        from ui.widgets.node_detail_dialog import NodeDetailDialog as _NewDlg
        dlg = _NewDlg(node, self.project_data, parent=self)
        result = dlg.exec()
        if result == QDialog.Accepted:
            action = dlg.action or ""
            if action in ("saved", "split", "merge"):
                self._load_to_editor()
                self.status_message.emit(f"节点 {node_id} 已更新 ({action})")
                if action in ("split", "merge"):
                    QMessageBox.warning(
                        self, "结构已变更",
                        f"骨架结构已发生变更（{action}）。\n\n"
                        "⚠️ 请注意：\n"
                        "• 血肉阶段需要为新节点重新生成 Beat\n"
                        "• 扩写阶段需要重新扩写受影响的章节\n\n"
                        "请依次进入血肉、扩写阶段完成更新。"
                    )
            elif action == "deleted":
                nid = node.get("node_id", node_id)
                self.project_data.cpg_nodes = [
                    n for n in self.project_data.cpg_nodes if n.get("node_id") != nid
                ]
                self.project_data.cpg_edges = [
                    e for e in self.project_data.cpg_edges
                    if e.get("from_node") != nid and e.get("to_node") != nid
                ]
                self._load_to_editor()
                self.status_message.emit(f"节点 {nid} 已删除")
                QMessageBox.warning(
                    self, "结构已变更",
                    f"节点 {nid} 已删除。\n\n"
                    "⚠️ 请注意：\n"
                    "• 血肉阶段需要重新进行以同步最新结构\n"
                    "• 扩写阶段需要重新扩写以反映变更\n\n"
                    "请依次进入血肉、扩写阶段完成更新。"
                )
            elif action and action.startswith("id_changed:"):
                new_id = action.split(":", 1)[1]
                self._load_to_editor()
                self.status_message.emit(f"节点编号已更改为 {new_id}")
                app_logger.info("骨架-节点编辑", f"节点编号从 {node_id} 变更为 {new_id}")

            if action:
                app_logger.info("骨架-节点编辑", f"完成对节点 {node_id} 的操作：{action}")


    # ------------------------------------------------------------------ #
    # Loading 遮罩
    # ------------------------------------------------------------------ #
    def _show_loading(self):
        parent = self._loading_overlay.parent()
        if parent:
            self._loading_overlay.setGeometry(parent.rect())
        self._loading_overlay.start()

    def _hide_loading(self):
        self._loading_overlay.stop()

    def resizeEvent(self, event):
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

        from env import DRAMA_STYLE_CONFIG
        from services.genre_manager import genre_manager
        style_key = self.project_data.drama_style or "short_drama"
        style_cfg = DRAMA_STYLE_CONFIG.get(style_key, {})

        genre_key = getattr(self.project_data, 'story_genre', 'custom')
        genre_cfg = genre_manager.get(genre_key)
        # 合并 drama_style + genre 的 skeleton block
        combined_block = style_cfg.get("skeleton_style_block", "")
        genre_skel = genre_cfg.get("skeleton_block", "")
        if genre_skel:
            combined_block = (combined_block + "\n\n" + genre_skel).strip()

        self._worker = CPGSkeletonWorker(
            sparkle=self.project_data.sparkle,
            world_variables=self.project_data.world_variables,
            finale_condition=self.project_data.finale_condition,
            ai_params=self._ai_settings.get_all_settings(),
            characters=self.project_data.characters,
            total_episodes=self._episodes_spin.value(),
            episode_duration=self._duration_range.durationString(),
            drama_style_block=combined_block,
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

        # 为每个新生成的节点创建 v0 版本快照
        from models.project_state import add_version as _add_version
        for node in nodes:
            _add_version(node, "ai_generate", "初始生成")

        self.project_data.cpg_title  = result.get("cpg_title", "")
        self.project_data.cpg_nodes  = nodes
        self.project_data.cpg_edges  = result.get("causal_edges", [])
        self.project_data.hauge_stages = result.get("hauge_stages", [])
        self.project_data.push_history("generate_skeleton")
        self._load_to_editor()
        self.status_message.emit(
            f"CPG 骨架完成: {len(nodes)} 集/节点, {len(self.project_data.cpg_edges)} 条边"
        )

    # ------------------------------------------------------------------ #
    # 进入 Phase 3
    # ------------------------------------------------------------------ #
    def _on_proceed(self):
        if not self.project_data.cpg_nodes:
            QMessageBox.warning(self, "提示", "请先生成 CPG 骨架！")
            return

        # ---- 编号冲突检测 ----
        all_ids = [n.get("node_id", "") for n in self.project_data.cpg_nodes]
        seen = set()
        duplicates = set()
        for nid in all_ids:
            if nid in seen:
                duplicates.add(nid)
            seen.add(nid)
        if duplicates:
            dup_list = ", ".join(sorted(duplicates))
            QMessageBox.warning(
                self, "编号冲突",
                f"以下节点编号存在重复：{dup_list}\n\n"
                f"请先修改重复的编号，确保每个节点编号唯一后再进入下一阶段。",
            )
            return

        for node in self.project_data.cpg_nodes:
            nid = node.get("node_id", "")
            if nid and nid not in self.project_data.confirmed_beats:
                self.project_data.confirmed_beats[nid] = None
        self.project_data.current_phase       = "flesh"
        self.project_data.current_node_index  = 0
        self.project_data.push_history("enter_flesh")
        app_logger.success(
            "骨架-确认",
            f"骨架已确认，进入血肉阶段",
            f"共包含 {len(self.project_data.cpg_nodes)} 个节点，{len(self.project_data.cpg_edges)} 条关系边",
        )
        self.phase_completed.emit()

    # ------------------------------------------------------------------ #
    # 工具
    # ------------------------------------------------------------------ #
    def _set_busy(self, busy: bool):
        self._btn_regen.setEnabled(not busy)
        self._btn_next.setEnabled(not busy)
        self._btn_back.setEnabled(not busy)
        self._episodes_spin.setEnabled(not busy)
        self._duration_range.setEnabled(not busy)
        self._btn_regen.setText("处理中..." if busy else "重新生成骨架")

    def _on_error(self, msg: str):
        self._set_busy(False)
        self._hide_loading()
        QMessageBox.critical(self, "AI 调用失败", msg)
        self.status_message.emit("错误: " + msg)

