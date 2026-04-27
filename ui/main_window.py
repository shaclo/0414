# ============================================================
# ui/main_window.py
# 主窗口：6 Phase 导航 + QStackedWidget + 菜单 + 状态栏
# Phase 1: 创世  Phase 2: 人物  Phase 3: 骨架
# Phase 4: 血肉  Phase 5: 扩写  Phase 6: 锁定
# ============================================================

import os
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QStackedWidget, QFileDialog, QMessageBox, QStatusBar,
    QScrollArea,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QFont

from services.logger_service import app_logger
from services.theme_manager import theme_manager

from models.project_state import ProjectData
from ui.phase1_genesis import Phase1Genesis
from ui.phase2_characters import Phase2Characters
from ui.phase2_skeleton import Phase2Skeleton       # 原骨架，保持文件名
from ui.phase3_flesh import Phase3Flesh             # 原血肉，保持文件名
from ui.phase5_expansion import Phase5Expansion
from ui.phase4_lock import Phase4Lock               # 原锁定，保持文件名


# 6 个阶段：文件内部索引 0-5
PHASE_NAMES = ["创世", "人物", "骨架", "血肉", "扩写", "锁定"]
PHASE_TO_IDX = {
    "genesis":   0,
    "character": 1,
    "skeleton":  2,
    "flesh":     3,
    "expansion": 4,
    "locked":    5,
}


class MainWindow(QMainWindow):
    """
    一句话剧本生成器主窗口（V2: 6阶段）。

    顶部:  导航指示器（6 个 Phase 步骤）+ 快捷保存/打开
    中间:  QStackedWidget（6 个 Phase 页面）
    底部:  状态栏
    菜单:  文件 → 新建/打开/保存
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("短剧剧本生成器 — NarrativeLoom BVSR × Causal Distillation  [V2]")
        self.resize(1366, 900)

        self.project_data = ProjectData()
        self._current_filepath: str = ""

        self._setup_menu()
        self._setup_ui()
        self._setup_statusbar()

        # 注册导航栏颜色刷新回调（主题切换时自动调用）
        theme_manager.register_nav_callback(self._refresh_nav_style)

    # ------------------------------------------------------------------ #
    # 菜单
    # ------------------------------------------------------------------ #
    def _setup_menu(self):
        mb = self.menuBar()
        file_menu = mb.addMenu("文件(&F)")

        for text, shortcut, slot in [
            ("新建项目",    "Ctrl+N",       self._on_new),
            ("打开项目...",  "Ctrl+O",       self._on_open),
            ("保存项目",    "Ctrl+S",       self._on_save),
            ("另存为...",    "Ctrl+Shift+S", self._on_save_as),
        ]:
            act = QAction(text, self)
            act.setShortcut(shortcut)
            act.triggered.connect(slot)
            file_menu.addAction(act)

        file_menu.addSeparator()
        log_act = QAction("查看日志", self)
        log_act.setStatusTip("查看应用运行日志，包含所有 AI 调用的完整 Prompt 和结果记录")
        log_act.triggered.connect(self._on_view_log)
        file_menu.addAction(log_act)

        file_menu.addSeparator()
        exit_act = QAction("退出(&Q)", self)
        exit_act.setShortcut("Ctrl+Q")
        exit_act.triggered.connect(self.close)
        file_menu.addAction(exit_act)

        # 工具菜单
        sys_menu = mb.addMenu("工具(&T)")

        # 主题设置（在模型设置之上）
        theme_act = QAction("主题设置...", self)
        theme_act.setStatusTip("设置界面字体、字号和配色主题（即时生效，无需重启）")
        theme_act.triggered.connect(self._on_theme_settings)
        sys_menu.addAction(theme_act)

        sys_menu.addSeparator()

        model_act = QAction("模型设置...", self)
        model_act.setStatusTip("配置 AI 供应商（Vertex AI / 豆包 / DeepSeek 等）、模型切换和鉴权")
        model_act.triggered.connect(self._on_model_settings)
        sys_menu.addAction(model_act)

        sys_menu.addSeparator()

        bvsr_act = QAction("BVSR 人格设置...", self)
        bvsr_act.setStatusTip("管理 BVSR 多人格生成系统的人格定义（添加/删除/修改/激活）")
        bvsr_act.triggered.connect(self._on_bvsr_settings)
        sys_menu.addAction(bvsr_act)

        strategy_act = QAction("回答风格策略...", self)
        strategy_act.setStatusTip("管理苏格拉底问答阶段「AI 自动回答」的风格策略和 Prompt 指令")
        strategy_act.triggered.connect(self._on_answer_strategy_settings)
        sys_menu.addAction(strategy_act)

        genre_act = QAction("题材预设...", self)
        genre_act.setStatusTip("查看并切换当前项目的写作题材预设（犯罪/爱情/悬疑/复仇等）")
        genre_act.triggered.connect(self._on_genre_settings)
        sys_menu.addAction(genre_act)


        sys_menu.addSeparator()
        skel_ai_act = QAction("骨架 — AI辅助修改设置...", self)
        skel_ai_act.setStatusTip("管理骨架节点快速重生成的情节方向、结构微调和 Prompt 模板")
        skel_ai_act.triggered.connect(self._on_skeleton_ai_settings)
        sys_menu.addAction(skel_ai_act)

        sys_menu.addSeparator()
        expansion_act = QAction("扩写设置 — 爽感 && 钩子公式...", self)
        expansion_act.setStatusTip("管理爽感节奏公式和结尾钩子公式的 Prompt 模板（随机抽样注入）")
        expansion_act.triggered.connect(self._on_expansion_template_settings)
        sys_menu.addAction(expansion_act)

        # 系统菜单
        system_menu = mb.addMenu("系统(&S)")
        update_act = QAction("系统更新 / 版本信息...", self)
        update_act.setStatusTip("查看当前系统版本号和最后更新日期")
        update_act.triggered.connect(self._on_system_update)
        system_menu.addAction(update_act)

    # ------------------------------------------------------------------ #
    # 主 UI
    # ------------------------------------------------------------------ #
    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ===== 导航栏 =====
        self._nav_widget = QWidget()
        self._nav_widget.setFixedHeight(52)
        nav_layout = QHBoxLayout(self._nav_widget)
        nav_layout.setContentsMargins(20, 0, 20, 0)

        self._phase_labels: list = []
        self._nav_sep_labels: list = []
        for i, name in enumerate(PHASE_NAMES):
            lbl = QLabel(f"○ {name}")
            lbl.setCursor(Qt.PointingHandCursor)
            lbl.mousePressEvent = lambda e, idx=i: self._on_phase_nav_click(idx)
            nav_layout.addWidget(lbl)
            self._phase_labels.append(lbl)

            if i < len(PHASE_NAMES) - 1:
                sep = QLabel("›")
                sep.setStyleSheet("")
                nav_layout.addWidget(sep)
                self._nav_sep_labels.append(sep)

        nav_layout.addStretch()

        self._nav_btns: list = []
        for text, slot in [("📂 打开", self._on_open), ("💾 保存", self._on_save)]:
            btn = QPushButton(text)
            btn.clicked.connect(slot)
            nav_layout.addWidget(btn)
            self._nav_btns.append(btn)

        root.addWidget(self._nav_widget)

        # 根据当前主题初始化导航栏颜色
        self._refresh_nav_style(theme_manager.get_current_theme())

        # ===== 页面堆栈 =====
        self._stack = QStackedWidget()
        root.addWidget(self._stack)

        self._build_phases()
        self._update_nav_indicator(0)

    def _wrap_in_scroll(self, widget: QWidget) -> QScrollArea:
        """将 Phase 页面包裹在 QScrollArea 中，防止窗口过小时内容被挤压"""
        scroll = QScrollArea()
        scroll.setWidget(widget)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        return scroll

    def _build_phases(self):
        """创建 6 个 Phase 页面并连接信号"""
        self._phase_widgets = []  # 保存原始 Phase 引用

        # Phase 0: 创世
        p1 = Phase1Genesis(self.project_data)
        p1.phase_completed.connect(self._on_p1_done)
        p1.status_message.connect(self._show_status)
        self._stack.addWidget(self._wrap_in_scroll(p1))  # index 0
        self._phase_widgets.append(p1)

        # Phase 1: 人物
        p2 = Phase2Characters(self.project_data)
        p2.phase_completed.connect(self._on_p2_done)
        p2.go_back.connect(lambda: self._switch_phase(0))
        p2.status_message.connect(self._show_status)
        self._stack.addWidget(self._wrap_in_scroll(p2))  # index 1
        self._phase_widgets.append(p2)

        # Phase 2: 骨架
        p3 = Phase2Skeleton(self.project_data)
        p3.phase_completed.connect(self._on_p3_done)
        p3.go_back.connect(lambda: self._switch_phase(1, call_on_enter=True))
        p3.status_message.connect(self._show_status)
        self._stack.addWidget(self._wrap_in_scroll(p3))  # index 2
        self._phase_widgets.append(p3)

        # Phase 3: 血肉
        p4 = Phase3Flesh(self.project_data)
        p4.phase_completed.connect(self._on_p4_done)
        p4.go_back_to_skeleton.connect(lambda: self._switch_phase(2, call_on_enter=True))
        p4.status_message.connect(self._show_status)
        self._stack.addWidget(self._wrap_in_scroll(p4))  # index 3
        self._phase_widgets.append(p4)

        # Phase 4: 扩写
        p5 = Phase5Expansion(self.project_data)
        p5.phase_completed.connect(self._on_p5_done)
        p5.go_back_to_flesh.connect(lambda: self._switch_phase(3, call_on_enter=True))
        p5.status_message.connect(self._show_status)
        self._stack.addWidget(self._wrap_in_scroll(p5))  # index 4
        self._phase_widgets.append(p5)

        # Phase 5: 锁定
        p6 = Phase4Lock(self.project_data)
        p6.go_back_to_flesh.connect(lambda: self._switch_phase(4, call_on_enter=True))
        p6.status_message.connect(self._show_status)
        self._stack.addWidget(self._wrap_in_scroll(p6))  # index 5
        self._phase_widgets.append(p6)

    def _setup_statusbar(self):
        self._statusbar = QStatusBar()
        self.setStatusBar(self._statusbar)
        self._show_status("就绪 — 请输入你的一句话小说开始创作")

    # ------------------------------------------------------------------ #
    # Phase 切换
    # ------------------------------------------------------------------ #
    def _switch_phase(self, idx: int, call_on_enter: bool = False):
        self._stack.setCurrentIndex(idx)
        self._update_nav_indicator(idx)
        if call_on_enter:
            w = self._phase_widgets[idx]
            if hasattr(w, "on_enter"):
                w.on_enter()

    def _update_nav_indicator(self, current: int):
        highest = self._get_highest_completed_phase() if hasattr(self, 'project_data') else -1
        p = theme_manager.get_current_theme()
        for i, lbl in enumerate(self._phase_labels):
            if i == current:
                lbl.setText(f"◉ {PHASE_NAMES[i]}")
                lbl.setStyleSheet(
                    f"color:{p['nav_active']};font-weight:bold;"
                    f"padding:0 10px;background:transparent;"
                )
            elif i <= highest:
                lbl.setText(f"✅ {PHASE_NAMES[i]}")
                lbl.setStyleSheet(
                    f"color:{p['success']};font-weight:bold;"
                    f"padding:0 10px;cursor:pointer;background:transparent;"
                )
            else:
                lbl.setText(f"○ {PHASE_NAMES[i]}")
                lbl.setStyleSheet(
                    f"color:{p['nav_text']};font-weight:bold;"
                    f"padding:0 10px;background:transparent;"
                )

    def _on_phase_nav_click(self, idx: int):
        """
        点击导航标签跳转到已完成的阶段（前进或回退均可）。
        - 已完成阶段（✅）：直接跳转，不丢失数据
        - 当前阶段（◉）：忽略
        - 未到达阶段（○）：不允许
        """
        current = self._stack.currentIndex()
        if idx == current:
            return

        # 获取最高已完成阶段索引
        highest = self._get_highest_completed_phase()

        if idx > highest:
            QMessageBox.information(
                self, "提示",
                f"「{PHASE_NAMES[idx]}」阶段尚未完成，无法跳转。\n"
                f"请按流程完成前序阶段后再进入。",
            )
            return

        self._switch_phase(idx, call_on_enter=True)

    def _get_highest_completed_phase(self) -> int:
        """根据 project_data 状态判断最高已完成的阶段索引"""
        pd = self.project_data

        # 根据 current_phase 和数据状态判断
        phase_str = pd.current_phase
        phase_idx = PHASE_TO_IDX.get(phase_str, 0)

        # current_phase 指向的是"正在进行"的阶段，所以已完成的是它本身
        # 但如果有数据支撑，可以回到该阶段
        highest = phase_idx

        # 额外检查：如果已有数据，允许回到对应阶段
        if pd.world_variables:
            highest = max(highest, 0)  # 创世完成
        if pd.characters or pd.current_phase in ("skeleton", "flesh", "expansion", "locked"):
            highest = max(highest, 1)  # 人物完成
        if pd.cpg_nodes:
            highest = max(highest, 2)  # 骨架完成
        if any(v for v in pd.confirmed_beats.values()):
            highest = max(highest, 3)  # 血肉（至少部分完成）

        return highest

    # ------------------------------------------------------------------ #
    # Phase 完成回调
    # ------------------------------------------------------------------ #
    def _on_p1_done(self, _data):
        self._auto_save()
        app_logger.success("主窗口", "创世阶段完成，进入人物设定阶段")
        self._switch_phase(1, call_on_enter=True)   # → 人物

    def _on_p2_done(self):
        self._auto_save()
        app_logger.success("主窗口", "人物设定阶段完成，进入骨架阶段")
        self._switch_phase(2, call_on_enter=True)   # → 骨架

    def _on_p3_done(self):
        self._auto_save()
        app_logger.success("主窗口", "骨架阶段完成，进入血肉阶段")
        self._switch_phase(3, call_on_enter=True)   # → 血肉

    def _on_p4_done(self):
        self._auto_save()
        app_logger.success("主窗口", "血肉阶段完成，进入扩写阶段")
        self._switch_phase(4, call_on_enter=True)   # → 扩写

    def _on_p5_done(self):
        self._auto_save()
        app_logger.success("主窗口", "扩写阶段完成，进入锁定阶段")
        self._switch_phase(5, call_on_enter=True)   # → 锁定

    # ------------------------------------------------------------------ #
    # 文件操作
    # ------------------------------------------------------------------ #
    def _on_new(self):
        reply = QMessageBox.question(
            self, "新建项目",
            "新建项目将清空当前进度（未保存内容会丢失）。确定吗？",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.No:
            return
        self.project_data = ProjectData()
        self._current_filepath = ""
        self._rebuild_phases()
        self._switch_phase(0)
        self._show_status("新建项目")
        app_logger.info("文件操作", "新建项目")

    def _on_open(self):
        os.makedirs("projects", exist_ok=True)
        filepath, _ = QFileDialog.getOpenFileName(
            self, "打开项目", "projects/",
            "Story JSON (*.story.json);;All Files (*)",
        )
        if not filepath:
            return
        try:
            self.project_data = ProjectData.load_from_file(filepath)
            self._current_filepath = filepath
            self._rebuild_phases()
            phase_str = self.project_data.current_phase
            idx = PHASE_TO_IDX.get(phase_str, 0)
            self._switch_phase(idx, call_on_enter=(idx >= 1))
            self._show_status(f"已打开: {filepath}")
            app_logger.info("文件操作", f"打开项目: {os.path.basename(filepath)}",
                            f"完整路径: {filepath}\n当前阶段: {phase_str}")
        except Exception as e:
            QMessageBox.critical(self, "打开失败", str(e))
            app_logger.error("文件操作", f"打开项目失败: {str(e)}", f"文件路径: {filepath}")

    def _on_save(self):
        if self._current_filepath:
            self._do_save(self._current_filepath)
        else:
            self._on_save_as()

    def _on_save_as(self):
        os.makedirs("projects", exist_ok=True)
        name = self.project_data.story_title or "untitled"
        filepath, _ = QFileDialog.getSaveFileName(
            self, "保存项目", f"projects/{name}.story.json",
            "Story JSON (*.story.json);;All Files (*)",
        )
        if filepath:
            self._do_save(filepath)
            self._current_filepath = filepath

    def _on_theme_settings(self):
        from ui.widgets.theme_settings_dialog import ThemeSettingsDialog
        dlg = ThemeSettingsDialog(parent=self)
        dlg.exec()
        # 对话框关闭后刷新导航栏（主题可能已变更）
        self._refresh_nav_style(theme_manager.get_current_theme())
        self._update_nav_indicator(self._stack.currentIndex())

    def _refresh_nav_style(self, palette: dict):
        """根据调色板刷新导航栏背景色和按钮样式"""
        if not hasattr(self, '_nav_widget'):
            return
        nav_bg = palette.get('nav_bg', '#1a252f')
        nav_text = palette.get('nav_text', '#7f8c8d')
        nav_sep = palette.get('nav_sep', '#4a6278')
        self._nav_widget.setStyleSheet(f"background:{nav_bg};")
        # 分隔符
        for sep in getattr(self, '_nav_sep_labels', []):
            sep.setStyleSheet(f"color:{nav_sep};background:transparent;")
        # 快捷按钮
        for btn in getattr(self, '_nav_btns', []):
            btn.setStyleSheet(
                f"QPushButton{{color:white;background:transparent;"
                f"border:1px solid {nav_sep};"
                f"border-radius:4px;padding:4px 14px;}}"
                f"QPushButton:hover{{background:{palette.get('accent', '#2c3e50')};border-color:{palette.get('accent', '#2c3e50')};}}"
            )
        # 刷新导航标签（当前阶段）
        if hasattr(self, '_stack'):
            self._update_nav_indicator(self._stack.currentIndex())

    def _on_model_settings(self):
        from ui.widgets.model_settings_dialog import ModelSettingsDialog
        dlg = ModelSettingsDialog(parent=self)
        dlg.exec()
        # 刷新 Phase3 的供应商多选框
        from ui.phase3_flesh import Phase3Flesh
        for w in self._phase_widgets:
            if isinstance(w, Phase3Flesh) and hasattr(w, '_refresh_provider_checkboxes'):
                w._refresh_provider_checkboxes()

    def _on_bvsr_settings(self):
        from ui.widgets.bvsr_settings_dialog import BVSRSettingsDialog
        dlg = BVSRSettingsDialog(parent=self)
        dlg.exec()
        # 刷新所有 Phase3Flesh 中的人格选择面板
        from ui.phase3_flesh import Phase3Flesh
        for w in self._phase_widgets:
            if isinstance(w, Phase3Flesh) and hasattr(w, '_persona_selector'):
                w._persona_selector.refresh()

    def _on_answer_strategy_settings(self):
        from ui.widgets.answer_strategy_dialog import AnswerStrategyDialog
        dlg = AnswerStrategyDialog(parent=self)
        dlg.exec()
        # 刷新 Phase1 的 QAPanel 策略下拉框
        from ui.phase1_genesis import Phase1Genesis
        for w in self._phase_widgets:
            if isinstance(w, Phase1Genesis) and hasattr(w, '_qa_panel'):
                w._qa_panel.refresh_strategies()


    def _on_genre_settings(self):
        from ui.widgets.genre_settings_dialog import GenreSettingsDialog
        dlg = GenreSettingsDialog(project_data=self.project_data, parent=self)
        dlg.exec()

    def _on_skeleton_ai_settings(self):
        from ui.widgets.skeleton_ai_settings_dialog import SkeletonAISettingsDialog
        dlg = SkeletonAISettingsDialog(project_data=self.project_data, parent=self)
        dlg.exec()

    def _on_expansion_template_settings(self):
        from ui.widgets.prompt_template_dialog import PromptTemplateDialog
        dlg = PromptTemplateDialog(parent=self)
        dlg.exec()

    def _on_system_update(self):
        from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFormLayout,
                                       QProgressBar, QTextEdit)
        from PySide6.QtCore import Qt as _Qt
        from env import APP_VERSION, APP_BUILD_DATE, GITHUB_RELEASES_API

        dlg = QDialog(self)
        dlg.setWindowTitle("系统更新")
        dlg.setMinimumWidth(680)
        dlg.setMinimumHeight(420)

        main_layout = QVBoxLayout(dlg)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(24, 24, 24, 24)

        # 标题
        title = QLabel("📽️ 短剧剧本生成器")
        title.setStyleSheet(" font-weight:bold;")
        title.setAlignment(_Qt.AlignCenter)
        main_layout.addWidget(title)

        subtitle = QLabel("NarrativeLoom BVSR × Causal Distillation")
        subtitle.setStyleSheet(" color:#7f8c8d;")
        subtitle.setAlignment(_Qt.AlignCenter)
        main_layout.addWidget(subtitle)

        sep = QLabel()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background:#dcdde1;")
        main_layout.addWidget(sep)

        # Content Layout (Horizontal Split)
        content_layout = QHBoxLayout()
        main_layout.addLayout(content_layout)

        # Left Side (Info & Actions)
        left_layout = QVBoxLayout()
        content_layout.addLayout(left_layout, 1)

        # 版本信息
        info_layout = QFormLayout()
        info_layout.setSpacing(6)
        ver_label = QLabel(f"v{APP_VERSION}")
        ver_label.setStyleSheet(" font-weight:bold; color:#2980b9;")
        info_layout.addRow("当前版本：", ver_label)
        date_label = QLabel(APP_BUILD_DATE)
        date_label.setStyleSheet("")
        info_layout.addRow("最后更新：", date_label)
        left_layout.addLayout(info_layout)

        sep2 = QLabel()
        sep2.setFixedHeight(1)
        sep2.setStyleSheet("background:#dcdde1;")
        left_layout.addWidget(sep2)

        # 状态区
        status_label = QLabel("点击「检查更新」查看是否有新版本。")
        status_label.setWordWrap(True)
        status_label.setStyleSheet(" margin-top:4px;")
        left_layout.addWidget(status_label)

        # 进度条
        progress_bar = QProgressBar()
        progress_bar.setRange(0, 100)
        progress_bar.setValue(0)
        progress_bar.setTextVisible(True)
        progress_bar.setStyleSheet(
            "QProgressBar{border:1px solid #dcdde1;border-radius:4px;text-align:center;height:22px;}"
            "QProgressBar::chunk{background:#27ae60;border-radius:3px;}"
        )
        progress_bar.hide()
        left_layout.addWidget(progress_bar)

        left_layout.addStretch()

        # 按钮
        btn_check = QPushButton("🔍 检查更新")
        btn_check.setStyleSheet(
            "QPushButton{background:#3498db;color:white;border:none;"
            "border-radius:4px;padding:8px 16px;font-weight:bold;}"
            "QPushButton:hover{background:#2980b9;}"
            "QPushButton:disabled{background:#bdc3c7;}"
        )
        left_layout.addWidget(btn_check)

        btn_download = QPushButton("⬇️ 下载并更新")
        btn_download.setStyleSheet(
            "QPushButton{background:#27ae60;color:white;border:none;"
            "border-radius:4px;padding:8px 16px;font-weight:bold;}"
            "QPushButton:hover{background:#229954;}"
            "QPushButton:disabled{background:#bdc3c7;}"
        )
        btn_download.hide()
        left_layout.addWidget(btn_download)

        btn_restart = QPushButton("🔄 立即重启应用")
        btn_restart.setStyleSheet(
            "QPushButton{background:#e74c3c;color:white;border:none;"
            "border-radius:4px;padding:8px 16px;font-weight:bold;}"
            "QPushButton:hover{background:#c0392b;}"
        )
        btn_restart.hide()
        left_layout.addWidget(btn_restart)

        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(dlg.accept)
        left_layout.addWidget(btn_close)

        # Right Side (Update Notes)
        right_layout = QVBoxLayout()
        content_layout.addLayout(right_layout, 1)

        log_label = QLabel("更新内容：")
        log_label.setStyleSheet("font-weight:bold; color:#2c3e50;")
        right_layout.addWidget(log_label)

        log_edit = QTextEdit()
        log_edit.setReadOnly(True)
        log_edit.setPlaceholderText("暂无更新内容或未检查更新...")
        log_edit.setStyleSheet(
            "QTextEdit{background:#f8f9fa;border:1px solid #dcdde1;"
            "border-radius:4px;padding:6px;}"
        )
        right_layout.addWidget(log_edit)

        # — 逻辑 —
        _state = {"download_url": "", "checker": None, "downloader": None}

        def on_check():
            btn_check.setEnabled(False)
            status_label.setText("🔍 正在检查更新…")
            status_label.setStyleSheet(" color:#e67e22;")

            from services.updater import UpdateChecker
            checker = UpdateChecker(GITHUB_RELEASES_API, APP_VERSION)
            _state["checker"] = checker  # prevent GC

            def on_result(info):
                if info["has_update"]:
                    status_label.setText(
                        f"✅ 发现新版本: v{info['latest_version']}（当前: v{APP_VERSION}）"
                    )
                    status_label.setStyleSheet(" color:#27ae60; font-weight:bold;")
                    log_edit.setMarkdown(info["release_notes"])
                    log_edit.show()
                    _state["download_url"] = info["download_url"]
                    btn_download.show()
                else:
                    status_label.setText(f"✅ 当前已是最新版本 v{APP_VERSION}")
                    status_label.setStyleSheet(" color:#27ae60;")
                btn_check.setEnabled(True)

            def on_error(msg):
                status_label.setText(f"❌ {msg}")
                status_label.setStyleSheet(" color:#e74c3c;")
                btn_check.setEnabled(True)

            checker.result.connect(on_result)
            checker.error.connect(on_error)
            checker.start()

        def on_download():
            if not _state["download_url"]:
                return
            btn_download.setEnabled(False)
            btn_check.setEnabled(False)
            progress_bar.show()
            progress_bar.setValue(0)

            import os as _os
            app_dir = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))

            from services.updater import UpdateDownloader
            downloader = UpdateDownloader(_state["download_url"], app_dir)
            _state["downloader"] = downloader  # prevent GC

            def on_progress(pct, msg):
                progress_bar.setValue(pct)
                status_label.setText(msg)
                status_label.setStyleSheet(" color:#2980b9;")

            def on_finished(success, msg):
                if success:
                    status_label.setText(f"✅ {msg}")
                    status_label.setStyleSheet(" color:#27ae60; font-weight:bold;")
                    progress_bar.setValue(100)
                    btn_download.hide()
                    btn_restart.show()
                else:
                    status_label.setText(f"❌ {msg}")
                    status_label.setStyleSheet(" color:#e74c3c;")
                    btn_download.setEnabled(True)
                btn_check.setEnabled(True)

            downloader.progress.connect(on_progress)
            downloader.finished.connect(on_finished)
            downloader.start()

        def on_restart():
            import sys as _sys
            import os as _os2
            import subprocess
            python = _sys.executable
            app_dir = _os2.path.dirname(_os2.path.dirname(_os2.path.abspath(__file__)))
            main_py = _os2.path.join(app_dir, "main.py")
            subprocess.Popen([python, main_py], cwd=app_dir)
            QApplication.quit()

        btn_check.clicked.connect(on_check)
        btn_download.clicked.connect(on_download)
        btn_restart.clicked.connect(on_restart)

        dlg.exec()

    def _do_save(self, filepath: str):
        try:
            self.project_data.save_to_file(filepath)
            basename = os.path.basename(filepath)
            self._show_status(f"💾 已保存: {filepath}")
            QMessageBox.information(self, "保存成功", f"工程文件已保存。\n文件: {basename}\n路径: {filepath}")
            app_logger.success("文件操作", f"保存项目: {basename}", f"完整路径: {filepath}")
        except Exception as e:
            QMessageBox.critical(self, "保存失败", str(e))
            app_logger.error("文件操作", f"保存项目失败: {str(e)}", f"文件路径: {filepath}")

    def _on_view_log(self):
        """打开日志查看对话框"""
        from ui.widgets.log_viewer_dialog import LogViewerDialog
        dlg = LogViewerDialog(parent=self)
        dlg.exec()

    def _auto_save(self):
        """Phase 切换时自动保存（如果已有路径）"""
        if self._current_filepath:
            try:
                self.project_data.save_to_file(self._current_filepath)
            except Exception:
                pass

    # ------------------------------------------------------------------ #
    # 工具方法
    # ------------------------------------------------------------------ #
    def _show_status(self, msg: str):
        self._statusbar.showMessage(msg)

    def _rebuild_phases(self):
        """加载新项目后重建所有 Phase 页面（共享新 project_data）"""
        while self._stack.count():
            w = self._stack.widget(0)
            self._stack.removeWidget(w)
            w.deleteLater()
        self._build_phases()
