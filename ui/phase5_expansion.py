# ============================================================
# ui/phase5_expansion.py
# Phase 5: 剧本扩写 — 将每个已确认Beat扩写为标准短剧剧本格式
# ============================================================

import json
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QSplitter, QComboBox, QTextEdit,
    QGroupBox, QMessageBox, QFileDialog, QSlider,
)
from PySide6.QtCore import Qt, Signal

from env import (
    SYSTEM_PROMPT_EXPANSION, USER_PROMPT_EXPANSION,
    TEMPERATURE_EXPANSION,
)
from services.worker import ExpansionWorker
from services.logger_service import app_logger
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
        self._title_label.setStyleSheet(" font-weight: bold;")
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
        self._progress_label.setStyleSheet(" color: #555;")
        root.addWidget(self._progress_label)

        # 主内容：左右分割
        h_splitter = QSplitter(Qt.Horizontal)

        # 左侧：Beat 摘要（只读参考）
        from PySide6.QtWidgets import QScrollArea
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        left_scroll.setMinimumWidth(500)
        left_scroll.setStyleSheet("QScrollArea{border:none;}")
        left_inner = QWidget()
        ll = QVBoxLayout(left_inner)
        ll.setContentsMargins(0, 0, 4, 0)
        ll.setSpacing(4)

        beat_label = QLabel("📋 Beat 摘要（参考）")
        beat_label.setStyleSheet("font-weight: bold;")
        ll.addWidget(beat_label)

        self._beat_summary = QTextEdit()
        self._beat_summary.setReadOnly(True)
        self._beat_summary.setStyleSheet(
            "QTextEdit {"
            "  background:#f8f9fa; border:1px solid #dcdde1;"
            "  border-radius:6px; padding:8px;"
            "}"
        )
        ll.addWidget(self._beat_summary, 1)

        # 角色摘要
        char_label = QLabel("👤 角色性格参考")
        char_label.setStyleSheet("font-weight: bold; margin-top:6px;")
        ll.addWidget(char_label)

        self._char_summary = QTextEdit()
        self._char_summary.setReadOnly(True)
        self._char_summary.setMaximumHeight(100)
        self._char_summary.setStyleSheet(
            "QTextEdit {"
            "  background:#fdf6e3; border:1px solid #f0d9a0;"
            "  border-radius:6px; padding:8px;"
            "}"
        )
        ll.addWidget(self._char_summary)

        # --- 扩写参数：叙事风格 + 场景数 + 台词上限 ---
        style_group = QGroupBox("扩写参数")
        sg_layout = QVBoxLayout(style_group)
        sg_layout.setSpacing(6)

        # 每集时长区间
        from ui.widgets.range_slider import DurationRangeWidget
        dur_row = QHBoxLayout()
        self._duration_range = DurationRangeWidget(
            min_val=0.5, max_val=30.0,
            low=self.project_data.episode_duration_min,
            high=self.project_data.episode_duration_max,
        )
        self._duration_range.rangeChanged.connect(self._on_duration_changed)
        dur_row.addWidget(self._duration_range)
        dur_row.addWidget(QLabel("  ≈ 每集"))
        self._word_count_label = QLabel("")
        self._word_count_label.setStyleSheet("color: #2980b9; font-weight: bold;")
        dur_row.addWidget(self._word_count_label)
        dur_row.addStretch()
        sg_layout.addLayout(dur_row)
        self._update_word_count_hint()

        # 叙事风格 + 场景数
        style_row = QHBoxLayout()
        style_row.addWidget(QLabel("叙事风格:"))
        from env import DRAMA_STYLE_CONFIG
        self._style_combo = QComboBox()
        for key, cfg in DRAMA_STYLE_CONFIG.items():
            self._style_combo.addItem(cfg["label"], key)
        current_style = self.project_data.drama_style or "short_drama"
        for i in range(self._style_combo.count()):
            if self._style_combo.itemData(i) == current_style:
                self._style_combo.setCurrentIndex(i)
                break
        self._style_combo.currentIndexChanged.connect(self._on_style_changed)
        self._style_combo.setMinimumWidth(180)
        style_row.addWidget(self._style_combo)

        style_row.addWidget(QLabel("  单集最多场景:"))
        self._scenes_slider = QSlider(Qt.Horizontal)
        self._scenes_slider.setRange(1, 8)
        self._scenes_slider.setValue(self.project_data.max_scenes_per_episode)
        self._scenes_slider.setTickPosition(QSlider.TicksBelow)
        self._scenes_slider.setTickInterval(1)
        self._scenes_slider.setFixedWidth(100)
        self._scenes_slider.valueChanged.connect(self._on_scenes_slider_changed)
        style_row.addWidget(self._scenes_slider)
        self._scenes_label = QLabel(f"\u2264{self.project_data.max_scenes_per_episode} \u4e2a")
        self._scenes_label.setStyleSheet("color: #e67e22; font-weight: bold; min-width: 40px;")
        style_row.addWidget(self._scenes_label)
        style_row.addStretch()
        sg_layout.addLayout(style_row)

        # 第二行：风格说明
        self._style_desc = QLabel("")
        self._style_desc.setStyleSheet("color: #7f8c8d;")
        self._style_desc.setWordWrap(True)
        self._update_style_desc()
        sg_layout.addWidget(self._style_desc)

        # 第三行：台词字数上限
        dialogue_row = QHBoxLayout()
        dialogue_row.addWidget(QLabel("单句台词上限:"))
        self._dialogue_slider = QSlider(Qt.Horizontal)
        self._dialogue_slider.setRange(20, 120)
        self._dialogue_slider.setValue(self.project_data.max_dialogue_chars)
        self._dialogue_slider.setTickPosition(QSlider.TicksBelow)
        self._dialogue_slider.setTickInterval(10)
        self._dialogue_slider.setFixedWidth(150)
        self._dialogue_slider.valueChanged.connect(self._on_dialogue_slider_changed)
        dialogue_row.addWidget(self._dialogue_slider)
        self._dialogue_label = QLabel(f"\u2264{self.project_data.max_dialogue_chars} \u5b57")
        self._dialogue_label.setStyleSheet("color: #8e44ad; font-weight: bold; min-width: 50px;")
        dialogue_row.addWidget(self._dialogue_label)
        self._dialogue_hint = QLabel("\uff08\u4e2d\u6587\u5b57\u7b26\uff0c\u8d85\u8fc7\u5219\u5efa\u8bae\u62c6\u5206\u53f0\u8bcd\uff09")
        self._dialogue_hint.setStyleSheet("color: #95a5a6;")
        dialogue_row.addWidget(self._dialogue_hint)
        dialogue_row.addStretch()
        sg_layout.addLayout(dialogue_row)

        ll.addWidget(style_group)

        # --- 爽感 & 钩子公式选择 (tag 样式) ---
        from config.prompt_templates import prompt_template_manager
        formula_group = QGroupBox("爽感 & 钩子公式选择（点击 + 添加，注入到 Prompt）")
        fg_layout = QVBoxLayout(formula_group)
        fg_layout.setSpacing(4)

        # 爽感行
        sat_row = QHBoxLayout()
        sat_label = QLabel("<b>⚡ 爽感:</b>")
        sat_label.setAlignment(Qt.AlignTop)
        sat_row.addWidget(sat_label)
        self._exp_sat_tag_container = QWidget()
        self._exp_sat_tag_flow = QVBoxLayout(self._exp_sat_tag_container)
        self._exp_sat_tag_flow.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self._exp_sat_tag_flow.setContentsMargins(0, 0, 0, 0)
        self._exp_sat_tag_flow.setSpacing(4)
        sat_row.addWidget(self._exp_sat_tag_container, 1)
        btn_add_sat = QPushButton("+")
        btn_add_sat.setFixedSize(28, 24)
        btn_add_sat.setToolTip("添加爽感公式")
        btn_add_sat.setStyleSheet(
            "QPushButton{color:#e67e22;background:#fef5e7;font-weight:bold;"
            "border:1px solid #bdc3c7;border-radius:3px;padding:0;}"
            "QPushButton:hover{background:#fdebd0;}"
        )
        btn_add_sat.clicked.connect(self._add_exp_sat_tag)
        sat_row.addWidget(btn_add_sat, alignment=Qt.AlignTop)
        fg_layout.addLayout(sat_row)

        # 钩子行
        hook_row = QHBoxLayout()
        hook_label = QLabel("<b>🪝 钩子:</b>")
        hook_label.setAlignment(Qt.AlignTop)
        hook_row.addWidget(hook_label)
        self._exp_hook_tag_container = QWidget()
        self._exp_hook_tag_flow = QVBoxLayout(self._exp_hook_tag_container)
        self._exp_hook_tag_flow.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self._exp_hook_tag_flow.setContentsMargins(0, 0, 0, 0)
        self._exp_hook_tag_flow.setSpacing(4)
        hook_row.addWidget(self._exp_hook_tag_container, 1)
        btn_add_hook = QPushButton("+")
        btn_add_hook.setFixedSize(28, 24)
        btn_add_hook.setToolTip("添加钩子公式")
        btn_add_hook.setStyleSheet(
            "QPushButton{color:#8e44ad;background:#f5eef8;font-weight:bold;"
            "border:1px solid #bdc3c7;border-radius:3px;padding:0;}"
            "QPushButton:hover{background:#ebdef0;}"
        )
        btn_add_hook.clicked.connect(self._add_exp_hook_tag)
        hook_row.addWidget(btn_add_hook, alignment=Qt.AlignTop)
        fg_layout.addLayout(hook_row)

        # 已选公式 ID 集合（用 enabled 状态初始化）
        self._exp_sat_selected_ids = {s.id for s in prompt_template_manager.get_satisfactions() if s.enabled}
        self._exp_hook_selected_ids = {h.id for h in prompt_template_manager.get_hooks() if h.enabled}
        self._refresh_exp_formula_tags()

        # 爽感节奏参数
        from ui.widgets.int_spinbox import IntSpinBox
        interval_row = QHBoxLayout()
        interval_row.addWidget(QLabel("小爽每"))
        self._sat_small_spin = IntSpinBox()
        self._sat_small_spin.setRange(1, 5)
        self._sat_small_spin.setValue(self.project_data.sat_small_interval)
        self._sat_small_spin.setSuffix("集")
        self._sat_small_spin.setMinimumWidth(100)
        self._sat_small_spin.setFixedHeight(32)
        self._sat_small_spin.valueChanged.connect(self._on_sat_interval_changed)
        interval_row.addWidget(self._sat_small_spin)

        interval_row.addWidget(QLabel(" 中爽每"))
        self._sat_medium_spin = IntSpinBox()
        self._sat_medium_spin.setRange(1, 20)
        self._sat_medium_spin.setValue(self.project_data.sat_medium_interval)
        self._sat_medium_spin.setSuffix("集")
        self._sat_medium_spin.setMinimumWidth(100)
        self._sat_medium_spin.setFixedHeight(32)
        self._sat_medium_spin.valueChanged.connect(self._on_sat_interval_changed)
        interval_row.addWidget(self._sat_medium_spin)

        interval_row.addWidget(QLabel(" 大爽每"))
        self._sat_big_spin = IntSpinBox()
        self._sat_big_spin.setRange(1, 50)
        self._sat_big_spin.setValue(self.project_data.sat_big_interval)
        self._sat_big_spin.setSuffix("集")
        self._sat_big_spin.setMinimumWidth(100)
        self._sat_big_spin.setFixedHeight(32)
        self._sat_big_spin.valueChanged.connect(self._on_sat_interval_changed)
        interval_row.addWidget(self._sat_big_spin)
        
        interval_row.addStretch()
        fg_layout.addLayout(interval_row)

        # 当前集爽感等级提示
        self._sat_level_hint = QLabel("")
        self._sat_level_hint.setStyleSheet("color:#e67e22;font-weight:bold;")
        fg_layout.addWidget(self._sat_level_hint)

        tip = QLabel("ℹ️ 未勾选任何公式时，系统会自动随机抽取对应等级的启用公式")
        tip.setStyleSheet("color:#95a5a6;")
        fg_layout.addWidget(tip)

        ll.addWidget(formula_group)

        # prompt预览将在 tag 操作时自动触发

        # AI参数
        self._ai_settings = AISettingsPanel(suggested_temp=TEMPERATURE_EXPANSION)
        ll.addWidget(self._ai_settings)

        self._prompt_viewer = PromptViewer()
        ll.addWidget(self._prompt_viewer)
        self._update_prompt_preview()

        left_scroll.setWidget(left_inner)
        h_splitter.addWidget(left_scroll)

        # 右侧：剧本编辑器
        self._screenplay_editor = ScreenplayEditor(target_min=600, target_max=800)
        self._screenplay_editor.text_changed.connect(self._on_screenplay_text_changed)
        h_splitter.addWidget(self._screenplay_editor)

        h_splitter.setSizes([500, 460])
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
        from ui.widgets.int_spinbox import IntSpinBox
        self._regen_spin = IntSpinBox()
        self._regen_spin.setRange(1, 20)
        self._regen_spin.setValue(1)
        self._regen_spin.setSuffix(" 章")
        self._regen_spin.setMinimumWidth(100)
        self._regen_spin.setFixedHeight(36)
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

        self._btn_clear_all = QPushButton("🗑️ 一键清除扩写内容")
        self._btn_clear_all.setStyleSheet(
            "QPushButton{background:#e74c3c;color:white;border:none;"
            "border-radius:4px;padding:6px 14px;}"
            "QPushButton:hover{background:#c0392b;}"
        )
        self._btn_clear_all.clicked.connect(self._on_clear_all_expansions)
        btn_row2.addWidget(self._btn_clear_all)

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
        """进入扩写阶段时刷新节点列表，同步扩写参数控件"""
        # 同步扩写参数控件
        current_style = self.project_data.drama_style or "short_drama"
        for i in range(self._style_combo.count()):
            if self._style_combo.itemData(i) == current_style:
                self._style_combo.setCurrentIndex(i)
                break
        self._update_style_desc()
        self._scenes_slider.setValue(self.project_data.max_scenes_per_episode)
        self._scenes_label.setText(f"\u2264{self.project_data.max_scenes_per_episode} \u4e2a")
        self._dialogue_slider.setValue(self.project_data.max_dialogue_chars)
        self._dialogue_label.setText(f"\u2264{self.project_data.max_dialogue_chars} \u5b57")
        # 同步爽感节奏参数
        self._sat_small_spin.setValue(self.project_data.sat_small_interval)
        self._sat_medium_spin.setValue(self.project_data.sat_medium_interval)
        self._sat_big_spin.setValue(self.project_data.sat_big_interval)
        self._update_sat_level_hint()

        # 同步时长区间控件 + 自动计算目标字数
        self._duration_range.setValues(
            self.project_data.episode_duration_min,
            self.project_data.episode_duration_max,
        )
        self._update_word_count_hint()
        dur_min = self.project_data.episode_duration_min
        dur_max = self.project_data.episode_duration_max
        target_min = int(dur_min * 180)
        target_max = int(dur_max * 180)
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
    # 扩写参数变更
    # ------------------------------------------------------------------ #
    def _on_style_changed(self):
        from env import DRAMA_STYLE_CONFIG
        style_key = self._style_combo.currentData() or "short_drama"
        self.project_data.drama_style = style_key
        cfg = DRAMA_STYLE_CONFIG.get(style_key, {})
        scenes_str = cfg.get("default_scenes_per_episode", "1-2")
        try:
            max_sc = int(scenes_str.split("-")[-1])
        except (ValueError, IndexError):
            max_sc = 3
        self._scenes_slider.setValue(max_sc)
        self._update_style_desc()
        self._sync_expansion_params()

    def _update_style_desc(self):
        from env import DRAMA_STYLE_CONFIG
        style_key = self._style_combo.currentData() or "short_drama"
        cfg = DRAMA_STYLE_CONFIG.get(style_key, {})
        self._style_desc.setText(cfg.get("description", ""))

    def _on_scenes_slider_changed(self, val):
        self._scenes_label.setText(f"\u2264{val} \u4e2a")
        self._sync_expansion_params()

    def _on_dialogue_slider_changed(self, val):
        self._dialogue_label.setText(f"\u2264{val} \u5b57")
        self._sync_expansion_params()

    def _on_sat_interval_changed(self, *_args):
        self.project_data.sat_small_interval = self._sat_small_spin.value()
        self.project_data.sat_medium_interval = self._sat_medium_spin.value()
        self.project_data.sat_big_interval = self._sat_big_spin.value()
        self._update_sat_level_hint()

    def _update_sat_level_hint(self):
        """\u6839\u636e\u5f53\u524d\u8282\u70b9\u96c6\u53f7\u663e\u793a\u723d\u611f\u7b49\u7ea7"""
        nid = self._node_combo.currentData() or ""
        ep_num = self._extract_episode_number(nid) if nid else 1
        from config.prompt_templates import prompt_template_manager
        level = prompt_template_manager.determine_satisfaction_level(
            ep_num,
            self._sat_small_spin.value(),
            self._sat_medium_spin.value(),
            self._sat_big_spin.value(),
        )
        level_cn = {"small": "\u5c0f\u723d\u70b9", "medium": "\u4e2d\u723d\u70b9", "big": "\u5927\u723d\u70b9"}.get(level, level)
        level_emoji = {"small": "\u2728", "medium": "\u2b50", "big": "\ud83d\udca5"}.get(level, "")
        self._sat_level_hint.setText(f"{level_emoji} \u5f53\u524d\u8282\u70b9(Ep{ep_num})\u9700\u8981\uff1a\u300c{level_cn}\u300d")

    def _on_duration_changed(self, *_args):
        dur_min = self._duration_range.low()
        dur_max = self._duration_range.high()
        self.project_data.episode_duration_min = dur_min
        self.project_data.episode_duration_max = dur_max
        self.project_data.episode_duration = int((dur_min + dur_max) / 2)
        self._update_word_count_hint()
        # 同步目标字数到编辑器
        target_min = int(dur_min * 180)
        target_max = int(dur_max * 180)
        self._screenplay_editor.set_target_range(target_min, target_max)

    def _update_word_count_hint(self):
        dur_min = self._duration_range.low()
        dur_max = self._duration_range.high()
        words_min = int(dur_min * 180)
        words_max = int(dur_max * 180)
        self._word_count_label.setText(f"{words_min}-{words_max} 字")

    def _sync_expansion_params(self):
        """将扩写参数控件值同步到 project_data"""
        self.project_data.max_scenes_per_episode = self._scenes_slider.value()
        self.project_data.scenes_per_episode = f"1-{self._scenes_slider.value()}"
        self.project_data.max_dialogue_chars = self._dialogue_slider.value()
    # ------------------------------------------------------------------ #
    # 爽感 & 钩子公式 tag 管理 (扩写阶段)
    # ------------------------------------------------------------------ #
    def _refresh_exp_formula_tags(self):
        """刷新爽感/钩子 tag 显示"""
        from config.prompt_templates import prompt_template_manager
        # 清空爽感行
        while self._exp_sat_tag_flow.count():
            item = self._exp_sat_tag_flow.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        # 清空钩子行
        while self._exp_hook_tag_flow.count():
            item = self._exp_hook_tag_flow.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # 重建爽感 tags
        sat_map = {s.id: s for s in prompt_template_manager.get_satisfactions()}
        for sid in sorted(self._exp_sat_selected_ids):
            s = sat_map.get(sid)
            if s:
                level_cn = {"small": "小爽", "medium": "中爽", "big": "大爽"}.get(s.level, s.level)
                self._exp_sat_tag_flow.addWidget(
                    self._make_exp_formula_tag(f"{s.name}（{level_cn}）", sid, "sat")
                )
        self._exp_sat_tag_flow.addStretch()

        # 重建钩子 tags
        hook_map = {h.id: h for h in prompt_template_manager.get_hooks()}
        for hid in sorted(self._exp_hook_selected_ids):
            h = hook_map.get(hid)
            if h:
                self._exp_hook_tag_flow.addWidget(
                    self._make_exp_formula_tag(h.name, hid, "hook")
                )
        self._exp_hook_tag_flow.addStretch()

        # 刷新 prompt 预览
        if hasattr(self, '_prompt_viewer'):
            self._update_prompt_preview()

    def _make_exp_formula_tag(self, label: str, template_id: str, category: str):
        """创建一个公式 tag 控件"""
        tag = QWidget()
        tag.setFixedHeight(24)
        h = QHBoxLayout(tag)
        h.setContentsMargins(6, 0, 2, 0)
        h.setSpacing(2)
        lbl = QLabel(label)
        lbl.setStyleSheet("color:#2c3e50;")
        h.addWidget(lbl)
        btn_x = QPushButton("x")
        btn_x.setFixedSize(16, 16)
        btn_x.setStyleSheet(
            "QPushButton{border:none;color:#e74c3c;font-weight:bold;padding:0;}"
            "QPushButton:hover{color:#c0392b;background:#fadbd8;border-radius:8px;}"
        )
        btn_x.setCursor(Qt.PointingHandCursor)
        if category == "sat":
            btn_x.clicked.connect(lambda _, tid=template_id: self._remove_exp_sat_tag(tid))
        else:
            btn_x.clicked.connect(lambda _, tid=template_id: self._remove_exp_hook_tag(tid))
        h.addWidget(btn_x)
        color = "#fef5e7" if category == "sat" else "#f5eef8"
        border_color = "#e67e22" if category == "sat" else "#8e44ad"
        tag.setObjectName("formulaTag")
        tag.setStyleSheet(
            f"#formulaTag{{background:{color};border:1px solid {border_color};"
            f"border-radius:10px;}}"
        )
        return tag

    def _remove_exp_sat_tag(self, template_id: str):
        self._exp_sat_selected_ids.discard(template_id)
        self._refresh_exp_formula_tags()

    def _remove_exp_hook_tag(self, template_id: str):
        self._exp_hook_selected_ids.discard(template_id)
        self._refresh_exp_formula_tags()

    def _add_exp_sat_tag(self):
        from config.prompt_templates import prompt_template_manager
        from ui.widgets.formula_picker_dialog import FormulaPickerDialog
        dlg = FormulaPickerDialog(
            title="选择爽感公式",
            templates=prompt_template_manager.get_satisfactions(),
            already_selected_ids=self._exp_sat_selected_ids,
            parent=self,
        )
        if dlg.exec() == FormulaPickerDialog.Accepted:
            chosen = dlg.get_chosen_id()
            if chosen:
                self._exp_sat_selected_ids.add(chosen)
                self._refresh_exp_formula_tags()

    def _add_exp_hook_tag(self):
        from config.prompt_templates import prompt_template_manager
        from ui.widgets.formula_picker_dialog import FormulaPickerDialog
        dlg = FormulaPickerDialog(
            title="选择钩子公式",
            templates=prompt_template_manager.get_hooks(),
            already_selected_ids=self._exp_hook_selected_ids,
            parent=self,
        )
        if dlg.exec() == FormulaPickerDialog.Accepted:
            chosen = dlg.get_chosen_id()
            if chosen:
                self._exp_hook_selected_ids.add(chosen)
                self._refresh_exp_formula_tags()

    def _update_prompt_preview(self):
        """根据当前勾选状态更新 PromptViewer 显示的完整 system prompt"""
        sat_prompt, hook_prompt = self._get_selected_formula_injections()
        full_system = SYSTEM_PROMPT_EXPANSION
        if sat_prompt:
            full_system += "\n\n" + sat_prompt
        elif not sat_prompt:
            full_system += "\n\n[系统将自动随机抽取爽感公式注入]"
        if hook_prompt:
            full_system += "\n\n" + hook_prompt
        elif not hook_prompt:
            full_system += "\n\n[系统将自动随机抽取钩子公式注入]"
        self._prompt_viewer.set_prompt(full_system, USER_PROMPT_EXPANSION)

    def _get_selected_formula_injections(self, episode_number: int = 1):
        """根据用户勾选+集号调度生成注入文本"""
        from config.prompt_templates import prompt_template_manager

        # 确定本集需要的爽感等级
        required_level = prompt_template_manager.determine_satisfaction_level(
            episode_number,
            self.project_data.sat_small_interval,
            self.project_data.sat_medium_interval,
            self.project_data.sat_big_interval,
        )

        # 爽感公式：按等级和选中状态生成
        sat_ids = list(self._exp_sat_selected_ids)
        sat_prompt = prompt_template_manager.build_satisfaction_prompt_for_episode(
            episode_number=episode_number,
            required_level=required_level,
            selected_ids=sat_ids if sat_ids else None,
        )

        # 钩子公式：按选中状态
        hook_ids = list(self._exp_hook_selected_ids)
        hook_prompt = prompt_template_manager.build_hook_prompt_by_ids(hook_ids) if hook_ids else ""
        return sat_prompt, hook_prompt

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
            app_logger.info("扩写-保存", f"节点 {self._current_node_id} 保存用户编辑的内容")

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
        app_logger.info("扩写-重新生成", f"从节点 {first_nid} 起重新生成 {count} 个节点的扩写内容")
        for i in range(self._node_combo.count()):
            if self._node_combo.itemData(i) == first_nid:
                self._node_combo.setCurrentIndex(i)
                break
        self._expand_node(first_nid)

    def _on_clear_all_expansions(self):
        reply = QMessageBox.warning(
            self, "确认清除",
            "这将会清除所有已扩写的剧本内容（仅正文，不影响 Beat 和骨架）。\n"
            "此操作不可撤销，确定吗？",
            QMessageBox.Yes | QMessageBox.No,
            defaultButton=QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.project_data.screenplay_texts.clear()
            self.project_data.push_history("clear_expansions")
            self._refresh_node_combo()
            if self._current_node_id:
                self._screenplay_editor.set_text("")
            self.status_message.emit("🧹 已清除所有扩写内容，请记得按 Ctrl+S 保存项目")
            app_logger.info("扩写-清除", "用户清除了所有扩写的剧本内容")

    def _expand_node(self, node_id: str):
        node = next((n for n in self.project_data.cpg_nodes
                     if n.get("node_id") == node_id), None)
        beat = self.project_data.confirmed_beats.get(node_id, {}) or {}

        if not beat:
            QMessageBox.warning(self, "提示", f"节点 {node_id} 尚未确认 Beat，无法扩写。")
            return

        # 组装角色摘要（含完整信息：重要性、性别、年龄、身份、性格、动机）
        chars_summary = "\n".join(
            f"[{c.get('importance_level','C')}] {c.get('name', '')}（{c.get('gender', '未知')}，{c.get('age', '未知')}岁，{c.get('position', '')}）：{c.get('personality', '')}；动机：{c.get('motivation', '')}"
            for c in self.project_data.characters
        ) or "（未设定角色）"

        # 拼接角色关系（确保 AI 知道角色间的具体关系，避免称呼/辈分矛盾）
        if self.project_data.character_relations:
            char_name_map = {c.get("char_id", ""): c.get("name", "") for c in self.project_data.characters}
            rel_lines = []
            for rel in self.project_data.character_relations:
                from_name = char_name_map.get(rel.get("from_char_id", ""), rel.get("from_char_id", ""))
                to_name = char_name_map.get(rel.get("to_char_id", ""), rel.get("to_char_id", ""))
                rel_type = rel.get("relation_type", "")
                rel_desc = rel.get("description", "")
                line = f"  {from_name} → {to_name}：{rel_type}"
                if rel_desc:
                    line += f"（{rel_desc}）"
                rel_lines.append(line)
            chars_summary += "\n\n【角色关系（对白中的称呼必须与此一致）】\n" + "\n".join(rel_lines)

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

        # 注入台词字数限制规则
        max_dc = self.project_data.max_dialogue_chars
        dialogue_rule = (
            f"\n## 台词字数限制（严格遵守！）\n"
            f"- 单句中文台词不得超过 {max_dc} 个字符\n"
            f"- 如果角色需要表达大量信息，必须拆分台词：插入一个动作描写或镜头切换，"
            f"或让其他角色插一句话打断，避免长篇独白\n"
        )
        expansion_block += dialogue_rule

        # 动态上下文指令：基于当前集号和已生成内容，程序化注入逐集指令
        dynamic_instructions = self._build_dynamic_context_instructions(
            node_id, episode_number, beat, node
        )
        if dynamic_instructions:
            expansion_block += "\n" + dynamic_instructions

        # 构建时长字符串
        dur_min = self.project_data.episode_duration_min
        dur_max = self.project_data.episode_duration_max
        dur_min_s = f"{dur_min:.1f}" if dur_min != int(dur_min) else str(int(dur_min))
        dur_max_s = f"{dur_max:.1f}" if dur_max != int(dur_max) else str(int(dur_max))
        episode_duration_str = f"{dur_min_s}到{dur_max_s}"

        # 获取用户勾选的公式注入
        sat_injection, hook_injection = self._get_selected_formula_injections(episode_number)

        # 世界观变量 JSON（注入扩写 Prompt，确保 AI 不违反设定）
        world_vars_json = json.dumps(
            self.project_data.world_variables, ensure_ascii=False, indent=2
        ) if self.project_data.world_variables else "（未设定世界观变量）"

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
            episode_duration=episode_duration_str,
            scenes_per_episode=self.project_data.scenes_per_episode or "1-2",
            drama_style_block=expansion_block,
            satisfaction_prompt_injection=sat_injection,
            hook_prompt_injection=hook_injection,
            world_variables_json=world_vars_json,
            opening_hook=node.get("opening_hook", ""),
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

        # 后处理：过滤元创作语言泄露
        text = self._postprocess_screenplay(text)

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
        app_logger.info("扩写-批量重写", f"重置并开始全部重写 {len(target)} 个节点的剧本扩写")

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
        try:
            # 去重：防止骨架中出现重复 node_id 导致重复导出
            exported_nids = set()
            for node in all_sorted:
                nid = node.get("node_id", "")
                if nid in exported_nids:
                    continue  # 跳过重复 node_id
                exported_nids.add(nid)
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
            with open(filepath, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            QMessageBox.information(self, "导出成功", f"剧本已保存到：\n{filepath}")
            self.status_message.emit(f"✅ 剧本已导出: {filepath}")
            app_logger.success("扩写-导出", f"导出全部剧本至：{filepath}")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", str(e))
            app_logger.error("扩写-导出", f"导出失败: {str(e)}")

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
        app_logger.success("扩写-确认", "扩写阶段完成，进入锁定阶段", f"已完成 {written}/{total} 个节点的扩写")
        self.phase_completed.emit()

    # ------------------------------------------------------------------ #
    # 动态上下文指令生成（逐集感知）
    # ------------------------------------------------------------------ #
    def _build_dynamic_context_instructions(self, node_id: str, episode_number: int,
                                             beat: dict, node: dict) -> str:
        """
        根据当前集的位置、Beat 内容、已生成剧本，
        动态生成只对本集有效的扩写指令。
        """
        import re
        from collections import Counter
        instructions = []
        total_eps = self.project_data.total_episodes or 20

        # --- 1. 集位置感知 ---
        progress_pct = round(episode_number / total_eps * 100)
        stage_name = node.get("hauge_stage_name", "")
        instructions.append(
            f"## 当前进度\n"
            f"- 你正在写第 {episode_number} 集（共 {total_eps} 集，进度 {progress_pct}%）\n"
            f"- 当前 Hauge 阶段：{stage_name}"
        )

        # --- 2. 金手指/关键能力首次出现检测 ---
        # 从世界观变量中提取"道具能力"类的变量名
        ability_vars = [
            v for v in self.project_data.world_variables
            if v.get("category") in ("道具能力", "关键道具/能力")
        ]
        if ability_vars:
            current_entities = set(beat.get("entities", []))
            # 扫描之前所有已确认 Beat 的 entities
            previous_entities = set()
            for prev_nid, prev_beat in self.project_data.confirmed_beats.items():
                if prev_nid == node_id or not prev_beat:
                    continue
                prev_ep = self._extract_episode_number(prev_nid)
                if prev_ep < episode_number:
                    previous_entities.update(prev_beat.get("entities", []))
            # 本集新出现的实体
            new_entities = current_entities - previous_entities
            # 检查新实体是否匹配任何道具能力变量
            for var in ability_vars:
                var_name = var.get("name", "")
                var_def = var.get("definition", "")
                var_constraints = var.get("constraints", "")
                for entity in new_entities:
                    if var_name and (var_name in entity or entity in var_name):
                        instructions.append(
                            f"## ⚠️ 本集重要：{entity} 首次登场\n"
                            f"「{var_name}」在本集首次出现，你必须通过具体场景展示：\n"
                            f"1. 视觉效果（观众能看到什么画面）\n"
                            f"2. 功能范围：{var_def}\n"
                            f"3. 使用限制/代价：{var_constraints or '需要在场景中自然交代'}\n"
                            f"不能只用一句台词或旁白一笔带过。"
                        )
                        break

        # --- 3. 反重复描写：扫描已生成剧本中的高频动作短语 ---
        existing_texts = []
        for prev_nid, prev_text in self.project_data.screenplay_texts.items():
            if prev_nid == node_id or not prev_text:
                continue
            existing_texts.append(prev_text)

        if existing_texts:
            # 提取常见动作描写短语（4-8字的重复模式）
            all_text = "\n".join(existing_texts)
            # 匹配中文动作短语模式
            phrases = re.findall(r'[\u4e00-\u9fff]{4,8}', all_text)
            phrase_counts = Counter(phrases)
            # 找出出现3次以上的短语
            overused = [p for p, c in phrase_counts.most_common(20) if c >= 3]
            if overused:
                overused_list = "、".join(f"「{p}」" for p in overused[:10])
                instructions.append(
                    f"## 描写去重（已使用过的高频表达，本集请回避）\n"
                    f"以下动作/表情描写在之前的集数中已大量使用，请换用不同的表达方式：\n"
                    f"{overused_list}\n"
                    f"如果需要表达类似情绪，请创造新的具体动作描写。"
                )

        # --- 4. 角色存活状态检测 ---
        # 扫描前序 Beat 的 causal_events，检测死亡/退场事件
        death_keywords = ["死亡", "牺牲", "被杀", "去世", "身亡", "丧命", "殒命", "阵亡", "遇害", "毒杀", "处死"]
        char_names = [c.get("name", "") for c in self.project_data.characters if c.get("name")]
        deceased_chars = []

        for prev_nid, prev_beat in self.project_data.confirmed_beats.items():
            if not prev_beat or prev_nid == node_id:
                continue
            prev_ep = self._extract_episode_number(prev_nid)
            if prev_ep >= episode_number:
                continue
            for event in prev_beat.get("causal_events", []):
                action = event.get("action", "") + event.get("causal_impact", "")
                # 检查是否包含死亡关键词
                has_death = any(kw in action for kw in death_keywords)
                if has_death:
                    # 检查是哪个角色
                    for name in char_names:
                        if name in action and name not in [d["name"] for d in deceased_chars]:
                            deceased_chars.append({
                                "name": name,
                                "episode": prev_nid,
                                "event": action[:50],
                            })

        if deceased_chars:
            status_lines = [f"  - {d['name']}：已在 {d['episode']} 中死亡/退场（{d['event']}）" for d in deceased_chars]
            instructions.append(
                f"## 角色状态（截至本集）\n"
                f"以下角色在之前的剧情中已死亡或退场，请勿给他们分配台词或行动，也不要称呼他们的物品为\"遗物\"（除非他们确实已死亡）：\n"
                + "\n".join(status_lines)
            )

        return "\n\n".join(instructions) if instructions else ""

    # ------------------------------------------------------------------ #
    # 后处理
    # ------------------------------------------------------------------ #
    @staticmethod
    def _postprocess_screenplay(text: str) -> str:
        """过滤扩写结果中的元创作语言泄露"""
        import re
        # 移除整行包含编剧元语言的行（如独立一行的创作指导）
        meta_patterns = [
            r'^.*让观众[获知感受理解看到].*$',
            r'^.*观众会[觉得感到产生].*$',
            r'^.*此处[需要应该可以].*$',
            r'^.*编剧[意图注意备注].*$',
            r'^.*创作[意图目的说明].*$',
            r'^.*\（注[：:].*\）.*$',
        ]
        lines = text.split('\n')
        cleaned_lines = []
        for line in lines:
            stripped = line.strip()
            # 跳过完全匹配元语言的独立行（不影响台词/动作描写中的自然用法）
            is_meta_line = False
            for pat in meta_patterns:
                if re.match(pat, stripped) and not any(
                    k in stripped for k in ['（', '：', '角色名']
                ):
                    # 确保不是台词行（台词行含有角色名+冒号格式）
                    if not re.match(r'^.{1,8}（.*?）[：:]', stripped):
                        is_meta_line = True
                        break
            if not is_meta_line:
                cleaned_lines.append(line)
        return '\n'.join(cleaned_lines)

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
