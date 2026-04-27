# ============================================================
# ui/phase2_skeleton.py
# Phase 2: 骨架 — CPG 骨架生成 + 可视化编辑
# ============================================================

import json
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QSplitter, QTextEdit, QMessageBox,
    QGroupBox, QInputDialog, QDoubleSpinBox, QFrame, QComboBox, QLineEdit,
    QListWidget, QListWidgetItem, QDialog, QDialogButtonBox, QFormLayout, QCheckBox,
    QSlider, QRadioButton, QButtonGroup, QScrollArea, QStyledItemDelegate,
)
from PySide6.QtCore import Qt, Signal, QTimer, QSize, QRect
from PySide6.QtGui import QColor, QFont, QPainter, QPen

from ui.widgets.range_slider import DurationRangeWidget
from ui.widgets.hook_selector_widget import HookSelectorWidget

from env import SYSTEM_PROMPT_CPG_SKELETON, USER_PROMPT_CPG_SKELETON, SUGGESTED_TEMPERATURES
from services.worker import CPGSkeletonWorker, SegmentSkeletonWorker
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


class NodeCardDelegate(QStyledItemDelegate):
    """自定义卡片 delegate，支持两行文字显示"""
    LINE1_ROLE = 266
    LINE2_ROLE = 267

    def paint(self, painter: QPainter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)

        from PySide6.QtWidgets import QStyle
        rect = option.rect.adjusted(2, 2, -2, -2)

        # 基础白底卡片
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#ffffff"))
        painter.drawRoundedRect(rect, 6, 6)

        # 左侧彩色饰条 (根据阶段颜色)
        bg = index.data(Qt.BackgroundRole)
        stage_color = bg.color() if (bg and hasattr(bg, 'color')) else QColor("#b2bec3")
        ribbon_rect = QRect(rect.left(), rect.top(), 6, rect.height())
        painter.setBrush(stage_color)
        painter.setClipRect(ribbon_rect)
        painter.drawRoundedRect(rect, 6, 6)
        painter.setClipping(False)

        # 边框和交互状态
        if option.state & QStyle.State_Selected:
            painter.setPen(QPen(QColor("#0984e3"), 2))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(rect, 6, 6)
        elif option.state & QStyle.State_MouseOver:
            painter.setPen(QPen(QColor("#74b9ff"), 1))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(rect, 6, 6)
        else:
            painter.setPen(QPen(QColor("#dcdde1"), 1))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(rect, 6, 6)

        # 文本区域 (留出左侧 ribbon 的空间)
        text_rect = rect.adjusted(12, 4, -4, -4)
        line1 = str(index.data(self.LINE1_ROLE) or index.data(Qt.DisplayRole) or "")
        line2 = str(index.data(self.LINE2_ROLE) or "")

        h = text_rect.height()
        line1_rect = QRect(text_rect.left(), text_rect.top(), text_rect.width(), h // 2)
        line2_rect = QRect(text_rect.left(), text_rect.top() + h // 2, text_rect.width(), h // 2)

        # 第一行：粗体
        f1 = QFont(painter.font())
        f1.setBold(True)
        f1.setPointSize(9)
        painter.setFont(f1)
        painter.setPen(QColor("#2c3e50"))
        # PySide6 的 drawText 标志位可以直接传整数 0x0080 | 0x0001
        painter.drawText(line1_rect, Qt.AlignVCenter | Qt.AlignLeft, line1)

        # 第二行：常规，稍小
        f2 = QFont(painter.font())
        f2.setBold(False)
        f2.setPointSize(8)
        painter.setFont(f2)
        painter.setPen(QColor("#636e72"))
        painter.drawText(line2_rect, Qt.AlignVCenter | Qt.AlignLeft, line2)

        painter.restore()

    def sizeHint(self, option, index):
        return QSize(185, 52)



# ============================================================
# 整数输入框（基于 QDoubleSpinBox，外观与每集时长控件完全一致）
# ============================================================
class _IntSpinBox(QDoubleSpinBox):
    """用 QDoubleSpinBox 模拟整数输入，外观与 DurationRangeWidget 完全一致。"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDecimals(0)
        self.setSingleStep(1.0)

    def value(self) -> int:  # type: ignore[override]
        return int(super().value())

    def setValue(self, v) -> None:
        super().setValue(float(v))

    def setRange(self, minimum, maximum) -> None:
        super().setRange(float(minimum), float(maximum))


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



# ============================================================
# 第一章版本选择对话框
# ============================================================
class Ch1VersionDialog(QDialog):
    """
    左右分栏：左侧版本卡片列表，右侧选中版本的详情。
    用户确认后返回所选节点。
    """
    def __init__(self, versions: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("📖 选择第一章方案")
        self.setWindowFlags(self.windowFlags() | Qt.WindowMaximizeButtonHint)
        self.setMinimumSize(900, 660)
        self.resize(1100, 750)
        self._versions = versions
        self._selected_node = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # 顶部提示
        hint = QLabel("👈 点选左侧版本查看详情，确认满意的方案后点击「确认此版本」作为第一章。")
        hint.setStyleSheet("color:#7f8c8d; padding:4px 0;")
        layout.addWidget(hint)

        # 左右分栏
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(6)

        # ── 左侧：版本卡片列表 ──
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)
        left_layout.addWidget(QLabel(f"<b>共 {len(self._versions)} 个版本</b>"))

        self._list = QListWidget()
        self._list.setWordWrap(True)
        self._list.setSpacing(4)
        self._list.setStyleSheet("""
            QListWidget {
                background: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 6px;
            }
            QListWidget::item {
                background: #ffffff;
                border: 1px solid #dee2e6;
                border-radius: 5px;
                padding: 8px 10px;
                margin: 3px 4px;
                color: #2d3436;
            }
            QListWidget::item:selected {
                background: #d0ebff;
                border: 2px solid #339af0;
                color: #1971c2;
            }
            QListWidget::item:hover {
                background: #f0f4f8;
            }
        """)
        for i, node in enumerate(self._versions):
            title = node.get("title", "无标题")
            hook  = node.get("episode_hook", "")
            text  = f"版本 {i+1}\n{title}\n钩子: {hook[:45]}{'…' if len(hook)>45 else ''}"
            item  = QListWidgetItem(text)
            item.setData(Qt.UserRole, i)
            from PySide6.QtCore import QSize
            item.setSizeHint(QSize(250, 95))
            self._list.addItem(item)

        self._list.currentRowChanged.connect(self._on_row_changed)
        left_layout.addWidget(self._list, 1)
        splitter.addWidget(left)

        # ── 右侧：版本详情 ──
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(QLabel("<b>版本详情</b>"))

        self._detail = QTextEdit()
        self._detail.setReadOnly(True)
        from services.theme_manager import theme_manager as _tm
        _, _fs = _tm.get_current_font()
        self._detail.setStyleSheet(
            f"QTextEdit {{ background:#fff; border:1px solid #dee2e6;"
            f" border-radius:6px; padding:10px; font-size:{_fs}pt; color:#2d3436; }}"
        )
        right_layout.addWidget(self._detail, 1)
        splitter.addWidget(right)

        splitter.setSizes([280, 680])
        layout.addWidget(splitter, 1)

        # 底部按钮
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_cancel = QPushButton("取消")
        btn_cancel.setMinimumWidth(90)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)

        self._btn_confirm = QPushButton("✅ 确认此版本")
        self._btn_confirm.setMinimumWidth(140)
        self._btn_confirm.setStyleSheet(
            "QPushButton{background:#27ae60;color:white;font-weight:bold;"
            "border:none;border-radius:5px;padding:8px 20px;}"
            "QPushButton:hover{background:#229954;}"
            "QPushButton:disabled{background:#bdc3c7;}"
        )
        self._btn_confirm.setEnabled(False)
        self._btn_confirm.clicked.connect(self._confirm)
        btn_row.addWidget(self._btn_confirm)
        layout.addLayout(btn_row)

        # 默认选中第一个
        if self._versions:
            self._list.setCurrentRow(0)

    def _on_row_changed(self, row: int):
        if row < 0 or row >= len(self._versions):
            self._detail.clear()
            self._btn_confirm.setEnabled(False)
            return
        node = self._versions[row]
        title    = node.get("title", "无标题")
        setting  = node.get("setting", "")
        chars    = ", ".join(node.get("characters", []))
        events   = node.get("event_summaries", [])
        tone     = node.get("emotional_tone", "")
        opening  = node.get("opening_hook", "")
        hook     = node.get("episode_hook", "")

        events_html = "".join(f"<li>{e}</li>" for e in events) if events else "<li>—</li>"
        html = f"""
<h2 style='margin:0 0 8px 0; color:#1971c2;'>版本 {row+1} &nbsp;·&nbsp; {title}</h2>
<hr style='border:none; border-top:1px solid #dee2e6; margin:6px 0;'>

<p><b>🌍 环境 / 场景：</b><br>{setting or '—'}</p>
<p><b>👥 出场角色：</b><br>{chars or '—'}</p>

<p><b>📋 主要事件：</b></p>
<ul style='margin:2px 0 10px 0; padding-left:20px;'>
{events_html}
</ul>

<p><b>😊 情感基调：</b><br>{tone or '—'}</p>
<hr style='border:none; border-top:1px solid #dee2e6; margin:8px 0;'>
<p><b>🔗 开篇钩子（承接上一集）：</b><br>
<span style='color:#6c757d;'>{opening or '（第一章无前置）'}</span></p>
<p><b>🎣 结尾悬念钩子：</b><br>
<span style='color:#e67e22;'><b>{hook or '—'}</b></span></p>
"""
        self._detail.setHtml(html)
        self._btn_confirm.setEnabled(True)

    def _confirm(self):
        row = self._list.currentRow()
        if 0 <= row < len(self._versions):
            self._selected_node = dict(self._versions[row])
            self._selected_node["_version_idx"] = row
            self.accept()

    def selected_node(self):
        return self._selected_node


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
        self._ch1_versions = []        # 存储第一章的多个版本结果
        self._ch1_gen_remaining = 0    # 剩余待生成版本数
        self._ch1_gen_total = 0        # 总版本数
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
        gc_layout.setContentsMargins(8, 8, 8, 8)

        self._node_list = QListWidget()
        self._node_list.setViewMode(QListWidget.IconMode)
        self._node_list.setResizeMode(QListWidget.Adjust)
        self._node_list.setWrapping(True)
        self._node_list.setSpacing(6)
        self._node_list.setSelectionMode(QListWidget.SingleSelection)
        self._node_list.setWordWrap(False)
        self._node_list.setIconSize(QSize(0, 0))
        self._node_list.setGridSize(QSize(195, 60))
        self._node_list.setItemDelegate(NodeCardDelegate(self._node_list))
        self._node_list.setStyleSheet("""
            QListWidget { background: #f5f6fa; border: none; border-radius: 6px; padding: 4px; }
            QListWidget::item { background: transparent; }
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
        self._episodes_spin = _IntSpinBox()
        self._episodes_spin.setRange(1, 200)
        self._episodes_spin.setValue(self.project_data.total_episodes)
        self._episodes_spin.setMinimumWidth(100)
        self._episodes_spin.setFixedHeight(32)
        self._episodes_spin.setToolTip("整个剧本的总集数，每集对应一个 CPG 节点")
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


        config_layout.addStretch()
        config_inner.addLayout(config_layout)

        bl.addWidget(config_group)

        # 节点详情已改为双击卡片弹窗，不再需要内嵌面板

        # === 第一章开篇（优先生成） ===
        ch1_group, ch1_inner = self._make_collapsible("STEP 1 📖 第一章开篇", expanded=True)

        ch1_hint = QLabel(
            "💡 第一章必须优先完成：需交代清楚矛盾点、金手指、主角目标。"
            "系统会生成多个版本供你挑选最佳方案，确认后才可生成后续章节。"
        )
        ch1_hint.setWordWrap(True)
        ch1_hint.setStyleSheet("color:#7f8c8d; padding: 2px 0;")
        ch1_inner.addWidget(ch1_hint)

        # 钩子公式选择器（第一章）
        self._ch1_hook_selector = HookSelectorWidget(collapsed=True)
        ch1_inner.addWidget(self._ch1_hook_selector)

        ch1_row = QHBoxLayout()
        ch1_row.addWidget(QLabel("生成版本数:"))
        self._ch1_count_spin = _IntSpinBox()
        self._ch1_count_spin.setRange(1, 6)
        self._ch1_count_spin.setValue(3)
        self._ch1_count_spin.setMinimumWidth(100)
        self._ch1_count_spin.setFixedHeight(32)
        self._ch1_count_spin.setToolTip("为第一章生成多少个不同版本供选择")
        ch1_row.addWidget(self._ch1_count_spin)

        self._btn_ch1_gen = QPushButton("🎲 生成第一章多版本")
        self._btn_ch1_gen.setStyleSheet(
            "QPushButton{background:#e67e22;color:white;border:none;font-weight:bold;"
            "border-radius:4px;padding:6px 16px;}"
            "QPushButton:hover{background:#d35400;}"
            "QPushButton:disabled{background:#bdc3c7;}"
        )
        self._btn_ch1_gen.clicked.connect(self._on_ch1_generate)
        ch1_row.addWidget(self._btn_ch1_gen)

        self._ch1_progress_label = QLabel("")
        self._ch1_progress_label.setStyleSheet("color:#e67e22; font-weight:bold;")
        ch1_row.addWidget(self._ch1_progress_label)
        ch1_row.addStretch()
        ch1_inner.addLayout(ch1_row)

        # 确认状态行（生成完或已确认时显示）
        ch1_status_row = QHBoxLayout()
        self._ch1_status_label = QLabel("")
        self._ch1_status_label.setStyleSheet("color:#27ae60; font-weight:bold;")
        ch1_status_row.addWidget(self._ch1_status_label)

        self._btn_ch1_reselect = QPushButton("🔄 重新选择版本")
        self._btn_ch1_reselect.setStyleSheet(
            "QPushButton{background:#2980b9;color:white;border:none;"
            "border-radius:4px;padding:5px 14px;}"
            "QPushButton:hover{background:#2471a3;}"
        )
        self._btn_ch1_reselect.setVisible(False)
        self._btn_ch1_reselect.clicked.connect(self._on_ch1_reselect)
        ch1_status_row.addWidget(self._btn_ch1_reselect)
        ch1_status_row.addStretch()
        ch1_inner.addLayout(ch1_status_row)

        bl.addWidget(ch1_group)

        # === 分段生成（需完成第一章后解锁） ===
        self._seg_group, seg_inner = self._make_collapsible("STEP 2 🔄 分段生成", expanded=True)
        seg_row1 = QHBoxLayout()
        seg_row1.addWidget(QLabel("起始集:"))
        self._seg_start_combo = QComboBox()
        self._seg_start_combo.setMinimumWidth(160)
        self._seg_start_combo.setFixedHeight(32)
        seg_row1.addWidget(self._seg_start_combo)

        seg_row1.addWidget(QLabel("结束集:"))
        self._seg_end_combo = QComboBox()
        self._seg_end_combo.setMinimumWidth(160)
        self._seg_end_combo.setFixedHeight(32)
        seg_row1.addWidget(self._seg_end_combo)

        self._btn_seg_gen = QPushButton("🎲 生成本段")
        self._btn_seg_gen.setStyleSheet(
            "QPushButton{background:#3498db;color:white;border:none;"
            "border-radius:4px;padding:5px 12px;}"
            "QPushButton:hover{background:#2980b9;}"
            "QPushButton:disabled{background:#bdc3c7;}"
        )
        self._btn_seg_gen.clicked.connect(self._on_seg_generate)
        seg_row1.addWidget(self._btn_seg_gen)

        self._btn_seg_confirm = QPushButton("✅ 确认本段")
        self._btn_seg_confirm.setStyleSheet(
            "QPushButton{background:#27ae60;color:white;border:none;"
            "border-radius:4px;padding:5px 12px;}"
            "QPushButton:hover{background:#229954;}"
            "QPushButton:disabled{background:#bdc3c7;}"
        )
        self._btn_seg_confirm.clicked.connect(self._on_seg_confirm)
        seg_row1.addWidget(self._btn_seg_confirm)

        self._btn_seg_clear = QPushButton("🗑️ 清空未确认")
        self._btn_seg_clear.setStyleSheet(
            "QPushButton{background:#e74c3c;color:white;border:none;"
            "border-radius:4px;padding:5px 12px;}"
            "QPushButton:hover{background:#c0392b;}"
            "QPushButton:disabled{background:#bdc3c7;}"
        )
        self._btn_seg_clear.clicked.connect(self._on_seg_clear)
        seg_row1.addWidget(self._btn_seg_clear)
        seg_row1.addStretch()
        seg_inner.addLayout(seg_row1)

        # 钩子公式选择器（分段生成）
        self._seg_hook_selector = HookSelectorWidget(collapsed=True)
        self._seg_hook_selector.selectionChanged.connect(self._on_seg_hook_changed)
        seg_inner.addWidget(self._seg_hook_selector)

        self._seg_progress_label = QLabel("进度: 已确认 0/0 集")
        self._seg_progress_label.setStyleSheet("color:#7f8c8d;")
        seg_inner.addWidget(self._seg_progress_label)
        bl.addWidget(self._seg_group)

        # 初始化下拉框内容
        self._refresh_seg_combos()

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
        self._update_dynamic_max_tokens()
        self._update_seg_progress()

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
        self._update_dynamic_max_tokens()

        # 恢复第一章候选版本
        if self.project_data.ch1_versions and not self._ch1_versions:
            self._ch1_versions = list(self.project_data.ch1_versions)

        # 恢复钩子选择
        ch1_hooks = self.project_data.hook_selections.get("Ep1", [])
        if ch1_hooks:
            self._ch1_hook_selector.set_selected_ids(ch1_hooks)
        # 分段钩子：优先使用 _seg_default，否则取最近一次有记录的集的选择
        seg_hooks = self.project_data.hook_selections.get("_seg_default", [])
        if not seg_hooks:
            for ep_id in reversed(sorted(self.project_data.hook_selections.keys(),
                                           key=lambda x: self._parse_ep_num(x))):
                if ep_id not in ("Ep1", "_seg_default"):
                    seg_hooks = self.project_data.hook_selections[ep_id]
                    break
        if seg_hooks:
            self._seg_hook_selector.set_selected_ids(seg_hooks)

        # 刷新下拉框
        self._refresh_seg_combos()

        self._sync_ch1_state()

        if self.project_data.cpg_nodes:
            self._load_to_editor()
        else:
            self._update_seg_progress()
            self.status_message.emit("请先设置总集数和每集时长，然后生成第一章")

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
                ver_tag = f"v{active_v}"
            else:
                ver_tag = ""
            confirmed_eps = set(self.project_data.skeleton_confirmed_eps)
            check = "✅ " if nid in confirmed_eps else ""
            # 第一行：Ep号 + 版本号（粗体），第二行：章节标题（细体）
            line1 = f"{check}{nid}  {ver_tag}" if ver_tag else f"{check}{nid}"
            line2 = title if title else stage
            item = QListWidgetItem(line1)  # DisplayRole 用于 fallback
            item.setData(Qt.UserRole, nid)
            item.setData(NodeCardDelegate.LINE1_ROLE, line1)
            item.setData(NodeCardDelegate.LINE2_ROLE, line2)
            item.setToolTip(
                f"节点: {nid}\n阶段: {stage}\n标题: {title}\n"
                f"版本: v{node.get('active_version', 0)}\n"
                f"钩子: {node.get('episode_hook','')}"
            )
            # 统一将阶段颜色设为左侧饰条的颜色，现代清爽风格
            sid = node.get("hauge_stage_id", 1)
            # 现代莫兰迪/强调色系: 机会(青) 变点(黄) 无路(红) 挫折(粉) 高潮(紫) 终局(蓝)
            colors = {1:"#00cec9", 2:"#fdcb6e", 3:"#d63031", 4:"#e84393", 5:"#6c5ce7", 6:"#0984e3"}
            item.setBackground(QColor(colors.get(sid, "#b2bec3")))
            self._node_list.addItem(item)
        self._update_seg_progress()

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
        # 如果已有分段确认的节点，提示覆盖
        if self.project_data.skeleton_confirmed_eps:
            reply = QMessageBox.question(
                self, "覆盖确认",
                f"当前已有 {len(self.project_data.skeleton_confirmed_eps)} 集已确认骨架。\n"
                "全量重新生成将覆盖所有内容。确定继续？",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply == QMessageBox.No:
                return
            self.project_data.skeleton_confirmed_eps.clear()
            app_logger.warning("骨架-全量重生成", "用户选择全量重新生成，已清空分段确认数据")
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
                    "opening_hook":    n.get("opening_hook", ""),
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
        # 全量生成完成，自动标记全部节点为已确认
        self.project_data.skeleton_confirmed_eps = [n.get("node_id") for n in nodes]
        self._load_to_editor()
        self._update_seg_progress()
        self._sync_ch1_state()
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
        self._btn_ch1_gen.setEnabled(not busy)
        self._btn_seg_gen.setEnabled(not busy)
        self._btn_seg_confirm.setEnabled(not busy)
        self._btn_seg_clear.setEnabled(not busy)
        self._btn_regen.setText("处理中..." if busy else "重新生成骨架")
        self._btn_seg_gen.setText("生成中..." if busy else "🎲 生成本段")
        self._btn_ch1_gen.setText("生成中..." if busy else "🎲 生成第一章多版本")

    def _on_error(self, msg: str):
        self._set_busy(False)
        self._hide_loading()
        QMessageBox.critical(self, "AI 调用失败", msg)
        self.status_message.emit("错误: " + msg)

    # ------------------------------------------------------------------ #
    # 分段生成 — 下拉框管理
    # ------------------------------------------------------------------ #
    def _refresh_seg_combos(self):
        """刷新起始集/结束集下拉框，标注已生成状态"""
        total = self._episodes_spin.value()
        existing_ids = {n.get("node_id", "") for n in self.project_data.cpg_nodes}

        # 记住当前选择
        old_start = self._get_seg_start_value()
        old_end = self._get_seg_end_value()

        self._seg_start_combo.blockSignals(True)
        self._seg_end_combo.blockSignals(True)
        self._seg_start_combo.clear()
        self._seg_end_combo.clear()

        for i in range(1, total + 1):
            ep_id = f"Ep{i}"
            if ep_id in existing_ids:
                label = f"Ep{i}  ✅ 已生成"
            else:
                label = f"Ep{i}"
            self._seg_start_combo.addItem(label, i)
            self._seg_end_combo.addItem(label, i)

        # 恢复选择
        if old_start and old_start <= total:
            self._seg_start_combo.setCurrentIndex(old_start - 1)
        elif total >= 2:
            self._seg_start_combo.setCurrentIndex(1)  # 默认第2集
        if old_end and old_end <= total:
            self._seg_end_combo.setCurrentIndex(old_end - 1)
        elif total >= 5:
            self._seg_end_combo.setCurrentIndex(4)  # 默认第5集
        else:
            self._seg_end_combo.setCurrentIndex(total - 1)

        self._seg_start_combo.blockSignals(False)
        self._seg_end_combo.blockSignals(False)

    def _get_seg_start_value(self) -> int:
        """从下拉框获取起始集编号"""
        idx = self._seg_start_combo.currentIndex()
        if idx < 0:
            return 0
        return self._seg_start_combo.itemData(idx) or 0

    def _get_seg_end_value(self) -> int:
        """从下拉框获取结束集编号"""
        idx = self._seg_end_combo.currentIndex()
        if idx < 0:
            return 0
        return self._seg_end_combo.itemData(idx) or 0

    def _set_seg_combo_values(self, start_val: int, end_val: int):
        """设置起始/结束下拉框的值"""
        total = self._seg_start_combo.count()
        if 1 <= start_val <= total:
            self._seg_start_combo.setCurrentIndex(start_val - 1)
        if 1 <= end_val <= total:
            self._seg_end_combo.setCurrentIndex(end_val - 1)

    def _on_seg_hook_changed(self, selected_ids):
        """分段钩子选择变化时立即持久化"""
        if selected_ids:
            self.project_data.hook_selections["_seg_default"] = list(selected_ids)

    # ------------------------------------------------------------------ #
    # 分段生成 — 进度
    # ------------------------------------------------------------------ #
    def _update_seg_progress(self):
        """刷新分段确认进度标签 + 下拉框状态"""
        confirmed = len(self.project_data.skeleton_confirmed_eps)
        total = self._episodes_spin.value()
        self._seg_progress_label.setText(f"进度: 已确认 {confirmed}/{total} 集")
        self._refresh_seg_combos()

    def _rebuild_sequential_edges(self):
        """
        自动为所有现有节点建立顺序因果边 (Ep1→Ep2→Ep3→...)。
        只补充缺失的边，不会删除用户手动添加的非顺序边。
        """
        # 收集所有节点 ID 并排序
        node_ids = [n.get("node_id", "") for n in self.project_data.cpg_nodes]
        node_ids.sort(key=lambda x: self._parse_ep_num(x))

        if len(node_ids) < 2:
            return

        # 构建现有边的集合用于快速查找
        existing = {(e["from_node"], e["to_node"]) for e in self.project_data.cpg_edges}

        # 对每对相邻节点补充顺序边
        added = 0
        for i in range(len(node_ids) - 1):
            from_id = node_ids[i]
            to_id   = node_ids[i + 1]
            if (from_id, to_id) not in existing:
                self.project_data.cpg_edges.append({
                    "from_node": from_id,
                    "to_node":   to_id,
                    "relation":  "causal",
                })
                added += 1

        if added:
            app_logger.info("骨架-自动连接", f"自动建立了 {added} 条顺序因果边")

    def _on_seg_generate(self):
        """分段生成指定范围的骨架节点（逐集串行，每集用完整上下文）"""
        if not self.project_data.sparkle:
            QMessageBox.warning(self, "提示", "请先完成创世阶段！")
            return

        if not self._seg_hook_selector.selected_ids():
            QMessageBox.warning(self, "提示", "请至少选择一个钩子公式！")
            return

        start_ep = self._get_seg_start_value()
        end_ep = self._get_seg_end_value()
        if start_ep < 1 or end_ep < 1:
            QMessageBox.warning(self, "提示", "请先选择起始集和结束集！")
            return
        if start_ep > end_ep:
            QMessageBox.warning(self, "提示", "起始集不能大于结束集！")
            return

        total = self._episodes_spin.value()
        if end_ep > total:
            QMessageBox.warning(self, "提示", f"结束集不能超过总集数 {total}！")
            return

        # 跳章检测：检查起始集之前是否有未生成的集
        existing_ids = {n.get("node_id", "") for n in self.project_data.cpg_nodes}
        missing_before = [i for i in range(1, start_ep) if f"Ep{i}" not in existing_ids]
        if missing_before:
            missing_str = ", ".join(f"Ep{i}" for i in missing_before[:10])
            if len(missing_before) > 10:
                missing_str += f" 等共{len(missing_before)}集"
            reply = QMessageBox.warning(
                self, "⚠️ 跳章警告",
                f"检测到起始集（Ep{start_ep}）之前有以下章节尚未生成：\n\n"
                f"{missing_str}\n\n"
                f"跳过这些章节可能导致剧情断裂、AI 缺少上下文。\n"
                f"建议先生成缺失的章节。\n\n确定要跳过吗？",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply == QMessageBox.No:
                return

        # 检查范围内是否已存在节点（不管是否已确认）
        existing_ids = {n.get("node_id", "") for n in self.project_data.cpg_nodes}
        overlap_ids = [f"Ep{i}" for i in range(start_ep, end_ep + 1) if f"Ep{i}" in existing_ids]

        confirmed_set = set(self.project_data.skeleton_confirmed_eps)
        overlap_confirmed = [eid for eid in overlap_ids if eid in confirmed_set]

        if overlap_ids:
            msg = f"第 {start_ep}~{end_ep} 集中已存在 {len(overlap_ids)} 个节点"
            if overlap_confirmed:
                msg += f"（其中 {len(overlap_confirmed)} 个已确认）"
            msg += "。\n\n重新生成将在这些节点上创建新版本（原有版本不会丢失）。\n确定继续吗？"
            reply = QMessageBox.question(
                self, "重复范围检测",
                msg,
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply == QMessageBox.No:
                return
            # 移除已确认状态（允许重新生成）
            for nid in overlap_confirmed:
                self.project_data.skeleton_confirmed_eps.remove(nid)

        # 初始化逐集生成队列
        self._seg_queue = list(range(start_ep, end_ep + 1))
        self._seg_total_count = len(self._seg_queue)
        self._seg_generated_count = 0

        self._set_busy(True)
        self._show_loading()
        self.status_message.emit(
            f"正在逐集生成第 {start_ep}~{end_ep} 集骨架（共{self._seg_total_count}集，质量优先模式）..."
        )
        self._launch_next_seg_episode()

    def _launch_next_seg_episode(self):
        """启动下一集骨架的生成"""
        if not self._seg_queue:
            # 全部完成
            self._set_busy(False)
            self._hide_loading()
            self._rebuild_sequential_edges()
            self._load_to_editor()
            start_ep = self._get_seg_start_value()
            end_ep = self._get_seg_end_value()
            self.status_message.emit(
                f"✅ 分段骨架全部完成：第 {start_ep}~{end_ep} 集（{self._seg_generated_count} 个节点）"
            )
            return

        current_ep = self._seg_queue[0]
        progress_num = self._seg_generated_count + 1
        self._ch1_progress_label.setText("")  # 清掉上一次的提示
        self.status_message.emit(
            f"正在生成第 {current_ep} 集（{progress_num}/{self._seg_total_count}）..."
        )

        total = self._episodes_spin.value()

        # 收集所有已存在的前序节点作为上下文（不再限定"已确认"）
        context_nodes = []
        for n in sorted(self.project_data.cpg_nodes,
                        key=lambda x: self._parse_ep_num(x.get("node_id", ""))):
            ep_num = self._parse_ep_num(n.get("node_id", ""))
            if ep_num and ep_num[0] < current_ep:
                context_nodes.append(n)

        from env import DRAMA_STYLE_CONFIG
        from services.genre_manager import genre_manager
        style_key = self.project_data.drama_style or "short_drama"
        style_cfg = DRAMA_STYLE_CONFIG.get(style_key, {})
        genre_key = getattr(self.project_data, 'story_genre', 'custom')
        genre_cfg = genre_manager.get(genre_key)
        combined_block = style_cfg.get("skeleton_style_block", "")
        genre_skel = genre_cfg.get("skeleton_block", "")
        if genre_skel:
            combined_block = (combined_block + "\n\n" + genre_skel).strip()

        # 钩子分配：顺序循环
        all_hook_ids = self._seg_hook_selector.selected_ids()
        if all_hook_ids:
            pick_id = all_hook_ids[self._seg_generated_count % len(all_hook_ids)]
            hook_ids_for_ep = [pick_id]
        else:
            hook_ids_for_ep = []

        self._seg_worker = SegmentSkeletonWorker(
            sparkle=self.project_data.sparkle,
            world_variables=self.project_data.world_variables,
            finale_condition=self.project_data.finale_condition,
            characters=self.project_data.characters,
            ai_params=self._ai_settings.get_all_settings(),
            start_ep=current_ep,
            end_ep=current_ep,    # 只生成 1 集
            total_episodes=total,
            episode_duration=self._duration_range.durationString(),
            confirmed_nodes=context_nodes,
            drama_style_block=combined_block,
            hook_ids=hook_ids_for_ep,
        )
        self._seg_worker.progress.connect(self.status_message)
        self._seg_worker.finished.connect(self._on_seg_ep_done)
        self._seg_worker.error.connect(self._on_seg_ep_error)
        self._seg_worker.start()

    def _on_seg_ep_done(self, result: dict):
        """单集生成完成回调"""
        current_ep = self._seg_queue.pop(0)
        self._seg_generated_count += 1

        new_nodes = result.get("nodes", [])
        if not new_nodes:
            app_logger.warning("骨架-分段生成", f"第 {current_ep} 集 AI 未返回有效节点")
        else:
            from models.project_state import add_version as _add_version, apply_snapshot, make_node_snapshot

            existing_map = {n.get("node_id", ""): n for n in self.project_data.cpg_nodes}

            for new_node in new_nodes:
                new_node.setdefault("status", "pending")
                new_node.setdefault("opening_hook", "")
                nid = new_node.get("node_id", "")

                if nid in existing_map:
                    old_node = existing_map[nid]
                    snap = make_node_snapshot(new_node)
                    apply_snapshot(old_node, snap)
                    _add_version(old_node, "ai_generate", "分段重新生成")
                else:
                    _add_version(new_node, "ai_generate", "分段生成")
                    self.project_data.cpg_nodes.append(new_node)

            self.project_data.cpg_nodes.sort(
                key=lambda x: self._parse_ep_num(x.get("node_id", ""))
            )
            self.project_data.push_history("segment_skeleton")

        # 实时刷新卡片列表
        self._load_to_editor()

        app_logger.log_ai_result(
            module="骨架-分段生成",
            action=f"第 {current_ep} 集骨架完成",
            result_summary=f"成功生成 {len(new_nodes)} 个节点",
            result_detail="",
        )

        # 继续生成下一集
        self._launch_next_seg_episode()

    def _on_seg_ep_error(self, msg: str):
        """单集生成失败回调"""
        current_ep = self._seg_queue.pop(0)
        self._seg_generated_count += 1
        app_logger.error("骨架-分段生成", f"第 {current_ep} 集生成失败: {msg}")
        self.status_message.emit(f"⚠️ 第 {current_ep} 集生成失败，跳过继续...")
        # 继续生成下一集
        self._launch_next_seg_episode()


    def _on_seg_confirm(self):
        """确认当前范围内的节点"""
        start_ep = self._get_seg_start_value()
        end_ep = self._get_seg_end_value()

        # 找到范围内存在的节点
        confirmed_count = 0
        for n in self.project_data.cpg_nodes:
            nid = n.get("node_id", "")
            ep_nums = self._parse_ep_num(nid)
            if ep_nums and start_ep <= ep_nums[0] <= end_ep:
                if nid not in self.project_data.skeleton_confirmed_eps:
                    self.project_data.skeleton_confirmed_eps.append(nid)
                    confirmed_count += 1

        if confirmed_count == 0:
            QMessageBox.information(self, "提示", "该范围内没有可确认的新节点。")
            return

        # 自动推进下拉框
        total = self._episodes_spin.value()
        new_start = end_ep + 1
        if new_start <= total:
            self._set_seg_combo_values(new_start, min(new_start + 4, total))

        # 记录分段的钩子选择
        seg_hooks = self._seg_hook_selector.selected_ids()
        if seg_hooks:
            for ep_num in range(start_ep, end_ep + 1):
                ep_id = f"Ep{ep_num}"
                self.project_data.hook_selections[ep_id] = seg_hooks

        self.project_data.push_history("segment_confirm")
        self._load_to_editor()
        self._sync_ch1_state()

        app_logger.success(
            "骨架-分段确认",
            f"确认第 {start_ep}~{end_ep} 集（{confirmed_count} 个节点）",
            f"累计已确认: {len(self.project_data.skeleton_confirmed_eps)} 集",
        )
        self.status_message.emit(
            f"已确认第 {start_ep}~{end_ep} 集（{confirmed_count} 个节点）"
        )

    def _on_seg_clear(self):
        """清空所有未确认的节点"""
        confirmed_set = set(self.project_data.skeleton_confirmed_eps)
        before_count = len(self.project_data.cpg_nodes)
        self.project_data.cpg_nodes = [
            n for n in self.project_data.cpg_nodes
            if n.get("node_id", "") in confirmed_set
        ]
        removed = before_count - len(self.project_data.cpg_nodes)

        if removed == 0:
            QMessageBox.information(self, "提示", "没有未确认的节点需要清空。")
            return

        self._load_to_editor()
        app_logger.info("骨架-清空未确认", f"清空了 {removed} 个未确认节点")
        self.status_message.emit(f"已清空 {removed} 个未确认节点")

    # ------------------------------------------------------------------ #
    # 第一章优先生成
    # ------------------------------------------------------------------ #
    def _is_ch1_confirmed(self) -> bool:
        """检查第一章是否已经被确认"""
        return "Ep1" in set(self.project_data.skeleton_confirmed_eps)

    def _sync_ch1_state(self):
        """根据第一章确认状态同步UI"""
        ch1_done = self._is_ch1_confirmed()

        if ch1_done:
            self._ch1_status_label.setText("✅ 第一章已确认")
            self._btn_ch1_gen.setText("🔄 重新生成第一章")
            self._btn_ch1_reselect.setVisible(bool(self._ch1_versions))
            # 解锁分段生成
            self._seg_group.setTitle("STEP 2 🔄 分段生成")
            self._btn_seg_gen.setEnabled(True)
            self._btn_seg_confirm.setEnabled(True)
            self._btn_seg_clear.setEnabled(True)
        else:
            self._ch1_status_label.setText("")
            self._btn_ch1_gen.setText("🎲 生成第一章多版本")
            self._btn_ch1_reselect.setVisible(bool(self._ch1_versions))
            # 锁定分段生成
            self._seg_group.setTitle("STEP 2 🔄 分段生成（需先完成第一章）")
            self._btn_seg_gen.setEnabled(False)
            self._btn_seg_confirm.setEnabled(False)
            self._btn_seg_clear.setEnabled(False)

    def _on_ch1_generate(self):
        """启动第一章多版本生成"""
        if not self.project_data.sparkle:
            QMessageBox.warning(self, "提示", "请先完成创世阶段！")
            return
            
        if not self._ch1_hook_selector.selected_ids():
            QMessageBox.warning(self, "提示", "请至少选择一个钩子公式！")
            return

        # 如果已确认，提示是否重新生成
        if self._is_ch1_confirmed():
            reply = QMessageBox.question(
                self, "重新生成",
                "第一章已确认。重新生成将清除当前第一章，确定继续？",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply == QMessageBox.No:
                return
            # 清除 Ep1 确认状态和节点
            if "Ep1" in self.project_data.skeleton_confirmed_eps:
                self.project_data.skeleton_confirmed_eps.remove("Ep1")
            self.project_data.cpg_nodes = [
                n for n in self.project_data.cpg_nodes
                if n.get("node_id") != "Ep1"
            ]

        count = self._ch1_count_spin.value()
        self._ch1_versions = []
        self._ch1_gen_total = count
        self._ch1_gen_remaining = count
        self._ch1_status_label.setText("")
        self._btn_ch1_reselect.setVisible(False)

        self._set_busy(True)
        self._show_loading()
        self._ch1_progress_label.setText(f"正在生成第 1/{count} 个版本…")
        self._launch_next_ch1_version()

    def _launch_next_ch1_version(self):
        """启动下一个第一章版本的生成"""
        from env import DRAMA_STYLE_CONFIG
        from services.genre_manager import genre_manager
        style_key = self.project_data.drama_style or "short_drama"
        style_cfg = DRAMA_STYLE_CONFIG.get(style_key, {})
        genre_key = getattr(self.project_data, 'story_genre', 'custom')
        genre_cfg = genre_manager.get(genre_key)
        combined_block = style_cfg.get("skeleton_style_block", "")
        genre_skel = genre_cfg.get("skeleton_block", "")
        if genre_skel:
            combined_block = (combined_block + "\n\n" + genre_skel).strip()

        total = self._episodes_spin.value()
        # 使用稍高温度来增加版本多样性
        ai_params = self._ai_settings.get_all_settings()
        ai_params["temperature"] = max(ai_params.get("temperature", 0.5), 0.7)

        # 计算本次版本是第几个（0-based）
        version_index = self._ch1_gen_total - self._ch1_gen_remaining  # 0-based

        # 根据版本数 vs 钩子数决定顺序还是随机
        all_hook_ids = self._ch1_hook_selector.selected_ids()
        if self._ch1_gen_total >= len(all_hook_ids):
            # 版本数 >= 钩子数：顺序循环分配，每个版本用一个确定的钩子
            pick_id = all_hook_ids[version_index % len(all_hook_ids)]
        else:
            # 版本数 < 钩子数：随机抽一个
            import random as _rnd
            pick_id = _rnd.choice(all_hook_ids)

        self._ch1_worker = SegmentSkeletonWorker(
            sparkle=self.project_data.sparkle,
            world_variables=self.project_data.world_variables,
            finale_condition=self.project_data.finale_condition,
            characters=self.project_data.characters,
            ai_params=ai_params,
            start_ep=1,
            end_ep=1,
            total_episodes=total,
            episode_duration=self._duration_range.durationString(),
            confirmed_nodes=[],
            drama_style_block=combined_block,
            hook_ids=[pick_id],
        )
        self._ch1_worker.progress.connect(self.status_message)
        self._ch1_worker.finished.connect(self._on_ch1_version_done)
        self._ch1_worker.error.connect(self._on_ch1_version_error)
        self._ch1_worker.start()

    def _on_ch1_version_done(self, result: dict):
        """单个版本生成完成"""
        nodes = result.get("nodes", [])
        if nodes:
            # 取第一个节点（start=1, end=1 应该只生成一个）
            node = nodes[0]
            node.setdefault("opening_hook", "")
            self._ch1_versions.append(node)

        current = self._ch1_gen_total - self._ch1_gen_remaining + 1
        self._ch1_gen_remaining -= 1

        if self._ch1_gen_remaining > 0:
            next_num = current + 1
            self._ch1_progress_label.setText(
                f"正在生成第 {next_num}/{self._ch1_gen_total} 个版本…"
            )
            self._launch_next_ch1_version()
        else:
            # 全部生成完毕
            self._set_busy(False)
            self._hide_loading()
            self._ch1_progress_label.setText(
                f"✅ 已生成 {len(self._ch1_versions)} 个版本"
            )
            # 持久化第一章候选版本
            self.project_data.ch1_versions = list(self._ch1_versions)
            self._populate_ch1_versions()

    def _on_ch1_version_error(self, msg: str):
        """版本生成失败"""
        self._ch1_gen_remaining -= 1
        current = self._ch1_gen_total - self._ch1_gen_remaining

        if self._ch1_gen_remaining > 0:
            self._ch1_progress_label.setText(
                f"版本{current}失败，继续生成下一个…"
            )
            self._launch_next_ch1_version()
        else:
            self._set_busy(False)
            self._hide_loading()
            if self._ch1_versions:
                self._ch1_progress_label.setText(
                    f"⚠️ 部分版本生成失败，已获得 {len(self._ch1_versions)} 个版本"
                )
                # 持久化第一章候选版本
                self.project_data.ch1_versions = list(self._ch1_versions)
                self._populate_ch1_versions()
            else:
                self._ch1_progress_label.setText("❌ 所有版本生成失败")
                QMessageBox.critical(self, "生成失败", f"第一章全部版本生成失败：{msg}")

    def _populate_ch1_versions(self):
        """打开版本选择对话框，让用户选择第一章方案。"""
        if not self._ch1_versions:
            return
        dlg = Ch1VersionDialog(self._ch1_versions, parent=self)
        if dlg.exec() == QDialog.Accepted:
            node = dlg.selected_node()
            if node:
                self._apply_ch1_node(node)

    def _on_ch1_reselect(self):
        """已生成版本时，重新打开选择对话框。"""
        if not self._ch1_versions:
            QMessageBox.information(self, "提示", "请先生成第一章版本。")
            return
        dlg = Ch1VersionDialog(self._ch1_versions, parent=self)
        if dlg.exec() == QDialog.Accepted:
            node = dlg.selected_node()
            if node:
                self._apply_ch1_node(node)

    def _apply_ch1_node(self, node: dict):
        """将选中的节点应用为第一章，更新数据和UI。"""
        idx = node.get("_version_idx", 0)
        selected_node = {k: v for k, v in node.items() if k != "_version_idx"}
        selected_node.setdefault("status", "pending")
        selected_node["node_id"] = "Ep1"

        from models.project_state import add_version as _add_version
        _add_version(selected_node, "ai_generate", f"第一章 v{idx+1}")

        self.project_data.cpg_nodes = [
            n for n in self.project_data.cpg_nodes
            if n.get("node_id") != "Ep1"
        ]
        self.project_data.cpg_nodes.insert(0, selected_node)
        self.project_data.cpg_nodes.sort(
            key=lambda x: self._parse_ep_num(x.get("node_id", ""))
        )

        if "Ep1" not in self.project_data.skeleton_confirmed_eps:
            self.project_data.skeleton_confirmed_eps.append("Ep1")

        # 记录第一章的钩子选择
        ch1_hooks = self._ch1_hook_selector.selected_ids()
        if ch1_hooks:
            self.project_data.hook_selections["Ep1"] = ch1_hooks

        self.project_data.push_history("ch1_confirm")
        self._rebuild_sequential_edges()
        self._load_to_editor()
        self._sync_ch1_state()

        self._ch1_progress_label.setText("")
        total = self._episodes_spin.value()
        self._refresh_seg_combos()
        self._set_seg_combo_values(2, min(5, total))

        app_logger.success(
            "骨架-第一章确认",
            f"确认第一章版本 {idx+1}/{len(self._ch1_versions)}",
            f"标题: {selected_node.get('title', '')}, 钩子: {selected_node.get('episode_hook', '')}",
        )
        self.status_message.emit(
            f"第一章已确认（版本{idx+1}），可以开始生成后续章节了！"
        )

    def _on_ch1_confirm(self):
        """兼容旧调用（已不再使用，保留防止引用报错）。"""
        pass

