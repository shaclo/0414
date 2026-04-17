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
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QFont

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

    # ------------------------------------------------------------------ #
    # 菜单
    # ------------------------------------------------------------------ #
    def _setup_menu(self):
        mb = self.menuBar()
        file_menu = mb.addMenu("文件(&F)")

        for text, shortcut, slot in [
            ("📄 新建项目",    "Ctrl+N",       self._on_new),
            ("📂 打开项目…",  "Ctrl+O",       self._on_open),
            ("💾 保存项目",    "Ctrl+S",       self._on_save),
            ("💾 另存为…",    "Ctrl+Shift+S", self._on_save_as),
        ]:
            act = QAction(text, self)
            act.setShortcut(shortcut)
            act.triggered.connect(slot)
            file_menu.addAction(act)

        # 系统菜单
        sys_menu = mb.addMenu("系统(&S)")
        bvsr_act = QAction("🎭 BVSR 人格设置…", self)
        bvsr_act.setStatusTip("管理 BVSR 多人格生成系统的人格定义（添加/删除/修改/激活）")
        bvsr_act.triggered.connect(self._on_bvsr_settings)
        sys_menu.addAction(bvsr_act)

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
        nav = QWidget()
        nav.setFixedHeight(52)
        nav.setStyleSheet("background:#1a252f;")
        nav_layout = QHBoxLayout(nav)
        nav_layout.setContentsMargins(20, 0, 20, 0)

        self._phase_labels: list = []
        for i, name in enumerate(PHASE_NAMES):
            lbl = QLabel(f"○ {name}")
            lbl.setStyleSheet("color:#7f8c8d;font-size:13px;font-weight:bold;padding:0 10px;")
            lbl.setCursor(Qt.PointingHandCursor)
            lbl.mousePressEvent = lambda e, idx=i: self._on_phase_nav_click(idx)
            nav_layout.addWidget(lbl)
            self._phase_labels.append(lbl)

            if i < len(PHASE_NAMES) - 1:
                sep = QLabel("›")
                sep.setStyleSheet("color:#4a6278;font-size:16px;")
                nav_layout.addWidget(sep)

        nav_layout.addStretch()

        for text, slot in [("📂 打开", self._on_open), ("💾 保存", self._on_save)]:
            btn = QPushButton(text)
            btn.setStyleSheet(
                "QPushButton{color:white;background:transparent;border:1px solid #4a6278;"
                "border-radius:4px;padding:4px 14px;font-size:13px;}"
                "QPushButton:hover{background:#2c3e50;}"
            )
            btn.clicked.connect(slot)
            nav_layout.addWidget(btn)

        root.addWidget(nav)

        # ===== 页面堆栈 =====
        self._stack = QStackedWidget()
        root.addWidget(self._stack)

        self._build_phases()
        self._update_nav_indicator(0)

    def _build_phases(self):
        """创建 6 个 Phase 页面并连接信号"""
        # Phase 0: 创世
        p1 = Phase1Genesis(self.project_data)
        p1.phase_completed.connect(self._on_p1_done)
        p1.status_message.connect(self._show_status)
        self._stack.addWidget(p1)            # index 0

        # Phase 1: 人物
        p2 = Phase2Characters(self.project_data)
        p2.phase_completed.connect(self._on_p2_done)
        p2.go_back.connect(lambda: self._switch_phase(0))
        p2.status_message.connect(self._show_status)
        self._stack.addWidget(p2)            # index 1

        # Phase 2: 骨架
        p3 = Phase2Skeleton(self.project_data)
        p3.phase_completed.connect(self._on_p3_done)
        p3.go_back.connect(lambda: self._switch_phase(1, call_on_enter=True))
        p3.status_message.connect(self._show_status)
        self._stack.addWidget(p3)            # index 2

        # Phase 3: 血肉
        p4 = Phase3Flesh(self.project_data)
        p4.phase_completed.connect(self._on_p4_done)
        p4.go_back_to_skeleton.connect(lambda: self._switch_phase(2, call_on_enter=True))
        p4.status_message.connect(self._show_status)
        self._stack.addWidget(p4)            # index 3

        # Phase 4: 扩写
        p5 = Phase5Expansion(self.project_data)
        p5.phase_completed.connect(self._on_p5_done)
        p5.go_back_to_flesh.connect(lambda: self._switch_phase(3, call_on_enter=True))
        p5.status_message.connect(self._show_status)
        self._stack.addWidget(p5)            # index 4

        # Phase 5: 锁定
        p6 = Phase4Lock(self.project_data)
        p6.go_back_to_flesh.connect(lambda: self._switch_phase(4, call_on_enter=True))
        p6.status_message.connect(self._show_status)
        self._stack.addWidget(p6)            # index 5

    def _setup_statusbar(self):
        self._statusbar = QStatusBar()
        self._statusbar.setStyleSheet(
            "QStatusBar{background:#ecf0f1;color:#555;border-top:1px solid #bdc3c7;}"
        )
        self.setStatusBar(self._statusbar)
        self._show_status("就绪 — 请输入你的一句话小说开始创作")

    # ------------------------------------------------------------------ #
    # Phase 切换
    # ------------------------------------------------------------------ #
    def _switch_phase(self, idx: int, call_on_enter: bool = False):
        self._stack.setCurrentIndex(idx)
        self._update_nav_indicator(idx)
        if call_on_enter:
            w = self._stack.currentWidget()
            if hasattr(w, "on_enter"):
                w.on_enter()

    def _update_nav_indicator(self, current: int):
        highest = self._get_highest_completed_phase() if hasattr(self, 'project_data') else -1
        for i, lbl in enumerate(self._phase_labels):
            if i == current:
                lbl.setText(f"◉ {PHASE_NAMES[i]}")
                lbl.setStyleSheet("color:#3498db;font-size:13px;font-weight:bold;padding:0 10px;")
            elif i <= highest:
                lbl.setText(f"✅ {PHASE_NAMES[i]}")
                lbl.setStyleSheet("color:#27ae60;font-size:13px;font-weight:bold;padding:0 10px;cursor:pointer;")
            else:
                lbl.setText(f"○ {PHASE_NAMES[i]}")
                lbl.setStyleSheet("color:#7f8c8d;font-size:13px;font-weight:bold;padding:0 10px;")

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
        self._switch_phase(1, call_on_enter=True)   # → 人物

    def _on_p2_done(self):
        self._auto_save()
        self._switch_phase(2, call_on_enter=True)   # → 骨架

    def _on_p3_done(self):
        self._auto_save()
        self._switch_phase(3, call_on_enter=True)   # → 血肉

    def _on_p4_done(self):
        self._auto_save()
        self._switch_phase(4, call_on_enter=True)   # → 扩写

    def _on_p5_done(self):
        self._auto_save()
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
        except Exception as e:
            QMessageBox.critical(self, "打开失败", str(e))

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

    def _on_bvsr_settings(self):
        from ui.widgets.bvsr_settings_dialog import BVSRSettingsDialog
        dlg = BVSRSettingsDialog(parent=self)
        dlg.exec()

    def _do_save(self, filepath: str):
        try:
            self.project_data.save_to_file(filepath)
            self._show_status(f"💾 已保存: {filepath}")
        except Exception as e:
            QMessageBox.critical(self, "保存失败", str(e))

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
