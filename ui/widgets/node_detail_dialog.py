# ============================================================
# ui/widgets/node_detail_dialog.py
# 骨架节点详情与 AI 交互编辑对话框
# 支持: 手动编辑 / Chat 对话 / Quick-Regen / BVSR 重写
# 版本管理: 每次修改自动创建新版本，版本下拉可切换
# ============================================================

import json
import copy
from datetime import datetime

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QSplitter, QLabel,
    QPushButton, QLineEdit, QTextEdit, QTextBrowser, QComboBox,
    QGroupBox, QFormLayout, QCheckBox, QRadioButton, QButtonGroup,
    QWidget, QStackedWidget, QScrollArea, QMessageBox, QListWidget,
    QListWidgetItem, QSizePolicy,
)
from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QColor, QFont

from models.project_state import (
    make_node_snapshot, apply_snapshot, add_version, get_active_version_snapshot,
    update_version, set_active_version,
)


DRAMA_DIRECTION_OPTIONS = [
    ("aggressive",  "🔥 更激进 — 冲突升级"),
    ("complex",     "🧩 更复杂 — 多线交织"),
    ("romantic",    "💕 更温情 — 关系深化"),
    ("suspense",    "🔍 更悬疑 — 伏笔加重"),
    ("dark",        "🌑 更黑暗 — 代价升级"),
    ("fast",        "⚡ 更紧凑 — 节奏加快"),
]

STRUCTURE_OPTIONS = [
    ("twist",       "增加反转点"),
    ("hook",        "强化结尾钩子"),
    ("inner",       "增加角色内心冲突"),
    ("focus",       "削减支线、聚焦主线"),
]


# ============================================================
# 钩子重写对话框
# ============================================================
class HookRewriteDialog(QDialog):
    """
    钩子重写子对话框：选择钩子类型 → AI 生成预览 → 采用或重新生成。
    """
    def __init__(self, node, project_data, parent=None):
        super().__init__(parent)
        self._node = node
        self._pd = project_data
        self._worker = None
        self._new_hook = ""    # 最终采用的钩子文本
        self._next_node = self._find_next_node()

        nid = node.get("node_id", "")
        self.setWindowTitle(f"🎣 重写结尾钩子 — {nid}")
        self.setMinimumSize(680, 520)
        self.resize(720, 560)
        self.setWindowFlags(self.windowFlags() | Qt.WindowMaximizeButtonHint)
        self._setup_ui()

    def _find_next_node(self):
        """查找下一集节点"""
        import re
        nid = self._node.get("node_id", "")
        nums = re.findall(r'\d+', nid)
        if not nums:
            return None
        next_id = f"Ep{int(nums[0]) + 1}"
        for n in self._pd.cpg_nodes:
            if n.get("node_id") == next_id:
                return n
        return None

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # 顶部：当前钩子展示
        nid = self._node.get("node_id", "")
        cur_hook = self._node.get("episode_hook", "")
        if cur_hook:
            cur_group = QGroupBox(f"当前钩子（{nid}）")
            cur_lay = QVBoxLayout(cur_group)
            cur_text = QTextBrowser()
            cur_text.setPlainText(cur_hook)
            cur_text.setMaximumHeight(80)
            cur_lay.addWidget(cur_text)
            layout.addWidget(cur_group)

        # 钩子类型选择（复用 HookSelectorWidget）
        from ui.widgets.hook_selector_widget import HookSelectorWidget
        hook_row = QHBoxLayout()
        hook_row.addWidget(QLabel("🎯 钩子类型选择:"))
        self._hook_selector = HookSelectorWidget()
        hook_row.addWidget(self._hook_selector, 1)
        layout.addLayout(hook_row)

        # 参考后续章节
        self._cb_ref_next = QCheckBox("参考后续章节（保持上下文连贯）")
        self._cb_ref_next.setChecked(True)
        if not self._next_node:
            self._cb_ref_next.setChecked(False)
            self._cb_ref_next.setEnabled(False)
            self._cb_ref_next.setToolTip("当前是最后一集，无后续章节可参考")
        else:
            next_id = self._next_node.get("node_id", "")
            self._cb_ref_next.setToolTip(
                f"勾选后，AI 会参考 {next_id} 的开头内容，确保新钩子能自然衔接"
            )
        layout.addWidget(self._cb_ref_next)

        # 生成按钮
        btn_gen = QPushButton("🎲 生成新钩子")
        btn_gen.setMinimumHeight(36)
        btn_gen.setStyleSheet(
            "QPushButton{background:#e17055;color:white;border-radius:6px;font-weight:bold;font-size:14px;}"
            "QPushButton:hover{background:#d63031;}"
        )
        btn_gen.clicked.connect(self._on_generate)
        self._btn_gen = btn_gen
        layout.addWidget(btn_gen)

        # 预览区
        preview_group = QGroupBox("✨ 新钩子预览")
        preview_lay = QVBoxLayout(preview_group)
        self._preview_text = QTextBrowser()
        self._preview_text.setMinimumHeight(120)
        self._preview_text.setPlaceholderText("点击「生成新钩子」后，新钩子将显示在这里...")
        from services.theme_manager import theme_manager as _tm
        _, _fs = _tm.get_current_font()
        self._preview_text.setStyleSheet(
            f"QTextBrowser{{ background:#fffde7; border:1px solid #f0e68c;"
            f" border-radius:6px; padding:10px; font-size:{_fs}pt; }}"
        )
        preview_lay.addWidget(self._preview_text)
        layout.addWidget(preview_group, 1)

        # 底部按钮
        btn_row = QHBoxLayout()
        self._btn_adopt = QPushButton("✅ 采用此钩子")
        self._btn_adopt.setEnabled(False)
        self._btn_adopt.setMinimumHeight(34)
        self._btn_adopt.setStyleSheet(
            "QPushButton{background:#00b894;color:white;border-radius:6px;font-weight:bold;}"
            "QPushButton:hover{background:#00a381;}"
            "QPushButton:disabled{background:#b2bec3;}"
        )
        self._btn_adopt.clicked.connect(self._on_adopt)
        btn_row.addWidget(self._btn_adopt)

        btn_regen = QPushButton("🔄 重新生成")
        btn_regen.setMinimumHeight(34)
        btn_regen.clicked.connect(self._on_generate)
        btn_row.addWidget(btn_regen)

        btn_cancel = QPushButton("取消")
        btn_cancel.setMinimumHeight(34)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)

        layout.addLayout(btn_row)

    def _on_generate(self):
        """启动 AI 生成"""
        hook_ids = self._hook_selector.selected_ids()
        if not hook_ids:
            QMessageBox.warning(self, "提示", "请至少选择一个钩子类型！")
            return

        self._btn_gen.setEnabled(False)
        self._btn_gen.setText("生成中...")
        self._btn_adopt.setEnabled(False)
        self._preview_text.setPlainText("正在生成，请稍候...")

        # 读取当前节点信息
        from models.project_state import get_active_version_snapshot
        snap = get_active_version_snapshot(self._node)
        events = snap.get("event_summaries", [])
        setting = snap.get("setting", "")
        chars = snap.get("characters", [])
        tone = snap.get("emotional_tone", "")

        # 下一集信息
        next_id = ""
        next_opening = ""
        next_events = []
        if self._cb_ref_next.isChecked() and self._next_node:
            next_snap = get_active_version_snapshot(self._next_node)
            next_id = self._next_node.get("node_id", "")
            next_opening = next_snap.get("opening_hook", "")
            next_events = next_snap.get("event_summaries", [])

        from services.worker import HookRewriteWorker
        self._worker = HookRewriteWorker(
            node_id=self._node.get("node_id", ""),
            event_summaries=events,
            setting=setting,
            characters=chars,
            emotional_tone=tone,
            hook_ids=hook_ids,
            ai_params={"temperature": 0.7, "max_tokens": 2048},
            next_node_id=next_id,
            next_opening_hook=next_opening,
            next_events=next_events,
        )
        self._worker.finished.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_done(self, result):
        self._btn_gen.setEnabled(True)
        self._btn_gen.setText("🎲 生成新钩子")
        hook_text = result.get("episode_hook", "")
        if hook_text:
            self._new_hook = hook_text
            self._preview_text.setPlainText(hook_text)
            self._btn_adopt.setEnabled(True)
        else:
            self._preview_text.setPlainText("⚠️ AI 未返回有效钩子，请重新生成。")

    def _on_error(self, msg):
        self._btn_gen.setEnabled(True)
        self._btn_gen.setText("🎲 生成新钩子")
        self._preview_text.setPlainText(f"❌ 生成失败: {msg}")

    def _on_adopt(self):
        """采用当前钩子并关闭"""
        self.accept()

    def adopted_hook(self) -> str:
        """返回被采用的钩子文本"""
        return self._new_hook


class NodeDetailDialog(QDialog):
    """
    骨架节点详情 + AI 交互编辑对话框。

    左侧: 当前版本内容（所有字段可编辑）+ 版本下拉
    右侧: AI 辅助面板 (Chat / Quick-Regen / BVSR 重写)
    底部: 因果连接编辑 + 操作按钮 (保存/拆分/合并/删除)
    """

    # action 码: 'saved' | 'deleted' | 'split' | 'id_changed:EpX'
    def __init__(self, node: dict, project_data, parent=None):
        super().__init__(parent)
        self._node = node          # 直接引用 project_data.cpg_nodes 中的 dict
        self._pd   = project_data
        self._worker = None
        self.action  = None        # 调用方检查此值

        nid   = node.get("node_id", "")
        title = node.get("title", "")
        self.setWindowTitle(f"节点详情 — {nid}  {title}")
        self.setMinimumSize(1280, 800)
        self.resize(1300, 840)
        self.setWindowFlags(self.windowFlags() | Qt.WindowMaximizeButtonHint)
        self._setup_ui()
        self._load_node_to_form(get_active_version_snapshot(node))

    # ------------------------------------------------------------------ #
    # UI 构建
    # ------------------------------------------------------------------ #
    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(6)

        # ---- 顶部: 标题 + 版本下拉 ----
        top_row = QHBoxLayout()
        nid = self._node.get("node_id", "")
        stage = self._node.get("hauge_stage_name", "")
        top_row.addWidget(QLabel(f"<b>{nid}</b> — {stage}"))
        top_row.addStretch()
        top_row.addWidget(QLabel("版本:"))
        self._ver_combo = QComboBox()
        self._ver_combo.setMinimumWidth(240)
        self._ver_combo.currentIndexChanged.connect(self._on_version_switch)
        top_row.addWidget(self._ver_combo)
        root.addLayout(top_row)
        self._refresh_version_combo()

        # ---- 中部: 左右分栏 ----
        splitter = QSplitter(Qt.Horizontal)

        # ---- 左侧: 内容编辑 ----
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 4, 0)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        self._f_title   = QLineEdit()
        self._f_setting = QTextEdit()
        self._f_setting.setFixedHeight(65)
        self._f_chars   = QTextEdit()
        self._f_chars.setFixedHeight(65)
        self._f_tone    = QLineEdit()
        self._f_hook    = QTextEdit()
        self._f_hook.setFixedHeight(115)
        self._f_hook.setPlaceholderText("本集结尾悬念钩子…")
        form.addRow("标题:",     self._f_title)
        form.addRow("环境:",     self._f_setting)
        form.addRow("角色:",     self._f_chars)
        form.addRow("情感基调:", self._f_tone)
        form.addRow("结尾钩子:", self._f_hook)
        lv.addLayout(form)

        # 钩子重写按钮
        hook_btn_row = QHBoxLayout()
        hook_btn_row.addStretch()
        btn_hook_rw = QPushButton("🎣 重写钩子")
        btn_hook_rw.setAutoDefault(False)
        btn_hook_rw.setDefault(False)
        btn_hook_rw.setMinimumHeight(28)
        btn_hook_rw.setToolTip("AI 重新生成本集的结尾悬念钩子")
        btn_hook_rw.setStyleSheet(
            "QPushButton{color:#e17055;border:1px solid #e17055;border-radius:4px;padding:2px 12px;}"
            "QPushButton:hover{background:#ffeaa7;}"
        )
        btn_hook_rw.clicked.connect(self._do_hook_rewrite)
        hook_btn_row.addWidget(btn_hook_rw)
        lv.addLayout(hook_btn_row)

        lv.addWidget(QLabel("📌 事件摘要 (每行一个事件):"))
        self._f_events = QTextEdit()
        self._f_events.setMinimumHeight(200)
        self._f_events.setStyleSheet("QTextEdit{background:#ffffff;}")
        lv.addWidget(self._f_events)

        # 因果边 — tag 样式
        edge_group = self._build_edge_section()
        lv.addWidget(edge_group)

        splitter.addWidget(left)

        # ---- 右侧: AI 辅助 ----
        right_widget = self._build_ai_panel()
        splitter.addWidget(right_widget)
        splitter.setSizes([440, 560])
        root.addWidget(splitter, 1)

        # ---- 底部: 操作按钮 ----
        btn_row = QHBoxLayout()

        btn_save = QPushButton("保存修改")
        btn_save.setAutoDefault(False)
        btn_save.setDefault(False)
        btn_save.setToolTip("覆盖保存到当前版本")
        btn_save.clicked.connect(self._do_save)
        btn_row.addWidget(btn_save)

        btn_save_new = QPushButton("另存新版本")
        btn_save_new.setAutoDefault(False)
        btn_save_new.setDefault(False)
        btn_save_new.setToolTip("将当前编辑保存为一个新版本")
        btn_save_new.setStyleSheet("color:#2980b9;")
        btn_save_new.clicked.connect(self._do_save_new_version)
        btn_row.addWidget(btn_save_new)

        self._cb_activate = QCheckBox("激活当前版本")
        self._cb_activate.setToolTip("勾选后，此版本将作为活跃版本用于后续阶段")
        self._cb_activate.setChecked(True)
        self._cb_activate.toggled.connect(self._on_activate_toggled)
        btn_row.addWidget(self._cb_activate)

        btn_row.addWidget(QLabel("  "))

        btn_cascade = QPushButton("🔗 自动改写后续章节")
        btn_cascade.setAutoDefault(False)
        btn_cascade.setDefault(False)
        btn_cascade.setToolTip("基于当前章节的修改，自动调整后续章节以保持连贯性")
        btn_cascade.setStyleSheet("color:#2980b9;")
        btn_cascade.clicked.connect(self._do_open_cascade)
        btn_row.addWidget(btn_cascade)

        from ui.widgets.split_dialog import SplitDialog
        btn_split = QPushButton("拆分...")
        btn_split.setAutoDefault(False)
        btn_split.setDefault(False)
        btn_split.clicked.connect(self._do_open_split)
        btn_row.addWidget(btn_split)

        btn_merge = QPushButton("合并->下一集")
        btn_merge.setAutoDefault(False)
        btn_merge.setDefault(False)
        btn_merge.clicked.connect(self._do_merge)
        btn_row.addWidget(btn_merge)

        btn_del = QPushButton("删除节点")
        btn_del.setAutoDefault(False)
        btn_del.setDefault(False)
        btn_del.setStyleSheet("color:#e74c3c;")
        btn_del.clicked.connect(self._do_delete)
        btn_row.addWidget(btn_del)

        btn_row.addStretch()

        # 编号修改
        btn_row.addWidget(QLabel("修改编号:"))
        self._id_combo = QComboBox()
        self._populate_id_combo()
        btn_row.addWidget(self._id_combo)
        btn_apply_id = QPushButton("应用")
        btn_apply_id.setAutoDefault(False)
        btn_apply_id.setDefault(False)
        btn_apply_id.clicked.connect(self._do_change_id)
        btn_row.addWidget(btn_apply_id)

        btn_close = QPushButton("关闭")
        btn_close.setAutoDefault(False)
        btn_close.setDefault(False)
        btn_close.clicked.connect(self.reject)
        btn_row.addWidget(btn_close)
        root.addLayout(btn_row)

    def keyPressEvent(self, event):
        """阻止 QDialog 默认的 Enter→accept() 和 Escape→reject() 中的 Enter 部分。
        QLineEdit 通过 returnPressed 信号独立处理 Enter，不受此影响。"""
        key = event.key()
        if key in (Qt.Key_Return, Qt.Key_Enter):
            # 如果焦点在 QLineEdit 上，让 QLineEdit 自己处理
            fw = self.focusWidget()
            if isinstance(fw, QLineEdit):
                # 手动触发对应的 returnPressed
                fw.returnPressed.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def reject(self):
        """如果已经保存过（self.action有值），使用accept返回，以便通知父窗口刷新UI"""
        if self.action:
            super().accept()
        else:
            super().reject()

    # ---- 版本下拉 ----
    def _refresh_version_combo(self):
        self._ver_combo.blockSignals(True)
        self._ver_combo.clear()
        versions = self._node.get("versions", [])
        active = self._node.get("active_version", 0)
        if not versions:
            self._ver_combo.addItem("v0 (当前内容)")
        else:
            for v in versions:
                ts = v.get("timestamp", "")[:16].replace("T", " ")
                marker = " [激活]" if v["ver_id"] == active else ""
                self._ver_combo.addItem(
                    f"v{v['ver_id']} {v.get('label','')}{marker} {ts}",
                    v["ver_id"]
                )
        current_idx = min(active, self._ver_combo.count() - 1)
        self._ver_combo.setCurrentIndex(current_idx)
        self._ver_combo.blockSignals(False)
        # 同步 checkbox（初始化时可能尚未创建）
        if hasattr(self, '_cb_activate'):
            self._cb_activate.blockSignals(True)
            self._cb_activate.setChecked(current_idx == active)
            self._cb_activate.blockSignals(False)

    def _on_version_switch(self, idx):
        versions = self._node.get("versions", [])
        if not versions or idx < 0 or idx >= len(versions):
            return
        snap = versions[idx]["snapshot"]
        self._load_node_to_form(snap)
        # 同步 checkbox：当前选中版本是否为激活版本
        active = self._node.get("active_version", 0)
        if hasattr(self, '_cb_activate'):
            self._cb_activate.blockSignals(True)
            self._cb_activate.setChecked(idx == active)
            self._cb_activate.blockSignals(False)
        # 切换聊天记录到该版本
        if hasattr(self, '_chat_browser'):
            self._switch_chat_to_version(idx)

    # ---- 工具: 从事件对象提取纯文本 ----
    @staticmethod
    def _extract_event_text(ev) -> str:
        """从 event_summaries 元素提取可读文本。
        AI 可能返回 str / {"description": ...} / {"event": ...} 等格式。"""
        if isinstance(ev, str):
            return ev
        if isinstance(ev, dict):
            # 优先级: description > event > 其他第一个字符串值
            for key in ("description", "event", "summary", "text"):
                if key in ev:
                    return str(ev[key])
            # fallback: 取第一个字符串类型的 value
            for v in ev.values():
                if isinstance(v, str) and len(v) > 10:
                    return v
        return str(ev)

    # ---- 左侧表单 load / read ----
    def _load_node_to_form(self, snap: dict):
        self._f_title.setText(snap.get("title", ""))
        self._f_setting.setPlainText(snap.get("setting", ""))
        chars = snap.get("characters", [])
        self._f_chars.setPlainText(", ".join(chars) if isinstance(chars, list) else str(chars))
        self._f_tone.setText(snap.get("emotional_tone", ""))
        self._f_hook.setPlainText(snap.get("episode_hook", ""))
        events = snap.get("event_summaries", [])
        if isinstance(events, list):
            self._f_events.setPlainText("\n".join(
                self._extract_event_text(e) for e in events
            ))
        else:
            self._f_events.setPlainText("")

    def _read_form_to_dict(self) -> dict:
        chars_raw = self._f_chars.toPlainText()
        chars = [c.strip() for c in chars_raw.split(",") if c.strip()]
        events_raw = self._f_events.toPlainText()
        events = [e.strip() for e in events_raw.split("\n") if e.strip()]
        return {
            "title":          self._f_title.text().strip(),
            "setting":        self._f_setting.toPlainText().strip(),
            "characters":     chars,
            "event_summaries": events,
            "emotional_tone": self._f_tone.text().strip(),
            "episode_hook":   self._f_hook.toPlainText().strip(),
        }

    # ---- 因果边 (tag-label 式) ----
    def _build_edge_section(self) -> QGroupBox:
        """构建因果连接编辑区 — 入口/出口各一行，tag 样式"""
        group = QGroupBox()
        edge_layout = QVBoxLayout(group)
        edge_layout.setContentsMargins(4, 4, 4, 4)
        edge_layout.setSpacing(4)
        nid = self._node.get("node_id", "")
        self._all_other_nodes = [n for n in self._pd.cpg_nodes if n.get("node_id") != nid]

        current_ins  = {e["from_node"] for e in (self._pd.cpg_edges or [])
                        if e.get("to_node") == nid}
        current_outs = {e["to_node"]   for e in (self._pd.cpg_edges or [])
                        if e.get("from_node") == nid}

        # 入口行
        in_row = QHBoxLayout()
        in_row.addWidget(QLabel("<b>← 入口:</b>"))
        self._in_tag_container = QWidget()
        self._in_tag_flow = QHBoxLayout(self._in_tag_container)
        self._in_tag_flow.setContentsMargins(0, 0, 0, 0)
        self._in_tag_flow.setSpacing(4)
        in_row.addWidget(self._in_tag_container, 1)
        btn_add_in = QPushButton("+")
        btn_add_in.setFixedSize(28, 24)
        btn_add_in.setAutoDefault(False)
        btn_add_in.setDefault(False)
        btn_add_in.setToolTip("添加入口连接")
        btn_add_in.setStyleSheet("QPushButton{color:#27ae60; background:#eafaf1; font-weight:bold; border:1px solid #bdc3c7; border-radius:3px; padding:0;}")
        btn_add_in.clicked.connect(lambda: self._add_edge_tag("in"))
        in_row.addWidget(btn_add_in)
        edge_layout.addLayout(in_row)

        # 出口行
        out_row = QHBoxLayout()
        out_row.addWidget(QLabel("<b>→ 出口:</b>"))
        self._out_tag_container = QWidget()
        self._out_tag_flow = QHBoxLayout(self._out_tag_container)
        self._out_tag_flow.setContentsMargins(0, 0, 0, 0)
        self._out_tag_flow.setSpacing(4)
        out_row.addWidget(self._out_tag_container, 1)
        btn_add_out = QPushButton("+")
        btn_add_out.setFixedSize(28, 24)
        btn_add_out.setAutoDefault(False)
        btn_add_out.setDefault(False)
        btn_add_out.setToolTip("添加出口连接")
        btn_add_out.setStyleSheet("QPushButton{color:#2980b9; background:#ebf5fb; font-weight:bold; border:1px solid #bdc3c7; border-radius:3px; padding:0;}")
        btn_add_out.clicked.connect(lambda: self._add_edge_tag("out"))
        out_row.addWidget(btn_add_out)
        edge_layout.addLayout(out_row)

        # 初始标签
        self._in_tags = set(current_ins)
        self._out_tags = set(current_outs)
        self._refresh_edge_tags()

        return group

    def _make_tag_widget(self, node_id: str, direction: str) -> QWidget:
        """创建一个 tag 控件：[Ep3 x]"""
        tag = QWidget()
        tag.setFixedHeight(24)
        h = QHBoxLayout(tag)
        h.setContentsMargins(6, 0, 2, 0)
        h.setSpacing(2)
        lbl = QLabel(node_id)
        lbl.setStyleSheet(" color:#2c3e50;")
        h.addWidget(lbl)
        btn_x = QPushButton("x")
        btn_x.setFixedSize(16, 16)
        btn_x.setStyleSheet(
            "QPushButton{border:none;color:#e74c3c;font-weight:bold;padding:0;}"
            "QPushButton:hover{color:#c0392b;background:#fadbd8;border-radius:8px;}"
        )
        btn_x.setCursor(Qt.PointingHandCursor)
        btn_x.clicked.connect(lambda _, nid=node_id, d=direction: self._remove_edge_tag(nid, d))
        h.addWidget(btn_x)
        color = "#d5f5e3" if direction == "in" else "#d6eaf8"
        border_color = "#27ae60" if direction == "in" else "#2980b9"
        tag.setObjectName("edgeTag")
        tag.setStyleSheet(
            f"#edgeTag{{background:{color};border:1px solid {border_color};"
            f"border-radius:10px;}}"
        )
        return tag

    def _refresh_edge_tags(self):
        """刷新入口/出口 tag 显示"""
        # 清空
        while self._in_tag_flow.count():
            item = self._in_tag_flow.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        while self._out_tag_flow.count():
            item = self._out_tag_flow.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        # 重建
        for nid in sorted(self._in_tags):
            self._in_tag_flow.addWidget(self._make_tag_widget(nid, "in"))
        self._in_tag_flow.addStretch()
        for nid in sorted(self._out_tags):
            self._out_tag_flow.addWidget(self._make_tag_widget(nid, "out"))
        self._out_tag_flow.addStretch()

    def _remove_edge_tag(self, node_id: str, direction: str):
        if direction == "in":
            self._in_tags.discard(node_id)
        else:
            self._out_tags.discard(node_id)
        self._refresh_edge_tags()

    def _add_edge_tag(self, direction: str):
        """弹出快速选择框添加连接"""
        existing = self._in_tags if direction == "in" else self._out_tags
        available = [n.get("node_id", "") for n in self._all_other_nodes
                     if n.get("node_id", "") not in existing]
        if not available:
            QMessageBox.information(self, "提示", "没有可添加的节点了。")
            return
        from PySide6.QtWidgets import QInputDialog
        chosen, ok = QInputDialog.getItem(
            self, f"添加{'入口' if direction == 'in' else '出口'}连接",
            "选择节点:", available, 0, False
        )
        if ok and chosen:
            if direction == "in":
                self._in_tags.add(chosen)
            else:
                self._out_tags.add(chosen)
            self._refresh_edge_tags()

    # ---- AI 辅助面板 ----
    def _build_ai_panel(self) -> QGroupBox:
        group = QGroupBox("🤖 AI 辅助修改")
        gv = QVBoxLayout(group)

        # 模式选择（只有两个模式，BVSR 内嵌）
        mode_row = QHBoxLayout()
        self._rb_chat  = QRadioButton("💬 自由对话")
        self._rb_regen = QRadioButton("⚡ 快速重生成")
        self._rb_chat.setChecked(True)
        for rb in (self._rb_chat, self._rb_regen):
            mode_row.addWidget(rb)
        mode_row.addStretch()
        gv.addLayout(mode_row)

        # 堆叠面板
        self._ai_stack = QStackedWidget()
        self._ai_stack.addWidget(self._build_chat_panel())    # 0
        self._ai_stack.addWidget(self._build_regen_panel())   # 1
        gv.addWidget(self._ai_stack, 1)

        self._rb_chat.toggled.connect(lambda c: c and self._ai_stack.setCurrentIndex(0))
        self._rb_regen.toggled.connect(lambda c: c and self._ai_stack.setCurrentIndex(1))
        return group

    # -- Chat 面板 --
    def _build_chat_panel(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)

        self._chat_browser = QTextBrowser()
        self._chat_browser.setOpenLinks(False)
        v.addWidget(self._chat_browser, 1)

        # 待应用的修改 node（Chat AI 检测到时暂存）
        self._pending_modify_node = None
        self._btn_apply_chat = QPushButton("✅ 确认修改 (将创建新版本，旧版本内容不受影响)")
        self._btn_apply_chat.setAutoDefault(False)
        self._btn_apply_chat.setDefault(False)
        self._btn_apply_chat.setVisible(False)
        self._btn_apply_chat.setStyleSheet(
            "QPushButton{background:#27ae60;color:white;font-weight:bold;"
            "padding:8px 16px;border-radius:4px;border:none;}"
            "QPushButton:hover{background:#229954;}"
        )
        self._btn_apply_chat.clicked.connect(self._do_apply_chat_modify)
        v.addWidget(self._btn_apply_chat)

        # 选项快捷按钮区（AI 回复中的编号选项）
        self._options_widget = QWidget()
        self._options_layout = QHBoxLayout(self._options_widget)
        self._options_layout.setContentsMargins(0, 2, 0, 2)
        self._options_layout.setSpacing(4)
        self._options_widget.setVisible(False)
        v.addWidget(self._options_widget)

        # 输入行
        inp_row = QHBoxLayout()
        self._chat_input = QLineEdit()
        self._chat_input.setPlaceholderText("输入消息… (Enter 发送)")
        self._chat_input.returnPressed.connect(self._do_chat_send)
        inp_row.addWidget(self._chat_input, 1)
        btn_send = QPushButton("发送")
        btn_send.setAutoDefault(False)
        btn_send.setDefault(False)
        btn_send.clicked.connect(self._do_chat_send)
        inp_row.addWidget(btn_send)
        btn_clear = QPushButton("清空对话")
        btn_clear.setAutoDefault(False)
        btn_clear.setDefault(False)
        btn_clear.setToolTip("在对话中插入分隔线，后续 AI 不再参考分隔线以上的内容")
        btn_clear.setStyleSheet("color:#e67e22;")
        btn_clear.clicked.connect(self._do_clear_chat)
        inp_row.addWidget(btn_clear)
        v.addLayout(inp_row)

        # 加载当前版本的聊天记录
        self._current_chat_ver = self._node.get("active_version", 0)
        self._chat_history = self._load_version_chat(self._current_chat_ver)
        self._render_chat_history()
        return w

    def _get_version_chats_store(self) -> dict:
        """获取版本聊天存储字典"""
        if "version_chats" not in self._node:
            # 迁移旧格式：将 node["chat_history"] 迁移到 version_chats
            old = self._node.pop("chat_history", [])
            self._node["version_chats"] = {}
            if old:
                active = str(self._node.get("active_version", 0))
                self._node["version_chats"][active] = old
        return self._node["version_chats"]

    def _load_version_chat(self, ver_idx: int) -> list:
        store = self._get_version_chats_store()
        return list(store.get(str(ver_idx), []))

    def _save_current_chat(self):
        store = self._get_version_chats_store()
        store[str(self._current_chat_ver)] = list(self._chat_history)

    def _render_chat_history(self):
        """清空浏览器并重新渲染当前聊天记录"""
        self._chat_browser.clear()
        for msg in self._chat_history:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                self._chat_browser.append(
                    '<hr><p style="color:#95a5a6;text-align:center;font-style:italic;">'
                    f'{content}</p><hr>'
                )
            elif role == "user":
                self._chat_browser.append(
                    f'<p style="color:#2d3436;"><b>你:</b> {content}</p>'
                )
            else:
                safe = content.replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
                self._chat_browser.append(
                    f'<p style="color:#0984e3;"><b>AI:</b> {safe}</p>'
                )

    def _switch_chat_to_version(self, ver_idx: int):
        """版本切换时切换聊天记录"""
        self._save_current_chat()
        self._current_chat_ver = ver_idx
        self._chat_history = self._load_version_chat(ver_idx)
        self._render_chat_history()
        self._clear_option_buttons()
        self._btn_apply_chat.setVisible(False)
        self._pending_modify_node = None

    def _do_clear_chat(self):
        """软清空：插入分隔标记"""
        marker = "—— 以上已清空，不再在后续内容中作为生成上文出现 ——"
        self._chat_history.append({"role": "system", "content": marker})
        self._save_current_chat()
        self._chat_browser.append(
            '<hr><p style="color:#95a5a6;text-align:center;font-style:italic;">'
            f'{marker}</p><hr>'
        )
        self._clear_option_buttons()

    # -- Quick-Regen 面板 --
    def _build_regen_panel(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        v = QVBoxLayout(inner)
        v.setContentsMargins(4, 4, 4, 4)

        # 读取自定义或默认的选项列表
        dir_options = self._pd.custom_drama_directions
        if dir_options is None:
            dir_options = list(DRAMA_DIRECTION_OPTIONS)
        self._active_dir_options = dir_options  # [(key, label), ...]

        struct_options = self._pd.custom_structure_options
        if struct_options is None:
            struct_options = list(STRUCTURE_OPTIONS)
        self._active_struct_options = struct_options  # [(key, label), ...]

        # 情节方向（每行最多3个，自动折行）
        v.addWidget(QLabel("📌 情节方向:"))
        self._dir_radios = {}
        dir_group = QButtonGroup(inner)
        MAX_DIR_PER_ROW = 3
        for i in range(0, len(dir_options), MAX_DIR_PER_ROW):
            row_w = QWidget()
            row_l = QHBoxLayout(row_w)
            row_l.setContentsMargins(8, 0, 0, 0)
            row_l.setSpacing(8)
            for item in dir_options[i:i + MAX_DIR_PER_ROW]:
                key, label = item[0], item[1]
                rb = QRadioButton(label)
                dir_group.addButton(rb)
                self._dir_radios[key] = rb
                row_l.addWidget(rb)
            row_l.addStretch()
            v.addWidget(row_w)

        # 结构微调（每行最多3个，自动折行）
        v.addWidget(QLabel("📌 结构微调:"))
        self._struct_checks = {}
        MAX_STRUCT_PER_ROW = 3
        for i in range(0, len(struct_options), MAX_STRUCT_PER_ROW):
            row_w = QWidget()
            row_l = QHBoxLayout(row_w)
            row_l.setContentsMargins(8, 0, 0, 0)
            row_l.setSpacing(8)
            for item in struct_options[i:i + MAX_STRUCT_PER_ROW]:
                key, label = item[0], item[1]
                cb = QCheckBox(label)
                self._struct_checks[key] = cb
                row_l.addWidget(cb)
            row_l.addStretch()
            v.addWidget(row_w)

        # 额外指令
        v.addWidget(QLabel("📌 额外指令:"))
        self._regen_extra = QLineEdit()
        self._regen_extra.setPlaceholderText("补充说明…")
        v.addWidget(self._regen_extra)

        btn_regen = QPushButton("🔄 重新生成")
        btn_regen.setFixedWidth(200)
        btn_regen.clicked.connect(self._do_quick_regen)
        v.addWidget(btn_regen)

        self._regen_status = QLabel("")
        self._regen_status.setStyleSheet("color:#27ae60;")
        v.addWidget(self._regen_status)

        # 改写预览区
        v.addWidget(QLabel("── ✏️ 改写预览 ──"))
        self._regen_preview = QTextEdit()
        self._regen_preview.setPlaceholderText("重新生成后，结果将显示在此处。\n可以手动修改后点击「确认修改」。")
        self._regen_preview.setMinimumHeight(120)
        v.addWidget(self._regen_preview, 1)

        btn_confirm_regen = QPushButton("✅ 确认修改 (覆盖当前版本)")
        btn_confirm_regen.setAutoDefault(False)
        btn_confirm_regen.setDefault(False)
        btn_confirm_regen.setStyleSheet(
            "QPushButton{background:#27ae60;color:white;font-weight:bold;"
            "padding:6px 16px;border-radius:4px;border:none;}"
            "QPushButton:hover{background:#229954;}"
        )
        btn_confirm_regen.clicked.connect(self._do_confirm_regen_preview)
        v.addWidget(btn_confirm_regen)

        v.addStretch()

        scroll.setWidget(inner)
        return scroll

    # BVSR 不再是单独面板 — 人格选择已内嵌到 Chat 和 Quick-Regen 面板中
    # 保留候选结果列表和采用逻辑供两个面板共用

    def _build_persona_checkboxes(self, parent_layout) -> dict:
        """构建人格复选框组，返回 {key: QCheckBox}"""
        from services.persona_engine import persona_engine
        personas = persona_engine.get_all_personas()
        widget = QWidget()
        flow = QHBoxLayout(widget)
        flow.setContentsMargins(0, 0, 0, 0)
        flow.setSpacing(6)
        checks = {}
        for key, p in personas.items():
            cb = QCheckBox(p.get("name", key).split("(")[0].strip())
            cb.setToolTip(p.get("identity_block", "")[:120])
            checks[key] = cb
            flow.addWidget(cb)
        flow.addStretch()
        parent_layout.addWidget(widget)
        return checks

    def _populate_id_combo(self):
        nid = self._node.get("node_id", "")
        self._id_combo.clear()
        self._id_combo.addItem(f"{nid} (当前)")
        total = max(self._pd.total_episodes, len(self._pd.cpg_nodes)) + 10
        for i in range(1, total + 1):
            cid = f"Ep{i}"
            if cid != nid:
                self._id_combo.addItem(cid, cid)

    # ------------------------------------------------------------------ #
    # 钩子重写
    # ------------------------------------------------------------------ #
    def _do_hook_rewrite(self):
        """打开钩子重写对话框"""
        dlg = HookRewriteDialog(self._node, self._pd, parent=self)
        if dlg.exec() == QDialog.Accepted:
            new_hook = dlg.adopted_hook()
            if new_hook:
                self._f_hook.setPlainText(new_hook)
                QMessageBox.information(
                    self, "钩子已更新",
                    "新钩子已写入表单。请点击「保存修改」或「另存新版本」来保存。"
                )
                # 检查是否有后续章节
                import re
                nid = self._node.get("node_id", "")
                nums = re.findall(r'\d+', nid)
                if nums:
                    next_id = f"Ep{int(nums[0]) + 1}"
                    next_node = next(
                        (n for n in self._pd.cpg_nodes if n.get("node_id") == next_id),
                        None
                    )
                    if next_node:
                        reply = QMessageBox.question(
                            self, "后续章节同步",
                            f"钩子已更改，{next_id} 的开头衔接（opening_hook）可能需要同步调整。\n\n"
                            f"是否需要 AI 为 {next_id} 重新生成开头衔接？\n"
                            f"（仅调整 opening_hook，不影响整集剧情）",
                            QMessageBox.Yes | QMessageBox.No,
                        )
                        if reply == QMessageBox.Yes:
                            self._regen_next_opening_hook(next_node, new_hook)

    def _regen_next_opening_hook(self, next_node, new_hook):
        """用新钩子为下一集重新生成 opening_hook"""
        from services.worker import HookRewriteWorker
        from models.project_state import get_active_version_snapshot

        next_snap = get_active_version_snapshot(next_node)
        next_id = next_node.get("node_id", "")
        cur_id = self._node.get("node_id", "")

        # 构建一个特殊的 Worker 来重写 opening_hook
        # 复用 AI service 直接调用
        from services.ai_service import ai_service
        from services.logger_service import app_logger

        system_prompt = (
            f"你是一位专业的短剧编剧。\n"
            f"上一集（{cur_id}）的结尾悬念钩子刚被修改为：\n"
            f"「{new_hook}」\n\n"
            f"请为 {next_id} 重新生成一个 opening_hook（开篇衔接），\n"
            f"要求：紧接上一集的悬念，同一场景、同一时间线、无缝延续。\n\n"
            f"{next_id} 的事件摘要：\n"
            + "\n".join(f"  - {e}" for e in next_snap.get("event_summaries", [])[:3])
            + f"\n\n严格输出 JSON：{{\"opening_hook\": \"你的开篇衔接文本\"}}"
        )

        try:
            result = ai_service.generate_json(
                user_prompt=f"请为 {next_id} 生成新的 opening_hook。",
                system_prompt=system_prompt,
                temperature=0.7,
                max_tokens=1024,
            )
            new_opening = result.get("opening_hook", "")
            if new_opening:
                from models.project_state import apply_snapshot, make_node_snapshot, add_version
                next_node["opening_hook"] = new_opening
                add_version(next_node, "ai_generate", "钩子同步-开头重写")
                app_logger.info("钩子同步", f"{next_id} 的 opening_hook 已更新")
                QMessageBox.information(
                    self, "同步完成",
                    f"{next_id} 的开篇衔接已更新为：\n\n{new_opening[:100]}..."
                )
            else:
                QMessageBox.warning(self, "同步失败", "AI 未返回有效的开篇衔接。")
        except Exception as e:
            QMessageBox.warning(self, "同步失败", f"重新生成 opening_hook 失败：{e}")

    # ------------------------------------------------------------------ #
    # 保存逻辑
    # ------------------------------------------------------------------ #
    def _do_save(self):
        """覆盖保存到当前版本（不创建新版本）"""
        new_snap = self._read_form_to_dict()
        apply_snapshot(self._node, new_snap)
        self._save_edges()

        # 覆盖当前版本的 snapshot
        update_version(self._node)
        self._refresh_version_combo()

        self.action = "saved"
        QMessageBox.information(self, "保存成功", "当前版本已保存。（页面保持打开，可继续编辑）")

    def _do_save_new_version(self):
        """将当前编辑另存为新版本"""
        new_snap = self._read_form_to_dict()
        apply_snapshot(self._node, new_snap)
        self._save_edges()

        ver_id = add_version(self._node, "manual", "手动编辑")

        # 根据 checkbox 决定是否激活
        if getattr(self, '_cb_activate', None) and self._cb_activate.isChecked():
            set_active_version(self._node, ver_id)

        self._refresh_version_combo()
        self.action = "saved"
        QMessageBox.information(self, "版本管理", f"已创建新版本 v{ver_id}。（页面保持打开，可继续编辑）")

    def _on_activate_toggled(self, checked: bool):
        """切换当前版本的激活状态"""
        if checked:
            idx = self._ver_combo.currentIndex()
            versions = self._node.get("versions", [])
            if 0 <= idx < len(versions):
                self._node["active_version"] = idx

    def _save_edges(self):
        nid = self._node.get("node_id", "")
        edges = self._pd.cpg_edges
        edges[:] = [e for e in edges
                    if not (e.get("to_node") == nid or e.get("from_node") == nid)]
        for from_id in self._in_tags:
            edges.append({"from_node": from_id, "to_node": nid, "relation": "causal"})
        for to_id in self._out_tags:
            edges.append({"from_node": nid, "to_node": to_id, "relation": "causal"})

    # ------------------------------------------------------------------ #
    # 删除
    # ------------------------------------------------------------------ #
    def _do_delete(self):
        nid = self._node.get("node_id", "")
        r = QMessageBox.question(self, "确认删除", f"确定删除节点 {nid}？相关边也会删除。",
                                 QMessageBox.Yes | QMessageBox.No)
        if r == QMessageBox.Yes:
            self.action = "deleted"
            self.accept()

    # ------------------------------------------------------------------ #
    # 编号修改
    # ------------------------------------------------------------------ #
    def _do_change_id(self):
        idx = self._id_combo.currentIndex()
        if idx == 0:
            return
        new_id = self._id_combo.currentData()
        if not new_id:
            return
        old_id = self._node.get("node_id", "")
        existing = {n.get("node_id") for n in self._pd.cpg_nodes}
        if new_id in existing:
            QMessageBox.warning(self, "编号冲突", f"编号 {new_id} 已存在。")
            return
        self._node["node_id"] = new_id
        for e in self._pd.cpg_edges:
            if e.get("from_node") == old_id: e["from_node"] = new_id
            if e.get("to_node")   == old_id: e["to_node"]   = new_id
        if old_id in self._pd.confirmed_beats:
            self._pd.confirmed_beats[new_id] = self._pd.confirmed_beats.pop(old_id)
        self.action = f"id_changed:{new_id}"
        self.accept()

    # ------------------------------------------------------------------ #
    # 拆分
    # ------------------------------------------------------------------ #
    def _do_open_cascade(self):
        """打开级联改写后续章节对话框"""
        from ui.widgets.cascade_rewrite_dialog import CascadeRewriteDialog
        dlg = CascadeRewriteDialog(self._node, self._pd, parent=self)
        if dlg.exec() == QDialog.Accepted:
            self.action = "saved"
            self._refresh_version_combo()

    def _do_open_split(self):
        from ui.widgets.split_dialog import SplitDialog
        dlg = SplitDialog(self._node, self._pd, parent=self)
        if dlg.exec() == QDialog.Accepted:
            self.action = "split"
            self.accept()

    # ------------------------------------------------------------------ #
    # 合并
    # ------------------------------------------------------------------ #
    def _do_merge(self):
        nid = self._node.get("node_id", "")
        # 找到出口边指向的最近节点
        outs = [e["to_node"] for e in (self._pd.cpg_edges or [])
                if e.get("from_node") == nid]
        if not outs:
            QMessageBox.information(self, "无法合并", "当前节点没有出口节点，无法合并。")
            return
        next_id = outs[0]
        next_node = next((n for n in self._pd.cpg_nodes if n.get("node_id") == next_id), None)
        if not next_node:
            QMessageBox.information(self, "无法合并", f"未找到节点 {next_id}。")
            return
        r = QMessageBox.question(
            self, "确认合并",
            f"将 {nid}「{self._node.get('title','')}」\n"
            f"与 {next_id}「{next_node.get('title','')}」合并为一集？\n"
            f"AI 将重写合并内容。",
            QMessageBox.Yes | QMessageBox.No,
        )
        if r != QMessageBox.Yes:
            return
        self._launch_merge(next_node)

    def _launch_merge(self, next_node: dict):
        import json as _json
        from env import (SYSTEM_PROMPT_NODE_MERGE, USER_PROMPT_NODE_MERGE,
                         DRAMA_STYLE_CONFIG)
        from services.worker import NodeRefineWorker

        style_key = self._pd.drama_style or "short_drama"
        drama_block = DRAMA_STYLE_CONFIG.get(style_key, {}).get("variation_style_block", "")
        nodes_json = _json.dumps([
            make_node_snapshot(self._node),
            make_node_snapshot(next_node),
        ], ensure_ascii=False, indent=2)

        sys_p = SYSTEM_PROMPT_NODE_MERGE.replace("{drama_style_block}", drama_block)
        usr_p = USER_PROMPT_NODE_MERGE.replace("{nodes_json}", nodes_json)

        ai_params = {"temperature": 0.7, "max_tokens": 2048}
        self._pd.push_history("merge_nodes", self._node.get("node_id", ""))
        self._worker = NodeRefineWorker("merge", sys_p, usr_p, ai_params)
        self._worker.finished.connect(lambda r: self._on_merge_done(r, next_node))
        self._worker.error.connect(lambda e: (setattr(self, '_worker', None),
                                               QMessageBox.warning(self, "合并失败", e)))
        self._worker.start()

    def _on_merge_done(self, result: dict, next_node: dict):
        self._worker = None
        node_data = result.get("node")
        if not node_data:
            QMessageBox.warning(self, "合并失败", "AI 未返回有效内容，请重试。")
            return
        # 更新当前节点
        apply_snapshot(self._node, node_data)
        add_version(self._node, "merge", f"合并 {next_node.get('node_id','')}")
        # 转移 next_node 的出口边
        nid = self._node.get("node_id", "")
        next_id = next_node.get("node_id", "")
        edges = self._pd.cpg_edges
        for e in edges:
            if e.get("from_node") == next_id:
                e["from_node"] = nid
        # 删除 next_node
        self._pd.cpg_nodes[:] = [n for n in self._pd.cpg_nodes
                                  if n.get("node_id") != next_id]
        edges[:] = [e for e in edges
                    if not (e.get("from_node") == nid and e.get("to_node") == next_id)]
        self.action = "merge"
        self.accept()

    # ------------------------------------------------------------------ #
    # Chat 模式
    # ------------------------------------------------------------------ #
    def _build_node_context_str(self) -> str:
        n = self._node
        events = "\n".join(f"  - {e}" for e in n.get("event_summaries", []))
        return (f"集号: {n.get('node_id','')}  标题: {n.get('title','')}\n"
                f"阶段: {n.get('hauge_stage_name','')}\n"
                f"环境: {n.get('setting','')}\n"
                f"角色: {', '.join(n.get('characters',[]))}\n"
                f"事件:\n{events}\n"
                f"情感: {n.get('emotional_tone','')}\n"
                f"钩子: {n.get('episode_hook','')}")

    def _build_prev_next_context(self) -> tuple[str, str]:
        nid = self._node.get("node_id", "")
        edges = self._pd.cpg_edges or []
        id_title = {n["node_id"]: n.get("title","") for n in self._pd.cpg_nodes}
        ins  = [f"{e['from_node']}《{id_title.get(e['from_node'],'?')}》"
                for e in edges if e.get("to_node") == nid]
        outs = [f"{e['to_node']}《{id_title.get(e['to_node'],'?')}》"
                for e in edges if e.get("from_node") == nid]
        return ", ".join(ins) or "（无）", ", ".join(outs) or "（无）"

    def _get_chat_system_prompt(self) -> str:
        from env import SYSTEM_PROMPT_NODE_CHAT
        n = self._node
        events = "\n".join(f"  - {e}" for e in n.get("event_summaries", []))
        prev_ctx, next_ctx = self._build_prev_next_context()
        return (SYSTEM_PROMPT_NODE_CHAT
                .replace("{node_id}",         n.get("node_id", ""))
                .replace("{hauge_stage_name}", n.get("hauge_stage_name", ""))
                .replace("{title}",           n.get("title", ""))
                .replace("{setting}",         n.get("setting", ""))
                .replace("{characters}",      ", ".join(n.get("characters", [])))
                .replace("{event_summaries}", events)
                .replace("{emotional_tone}",  n.get("emotional_tone", ""))
                .replace("{episode_hook}",    n.get("episode_hook", ""))
                .replace("{sparkle}",         self._pd.sparkle or "")
                .replace("{prev_context}",    prev_ctx)
                .replace("{next_context}",    next_ctx))

    def _do_chat_send(self, override_text: str = None):
        text = override_text or self._chat_input.text().strip()
        if not text or self._worker is not None:
            return
        self._chat_input.clear()
        self._clear_option_buttons()
        self._append_chat("user", text)

        from env import USER_PROMPT_NODE_CHAT
        from services.worker import NodeRefineWorker

        sys_p = self._get_chat_system_prompt()

        # 构建上文（仅包含最后一次清空标记之后的内容）
        context_msgs = self._get_context_messages()
        history_block = ""
        if len(context_msgs) > 1:  # 除了刚发的这条
            lines = []
            for m in context_msgs[:-1]:  # 不含最后一条（刚发的）
                prefix = "用户" if m["role"] == "user" else "AI"
                lines.append(f"{prefix}: {m['content'][:200]}")
            history_block = "\n".join(lines[-10:])  # 最近10条

        usr_p = USER_PROMPT_NODE_CHAT.replace("{user_message}", text)
        if history_block:
            usr_p = f"[对话上文]\n{history_block}\n\n" + usr_p

        self._worker = NodeRefineWorker(
            "chat", sys_p, usr_p,
            {"temperature": 0.8, "max_tokens": 2048}
        )
        self._worker.finished.connect(self._on_chat_response)
        self._worker.error.connect(lambda e: (self._append_chat("ai", f"❌ {e}"),
                                               setattr(self, '_worker', None)))
        self._worker.start()

    def _get_context_messages(self) -> list:
        """获取最后一次清空标记之后的有效对话上文"""
        last_clear = -1
        for i, m in enumerate(self._chat_history):
            if m.get("role") == "system":
                last_clear = i
        return self._chat_history[last_clear + 1:]

    def _on_chat_response(self, result: dict):
        self._worker = None
        response = result.get("response", "")
        modify_node = result.get("modify_node")
        self._append_chat("ai", response)

        if modify_node:
            self._pending_modify_node = modify_node
            self._btn_apply_chat.setVisible(True)
            self._clear_option_buttons()
        else:
            self._btn_apply_chat.setVisible(False)
            # 解析 AI 回复中的编号选项
            self._parse_and_show_options(response)

    def _parse_and_show_options(self, text: str):
        """解析 AI 回复中的编号选项和确认修改提示，显示快捷按钮"""
        import re
        self._clear_option_buttons()

        has_content = False

        # 1) 检测"确认修改"提示：AI 提出了修改方案，等待用户确认
        confirm_patterns = [
            "确认修改", "请确认", "应用修改", "执行修改",
            "以上是修改方案", "是否应用", "是否修改",
        ]
        if any(p in text for p in confirm_patterns):
            btn_confirm = QPushButton("✅ 确认修改")
            btn_confirm.setAutoDefault(False)
            btn_confirm.setDefault(False)
            btn_confirm.setToolTip("发送确认修改指令，让 AI 执行修改")
            btn_confirm.setStyleSheet(
                "QPushButton{background:#27ae60;color:white;font-weight:bold;"
                "padding:4px 16px;border-radius:4px;border:none;}"
                "QPushButton:hover{background:#229954;}"
            )
            btn_confirm.setCursor(Qt.PointingHandCursor)
            btn_confirm.clicked.connect(lambda: self._do_chat_send(override_text="确认修改"))
            self._options_layout.addWidget(btn_confirm)

            hint = QLabel("  或在聊天框输入您的意见")
            hint.setStyleSheet("color:#7f8c8d;")
            self._options_layout.addWidget(hint)
            has_content = True

        # 2) 解析编号选项 (1. xxx / 1、xxx / 1. **xxx**)
        pattern = r'^\s*([1-9])[.、\)\]）】]\s*[*「]*([^*」\n]{2,30})[*」]*'
        options = []
        for line in text.split("\n"):
            m = re.match(pattern, line.strip())
            if m:
                num = m.group(1)
                label = m.group(2).strip().rstrip("：:")
                options.append((num, label))

        if options and len(options) <= 6:
            if has_content:
                sep = QLabel("  │  ")
                sep.setStyleSheet("color:#bdc3c7;")
                self._options_layout.addWidget(sep)
            lbl = QLabel("快捷选择:")
            lbl.setStyleSheet("")
            self._options_layout.addWidget(lbl)
            for num, label in options:
                btn = QPushButton(f"{num}. {label[:12]}")
                btn.setAutoDefault(False)
                btn.setDefault(False)
                btn.setToolTip(f"选择方案{num}: {label}")
                btn.setStyleSheet(
                    "QPushButton{background:#ebf5fb;border:1px solid #3498db;"
                    "border-radius:3px;padding:2px 8px;}"
                    "QPushButton:hover{background:#d4e6f1;}"
                )
                btn.setCursor(Qt.PointingHandCursor)
                btn.clicked.connect(lambda _, n=num, l=label: self._on_option_click(n, l))
                self._options_layout.addWidget(btn)
            has_content = True

        if has_content:
            self._options_layout.addStretch()
            self._options_widget.setVisible(True)

    def _on_option_click(self, num: str, label: str):
        """用户点击快捷选项按钮"""
        self._do_chat_send(override_text=f"选择方案 {num}：{label}")

    def _clear_option_buttons(self):
        """清除选项按钮"""
        while self._options_layout.count():
            item = self._options_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._options_widget.setVisible(False)

    def _append_chat(self, role: str, text: str):
        if role == "user":
            html = f'<p style="color:#2d3436;"><b>你:</b> {text}</p>'
        else:
            safe = text.replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
            html = f'<p style="color:#0984e3;"><b>AI:</b> {safe}</p>'
        self._chat_browser.append(html)
        # Persist to version-specific chat
        self._chat_history.append({"role": role, "content": text})
        self._save_current_chat()

    def _do_apply_chat_modify(self):
        if not self._pending_modify_node:
            return
        apply_snapshot(self._node, self._pending_modify_node)
        self._load_node_to_form(self._pending_modify_node)
        ver_id = add_version(self._node, "chat_refine", "Chat AI 修改")
        self._refresh_version_combo()
        self._pending_modify_node = None
        self._btn_apply_chat.setVisible(False)
        self._append_chat("ai",
            f"✅ 修改已应用并创建为 v{ver_id}。旧版本内容不受影响，可通过版本下拉随时切换。")

    # ------------------------------------------------------------------ #
    # Quick-Regen
    # ------------------------------------------------------------------ #
    def _build_regen_instruction(self) -> str:
        """构建调整指令：情节方向 + 结构微调 + 额外指令 三者共存"""
        parts = []
        # 从 self._active_dir_options 查找匹配 label
        dir_lookup = {item[0]: item[1] for item in getattr(self, '_active_dir_options', DRAMA_DIRECTION_OPTIONS)}
        for key, rb in self._dir_radios.items():
            if rb.isChecked():
                parts.append(f"情节方向: {dir_lookup.get(key, key)}")

        struct_lookup = {item[0]: item[1] for item in getattr(self, '_active_struct_options', STRUCTURE_OPTIONS)}
        struct_parts = []
        for key, cb in self._struct_checks.items():
            if cb.isChecked():
                struct_parts.append(struct_lookup.get(key, key))
        if struct_parts:
            parts.append(f"结构微调: {', '.join(struct_parts)}")

        extra = self._regen_extra.text().strip()
        if extra:
            parts.append(f"额外要求: {extra}")
        return "\n".join(parts) if parts else "保持原有风格，提升内容质量"

    def _do_quick_regen(self):
        if self._worker:
            return

        # 验证情节方向不能为空
        direction_selected = any(rb.isChecked() for rb in self._dir_radios.values())
        if not direction_selected:
            QMessageBox.warning(self, "提示", "请至少选择一个「情节方向」。")
            return

        from env import (SYSTEM_PROMPT_NODE_QUICK_REGEN, USER_PROMPT_NODE_QUICK_REGEN,
                         DRAMA_STYLE_CONFIG)
        from services.worker import NodeRefineWorker

        style_key = self._pd.drama_style or "short_drama"
        drama_block = DRAMA_STYLE_CONFIG.get(style_key, {}).get("variation_style_block", "")
        prev_ctx, next_ctx = self._build_prev_next_context()
        node_ctx = self._build_node_context_str()
        instructions = self._build_regen_instruction()

        # 使用自定义 prompt（如果有），否则用默认值
        sys_template = self._pd.custom_quick_regen_sys_prompt or SYSTEM_PROMPT_NODE_QUICK_REGEN
        usr_template = self._pd.custom_quick_regen_usr_prompt or USER_PROMPT_NODE_QUICK_REGEN

        sys_p = (sys_template
                 .replace("{persona_identity_block}", "")
                 .replace("{drama_style_block}", drama_block)
                 .replace("{node_context}", node_ctx)
                 .replace("{prev_context}", prev_ctx)
                 .replace("{next_context}", next_ctx))
        usr_p = (usr_template
                 .replace("{adjustment_instructions}", instructions)
                 .replace("{extra_instructions}", ""))
        self._worker = NodeRefineWorker(
            "quick_regen", sys_p, usr_p, {"temperature": 0.7, "max_tokens": 4096}
        )

        self._regen_status.setText("⏳ 生成中…")
        self._regen_preview.clear()
        self._worker.finished.connect(self._on_regen_done)
        self._worker.error.connect(lambda e: (setattr(self, '_worker', None),
                                               self._regen_status.setText(f"❌ {e}")))
        self._worker.start()

    def _on_regen_done(self, result: dict):
        self._worker = None
        node = result.get("node")
        if node:
            # 将结果显示在改写预览区，不直接应用
            preview_lines = []
            preview_lines.append(f"标题: {node.get('title', '')}")
            preview_lines.append(f"环境: {node.get('setting', '')}")
            chars = node.get("characters", [])
            preview_lines.append(f"角色: {', '.join(chars) if isinstance(chars, list) else chars}")
            preview_lines.append(f"情感基调: {node.get('emotional_tone', '')}")
            preview_lines.append(f"结尾钩子: {node.get('episode_hook', '')}")
            events = node.get("event_summaries", [])
            if events:
                preview_lines.append("事件摘要:")
                for ev in events:
                    preview_lines.append(f"  • {self._extract_event_text(ev)}")
            self._regen_preview.setPlainText("\n".join(preview_lines))
            # 归一化 event_summaries 为纯字符串列表后暂存
            normalized_node = dict(node)
            if isinstance(events, list):
                normalized_node["event_summaries"] = [
                    self._extract_event_text(e) for e in events
                ]
            self._regen_preview_node = normalized_node
            self._regen_status.setText("✅ 已生成，请在预览区检查或修改后点击「确认修改」")
        else:
            candidates = result.get("candidates")
            if candidates:
                # 兼容旧的多候选格式：取第一个有效节点
                for c in candidates:
                    n = c.get("node")
                    if n:
                        node = n
                        break
                if node:
                    preview_lines = []
                    preview_lines.append(f"标题: {node.get('title', '')}")
                    preview_lines.append(f"环境: {node.get('setting', '')}")
                    self._regen_preview.setPlainText(json.dumps(node, ensure_ascii=False, indent=2))
                    self._regen_preview_node = node
                    self._regen_status.setText("✅ 已生成，请确认修改")
                    return
            self._regen_status.setText("❌ AI 返回内容无效，原始返回已显示在预览区")
            # 显示原始返回内容供调试
            raw_text = result.get("raw_text", "")
            if raw_text:
                self._regen_preview.setPlainText(f"❌ AI 原始返回内容 (JSON解析失败):\n\n{raw_text}")
            else:
                self._regen_preview.setPlainText("❌ AI 返回了空内容")

    def _do_confirm_regen_preview(self):
        """将改写预览区的内容应用到当前版本（覆盖保存，不创建新版本）"""
        node = getattr(self, '_regen_preview_node', None)
        if not node:
            QMessageBox.warning(self, "提示", "没有可确认的改写内容，请先点击「重新生成」。")
            return
        apply_snapshot(self._node, node)
        self._load_node_to_form(node)
        # 覆盖当前版本
        update_version(self._node)
        self._refresh_version_combo()
        self._regen_status.setText("✅ 已确认修改并覆盖当前版本")
        self._regen_preview_node = None
        self.action = "saved"

    # ------------------------------------------------------------------ #
    # BVSR 重写
    # ------------------------------------------------------------------ #
    def _do_bvsr_rewrite(self):
        if self._worker:
            return
        selected = [k for k, cb in self._regen_persona_checks.items() if cb.isChecked()]
        if not selected:
            QMessageBox.information(self, "提示", "请至少选择一个人格。")
            return

        from env import (SYSTEM_PROMPT_NODE_BVSR_REWRITE, USER_PROMPT_NODE_BVSR_REWRITE,
                         DRAMA_STYLE_CONFIG)
        from services.worker import NodeRefineWorker
        from services.persona_engine import persona_engine

        style_key = self._pd.drama_style or "short_drama"
        drama_block = DRAMA_STYLE_CONFIG.get(style_key, {}).get("variation_style_block", "")
        prev_ctx, next_ctx = self._build_prev_next_context()
        n = self._node

        all_personas = persona_engine.get_all_personas()
        persona_calls = []
        for key in selected:
            p = all_personas.get(key, {})
            sys_p = (SYSTEM_PROMPT_NODE_BVSR_REWRITE
                     .replace("{persona_identity_block}", p.get("identity_block",""))
                     .replace("{hauge_stage_name}", n.get("hauge_stage_name",""))
                     .replace("{prev_context}", prev_ctx)
                     .replace("{next_context}", next_ctx)
                     .replace("{sparkle}", self._pd.sparkle or "")
                     .replace("{drama_style_block}", drama_block))
            usr_p = (USER_PROMPT_NODE_BVSR_REWRITE
                     .replace("{node_id}", n.get("node_id",""))
                     .replace("{title}", n.get("title","")))
            persona_calls.append({"persona_key": key,
                                  "system_prompt": sys_p, "user_prompt": usr_p})

        self._bvsr_status.setText(f"⏳ 启动 {len(selected)} 个人格并行重写…")
        self._bvsr_result_list.clear()
        self._worker = NodeRefineWorker(
            "bvsr_rewrite", "", "", {"temperature": 1.0, "max_tokens": 2048},
            persona_calls=persona_calls,
        )
        self._worker.finished.connect(self._on_bvsr_done)
        self._worker.error.connect(lambda e: (setattr(self, '_worker', None),
                                               self._bvsr_status.setText(f"❌ {e}")))
        self._worker.start()

    def _on_bvsr_done(self, result: dict):
        self._worker = None
        candidates = result.get("candidates", [])
        self._show_candidates(candidates)
        self._bvsr_status.setText(f"✅ {len(candidates)} 个人格候选已生成")

    def _show_candidates(self, candidates: list):
        from services.persona_engine import persona_engine
        all_personas = persona_engine.get_all_personas()
        self._bvsr_result_list.clear()
        for c in candidates:
            key = c.get("persona_key", "")
            p_name = all_personas.get(key, {}).get("name", key)
            node = c.get("node")
            if node:
                title = node.get("title", "—")
                item = QListWidgetItem(f"🎭 {p_name}\n   {title}")
                item.setData(Qt.UserRole, node)
                self._bvsr_result_list.addItem(item)
            else:
                item = QListWidgetItem(f"❌ {p_name} — {c.get('error','失败')}")
                item.setFlags(item.flags() & ~Qt.ItemIsEnabled)
                self._bvsr_result_list.addItem(item)

        # 双击触发已在 _build_regen_panel 中一次性连接

    def _on_adopt_candidate(self, item: QListWidgetItem):
        node = item.data(Qt.UserRole)
        if not node:
            return
        r = QMessageBox.question(self, "采用此版本",
                                 f"采用「{node.get('title','')}」为本集新版本？",
                                 QMessageBox.Yes | QMessageBox.No)
        if r == QMessageBox.Yes:
            apply_snapshot(self._node, node)
            self._load_node_to_form(node)
            add_version(self._node, "bvsr_rewrite", "BVSR 重写")
            self._refresh_version_combo()
            self._bvsr_status.setText("✅ 已采用并创建新版本")
