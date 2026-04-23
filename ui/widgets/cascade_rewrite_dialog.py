# ============================================================
# ui/widgets/cascade_rewrite_dialog.py
# 级联改写后续章节对话框
# 用户修改一个章节后，自动调整后续 N 章（最多5章）
# ============================================================

import json
import re
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSpinBox, QRadioButton, QButtonGroup, QGroupBox, QTextEdit,
    QScrollArea, QWidget, QMessageBox, QSplitter, QListWidget,
    QListWidgetItem,
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor

from models.project_state import (
    make_node_snapshot, apply_snapshot, add_version, set_active_version,
    get_active_version_snapshot,
)

# 与主骨架视图一致的阶段短名
STAGE_NAMES_SHORT = {1: "机会", 2: "变点", 3: "无路可退", 4: "挫折", 5: "高潮", 6: "终局"}
STAGE_COLORS = {1: "#dfe6e9", 2: "#ffeaa7", 3: "#fab1a0", 4: "#ff7675", 5: "#fd79a8", 6: "#a29bfe"}


class CascadeRewriteDialog(QDialog):
    """
    级联改写后续章节对话框。

    左侧: 配置面板（范围、方式、prompt、后续章节卡片）
    右侧: 改写结果展示
    """

    def __init__(self, source_node: dict, project_data, parent=None):
        super().__init__(parent)
        self._source = source_node
        self._pd = project_data
        self._worker = None
        self._rewrite_results = []

        nid = source_node.get("node_id", "")
        self.setWindowTitle(f"🔗 级联改写后续章节 — 基于 {nid} 的修改")
        self.setMinimumSize(1100, 650)
        self.setWindowFlags(self.windowFlags() | Qt.WindowMaximizeButtonHint)
        self._setup_ui()
        self._refresh_cards()

    # ================================================================== #
    # UI
    # ================================================================== #
    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)

        # 顶部来源信息
        nid = self._source.get("node_id", "")
        title = get_active_version_snapshot(self._source).get("title", "")
        src_lbl = QLabel(f"<b>修改来源:</b> {nid} — {title}")
        src_lbl.setStyleSheet(" padding:4px 0;")
        root.addWidget(src_lbl)

        # ---- 水平 Splitter: 左(配置) | 右(结果) ----
        splitter = QSplitter(Qt.Horizontal)

        # ===================== 左侧面板 =====================
        left = QWidget()
        left_v = QVBoxLayout(left)
        left_v.setContentsMargins(4, 4, 4, 4)
        left_v.setSpacing(6)

        # -- 范围 + 方式 --
        config_row = QHBoxLayout()
        config_row.addWidget(QLabel("修改范围: 后续"))
        self._range_spin = QSpinBox()
        self._range_spin.setRange(1, 5)
        self._range_spin.setValue(3)
        self._range_spin.setSuffix(" 章")
        self._range_spin.valueChanged.connect(self._refresh_cards)
        config_row.addWidget(self._range_spin)
        config_row.addStretch()
        left_v.addLayout(config_row)

        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("修改方式:"))
        self._rb_head = QRadioButton("仅调整开头衔接（结尾不变）")
        self._rb_full = QRadioButton("完整级联改写")
        self._rb_head.setChecked(True)
        mode_group = QButtonGroup(self)
        mode_group.addButton(self._rb_head)
        mode_group.addButton(self._rb_full)
        self._rb_head.toggled.connect(self._on_mode_changed)
        self._rb_full.toggled.connect(self._on_mode_changed)
        mode_row.addWidget(self._rb_head)
        mode_row.addWidget(self._rb_full)
        mode_row.addStretch()
        left_v.addLayout(mode_row)

        # -- 可折叠 Prompt 模板 --
        self._prompt_group = QGroupBox("▶ 查看 Prompt 模板")
        self._prompt_group.setCheckable(True)
        self._prompt_group.setChecked(False)
        pg_layout = QVBoxLayout(self._prompt_group)
        self._prompt_edit = QTextEdit()
        self._prompt_edit.setReadOnly(True)
        self._prompt_edit.setMaximumHeight(180)
        self._prompt_edit.setStyleSheet(" background:#f8f9fa;")
        pg_layout.addWidget(self._prompt_edit)
        self._prompt_group.toggled.connect(self._on_prompt_toggle)
        left_v.addWidget(self._prompt_group)
        self._prompt_edit.setVisible(False)

        # -- 后续章节卡片列表（与主骨架视图一致的样式）--
        left_v.addWidget(QLabel("<b>── 后续章节预览 ──</b>  <span style='color:#7f8c8d;'>(双击打开详情编辑)</span>"))
        self._card_list = QListWidget()
        self._card_list.setViewMode(QListWidget.IconMode)
        self._card_list.setResizeMode(QListWidget.Adjust)
        self._card_list.setWrapping(True)
        self._card_list.setSpacing(6)
        self._card_list.setSelectionMode(QListWidget.SingleSelection)
        self._card_list.setWordWrap(True)
        self._card_list.setIconSize(QSize(0, 0))
        self._card_list.setGridSize(QSize(200, 72))
        self._card_list.setStyleSheet("""
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
        self._card_list.itemDoubleClicked.connect(self._on_card_double_clicked)
        left_v.addWidget(self._card_list, 1)

        # -- 按钮 --
        btn_row = QHBoxLayout()
        self._btn_start = QPushButton("🔄 开始级联改写")
        self._btn_start.setFixedWidth(180)
        self._btn_start.setStyleSheet(
            "QPushButton{background:#2980b9;color:white;font-weight:bold;"
            "padding:8px 16px;border-radius:4px;border:none;}"
            "QPushButton:hover{background:#2471a3;}"
        )
        self._btn_start.clicked.connect(self._do_cascade_rewrite)
        btn_row.addWidget(self._btn_start)

        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)
        btn_row.addStretch()
        left_v.addLayout(btn_row)

        # -- 状态 --
        self._status = QLabel("")
        self._status.setStyleSheet("color:#27ae60;")
        left_v.addWidget(self._status)

        splitter.addWidget(left)

        # ===================== 右侧面板：改写结果 =====================
        right = QWidget()
        right_v = QVBoxLayout(right)
        right_v.setContentsMargins(4, 4, 4, 4)
        right_v.setSpacing(6)

        right_header = QHBoxLayout()
        right_header.addWidget(QLabel("<b>── 改写结果 ──</b>"))
        right_header.addStretch()
        self._btn_save = QPushButton("✅ 确认保存所有改写")
        self._btn_save.setStyleSheet(
            "QPushButton{background:#27ae60;color:white;font-weight:bold;"
            "padding:8px 16px;border-radius:4px;border:none;}"
            "QPushButton:hover{background:#229954;}"
        )
        self._btn_save.clicked.connect(self._do_save_all)
        self._btn_save.setEnabled(False)
        right_header.addWidget(self._btn_save)
        right_v.addLayout(right_header)

        self._result_area = QScrollArea()
        self._result_area.setWidgetResizable(True)
        self._result_container = QWidget()
        self._result_layout = QVBoxLayout(self._result_container)
        self._result_layout.setSpacing(8)
        self._result_layout.setContentsMargins(4, 4, 4, 4)
        self._result_layout.addStretch()
        self._result_area.setWidget(self._result_container)
        self._result_area.setStyleSheet("QScrollArea{background:#fafbfc;border:1px solid #dcdde1;border-radius:6px;}")
        right_v.addWidget(self._result_area, 1)

        splitter.addWidget(right)
        splitter.setSizes([480, 520])
        root.addWidget(splitter, 1)

    # ================================================================== #
    # Prompt 折叠
    # ================================================================== #
    def _on_prompt_toggle(self, checked: bool):
        self._prompt_edit.setVisible(checked)
        self._prompt_group.setTitle("▼ 收起 Prompt 模板" if checked else "▶ 查看 Prompt 模板")
        if checked:
            self._refresh_prompt_preview()

    def _on_mode_changed(self):
        """切换修改方式时刷新 prompt 预览"""
        if self._prompt_group.isChecked():
            self._refresh_prompt_preview()

    def _refresh_prompt_preview(self):
        from env import (SYSTEM_PROMPT_CASCADE_HEAD_ONLY, SYSTEM_PROMPT_CASCADE_FULL,
                         USER_PROMPT_CASCADE_REWRITE)
        if self._rb_head.isChecked():
            sys_p = self._pd.custom_cascade_head_prompt or SYSTEM_PROMPT_CASCADE_HEAD_ONLY
            mode = "仅调整开头衔接"
            custom = "（自定义）" if self._pd.custom_cascade_head_prompt else "（默认）"
        else:
            sys_p = self._pd.custom_cascade_full_prompt or SYSTEM_PROMPT_CASCADE_FULL
            mode = "完整级联改写"
            custom = "（自定义）" if self._pd.custom_cascade_full_prompt else "（默认）"
        self._prompt_edit.setPlainText(
            f"═══ 当前模式: {mode} {custom} ═══\n\n"
            f"══ System Prompt ══\n{sys_p}\n\n"
            f"══ User Prompt ══\n{USER_PROMPT_CASCADE_REWRITE}"
        )

    # ================================================================== #
    # 后续章节卡片（与主骨架视图一致样式）
    # ================================================================== #
    @staticmethod
    def _parse_ep_num(ep_id: str) -> tuple:
        nums = re.findall(r'\d+', ep_id or '')
        return tuple(int(n) for n in nums) if nums else (0,)

    def _get_sorted_nodes(self) -> list:
        return sorted(self._pd.cpg_nodes, key=lambda n: self._parse_ep_num(n.get("node_id", "")))

    def _get_subsequent_nodes(self) -> list:
        sorted_nodes = self._get_sorted_nodes()
        source_id = self._source.get("node_id", "")
        idx = -1
        for i, n in enumerate(sorted_nodes):
            if n.get("node_id") == source_id:
                idx = i
                break
        if idx < 0:
            return []
        count = self._range_spin.value()
        return sorted_nodes[idx + 1: idx + 1 + count]

    def _refresh_cards(self):
        """刷新后续章节卡片列表（与主骨架视图同款样式）"""
        self._card_list.clear()
        subsequent = self._get_subsequent_nodes()
        if not subsequent:
            item = QListWidgetItem("（没有后续章节）")
            item.setSizeHint(QSize(190, 62))
            self._card_list.addItem(item)
            return

        for node in subsequent:
            snap = get_active_version_snapshot(node)
            nid = node.get("node_id", "")
            title = snap.get("title", "")
            sid = node.get("hauge_stage_id", 1)
            stage = STAGE_NAMES_SHORT.get(sid, "")
            versions = node.get("versions", [])
            ver_tag = f"  v{node.get('active_version', 0)}" if versions else ""

            label = f"{nid}  {stage}\n{title[:14]}{ver_tag}"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, nid)
            item.setSizeHint(QSize(190, 62))
            item.setToolTip(
                f"节点: {nid}\n阶段: {stage}\n标题: {title}\n"
                f"版本: v{node.get('active_version', 0)}\n"
                f"钩子: {snap.get('episode_hook', '')}"
            )
            item.setBackground(QColor(STAGE_COLORS.get(sid, "#ffffff")))
            self._card_list.addItem(item)

    def _on_card_double_clicked(self, item: QListWidgetItem):
        """双击卡片打开节点详情对话框（可查看和编辑）"""
        node_id = item.data(Qt.UserRole)
        if not node_id:
            return
        node = next((n for n in self._pd.cpg_nodes if n.get("node_id") == node_id), None)
        if not node:
            return
        from ui.widgets.node_detail_dialog import NodeDetailDialog
        dlg = NodeDetailDialog(node, self._pd, parent=self)
        dlg.exec()
        # 刷新卡片（用户可能手动编辑了）
        self._refresh_cards()

    # ================================================================== #
    # AI 改写
    # ================================================================== #
    def _do_cascade_rewrite(self):
        if self._worker:
            return

        subsequent = self._get_subsequent_nodes()
        if not subsequent:
            QMessageBox.warning(self, "提示", "没有后续章节可改写。")
            return

        from env import (SYSTEM_PROMPT_CASCADE_HEAD_ONLY, SYSTEM_PROMPT_CASCADE_FULL,
                         USER_PROMPT_CASCADE_REWRITE, DRAMA_STYLE_CONFIG)
        from services.worker import NodeRefineWorker

        style_key = self._pd.drama_style or "short_drama"
        drama_block = DRAMA_STYLE_CONFIG.get(style_key, {}).get("variation_style_block", "")

        source_snap = get_active_version_snapshot(self._source)
        source_json = json.dumps(source_snap, ensure_ascii=False, indent=2)

        sub_nodes_data = []
        for n in subsequent:
            snap = get_active_version_snapshot(n)
            snap["node_id"] = n.get("node_id", "")
            snap["hauge_stage_name"] = n.get("hauge_stage_name", "")
            sub_nodes_data.append(snap)
        sub_json = json.dumps(sub_nodes_data, ensure_ascii=False, indent=2)

        if self._rb_head.isChecked():
            sys_template = self._pd.custom_cascade_head_prompt or SYSTEM_PROMPT_CASCADE_HEAD_ONLY
            mode_instruction = "调整开头衔接（保持结尾不变）"
        else:
            sys_template = self._pd.custom_cascade_full_prompt or SYSTEM_PROMPT_CASCADE_FULL
            mode_instruction = "进行完整级联改写"

        sys_p = (sys_template
                 .replace("{drama_style_block}", drama_block)
                 .replace("{source_node_json}", source_json)
                 .replace("{subsequent_nodes_json}", sub_json)
                 .replace("{sparkle}", self._pd.sparkle or ""))

        usr_p = (USER_PROMPT_CASCADE_REWRITE
                 .replace("{source_node_id}", self._source.get("node_id", ""))
                 .replace("{source_title}", source_snap.get("title", ""))
                 .replace("{mode_instruction}", mode_instruction)
                 .replace("{count}", str(len(subsequent))))

        # 每章完整改写约需 2500-3000 tokens
        max_tokens = max(8192, len(subsequent) * 3000)

        self._worker = NodeRefineWorker(
            "cascade_rewrite", sys_p, usr_p,
            {"temperature": 0.7, "max_tokens": min(max_tokens, 16384)}
        )

        self._status.setText(f"⏳ 正在改写 {len(subsequent)} 个后续章节…")
        self._status.setStyleSheet("color:#2980b9;")
        self._btn_start.setEnabled(False)
        self._btn_save.setEnabled(False)
        self._rewrite_results = []
        self._worker.finished.connect(self._on_cascade_done)
        self._worker.error.connect(self._on_cascade_error)
        self._worker.start()

    def _on_cascade_error(self, msg: str):
        self._worker = None
        self._btn_start.setEnabled(True)
        self._status.setText(f"❌ {msg}")
        self._status.setStyleSheet("color:#e74c3c;")

    def _on_cascade_done(self, result: dict):
        self._worker = None
        self._btn_start.setEnabled(True)
        nodes = result.get("nodes", [])
        raw_text = result.get("raw_text", "")

        if not nodes:
            self._status.setText("❌ AI 返回内容无效")
            self._status.setStyleSheet("color:#e74c3c;")
            self._clear_results()
            lbl = QLabel(f"AI 原始返回:\n{raw_text[:1000]}")
            lbl.setWordWrap(True)
            lbl.setStyleSheet("background:#fff3e0; padding:8px; border-radius:4px;")
            self._result_layout.insertWidget(0, lbl)
            return

        subsequent = self._get_subsequent_nodes()
        self._rewrite_results = []

        for i, target_node in enumerate(subsequent):
            target_nid = target_node.get("node_id", "")
            matched = None
            for ai_node in nodes:
                if ai_node.get("node_id") == target_nid:
                    matched = ai_node
                    break
            if not matched and i < len(nodes):
                matched = nodes[i]

            if matched:
                events = matched.get("event_summaries", [])
                if isinstance(events, list):
                    matched["event_summaries"] = [
                        self._extract_event_text(e) for e in events
                    ]
                self._rewrite_results.append({
                    "node": target_node,
                    "new_data": matched,
                })

        self._show_results()
        count = len(self._rewrite_results)
        self._status.setText(f"✅ 已生成 {count} 个章节的改写方案，请检查后点击右侧「确认保存」")
        self._status.setStyleSheet("color:#27ae60;")
        self._btn_save.setEnabled(True)

    # ================================================================== #
    # 结果展示
    # ================================================================== #
    def _clear_results(self):
        while self._result_layout.count():
            item = self._result_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _show_results(self):
        self._clear_results()
        for item in self._rewrite_results:
            card = self._make_result_card(item["node"], item["new_data"])
            self._result_layout.addWidget(card)
        self._result_layout.addStretch()

    def _make_result_card(self, original_node: dict, new_data: dict) -> QWidget:
        """创建改写结果卡片"""
        card = QWidget()
        card.setStyleSheet(
            "QWidget{background:#f0fff0;border:1px solid #27ae60;"
            "border-radius:6px;padding:6px;}"
        )
        v = QVBoxLayout(card)
        v.setSpacing(3)
        v.setContentsMargins(8, 6, 8, 6)

        nid = original_node.get("node_id", "")
        old_snap = get_active_version_snapshot(original_node)
        old_title = old_snap.get("title", "")
        new_title = new_data.get("title", "")

        header = QLabel(f"<b>{nid}</b> ✅ 已改写")
        header.setStyleSheet(" color:#27ae60;")
        v.addWidget(header)

        if old_title != new_title:
            v.addWidget(QLabel(f"<span style='color:#95a5a6;'>旧标题:</span> <s>{old_title}</s>"))
            v.addWidget(QLabel(f"<span style='color:#27ae60;'>新标题:</span> <b>{new_title}</b>"))
        else:
            v.addWidget(QLabel(f"<span style=''>标题: {new_title} (未变)</span>"))

        # 环境
        new_setting = new_data.get("setting", "")
        if new_setting:
            s_lbl = QLabel(f"<span style='color:#7f8c8d;'>环境:</span> {new_setting[:60]}")
            s_lbl.setWordWrap(True)
            v.addWidget(s_lbl)

        # 新事件
        new_events = new_data.get("event_summaries", [])
        if new_events:
            v.addWidget(QLabel("<span style='color:#2c3e50;'>事件摘要:</span>"))
            for ev in new_events[:5]:
                ev_text = self._extract_event_text(ev)
                display = ev_text[:80] + ("…" if len(str(ev_text)) > 80 else "")
                lbl = QLabel(f"  • {display}")
                lbl.setWordWrap(True)
                lbl.setStyleSheet(" color:#34495e; border:none;")
                v.addWidget(lbl)
            if len(new_events) > 5:
                more = QLabel(f"<span style='color:#95a5a6;'>… 共 {len(new_events)} 个事件</span>")
                more.setStyleSheet("border:none;")
                v.addWidget(more)

        # 新钩子
        new_hook = new_data.get("episode_hook", "")
        if new_hook:
            hook_lbl = QLabel(f"🎣 {new_hook[:100]}{'…' if len(new_hook)>100 else ''}")
            hook_lbl.setWordWrap(True)
            hook_lbl.setStyleSheet(" color:#e67e22; border:none;")
            v.addWidget(hook_lbl)

        return card

    @staticmethod
    def _extract_event_text(ev) -> str:
        if isinstance(ev, str):
            return ev
        if isinstance(ev, dict):
            for key in ("description", "event", "summary", "text"):
                if key in ev:
                    return str(ev[key])
            for val in ev.values():
                if isinstance(val, str) and len(val) > 10:
                    return val
        return str(ev)

    # ================================================================== #
    # 保存
    # ================================================================== #
    def _do_save_all(self):
        if not self._rewrite_results:
            return

        r = QMessageBox.question(
            self, "确认保存",
            f"将为 {len(self._rewrite_results)} 个后续章节各创建一个新版本并激活。\n"
            f"旧版本内容不受影响，可随时切换。\n\n确认保存？",
            QMessageBox.Yes | QMessageBox.No
        )
        if r != QMessageBox.Yes:
            return

        saved_ids = []
        for item in self._rewrite_results:
            node = item["node"]
            new_data = item["new_data"]
            apply_snapshot(node, new_data)
            mode_label = "级联衔接" if self._rb_head.isChecked() else "级联改写"
            ver_id = add_version(node, "cascade_rewrite", mode_label)
            set_active_version(node, ver_id)
            saved_ids.append(node.get("node_id", ""))

        self._status.setText(f"✅ 已保存: {', '.join(saved_ids)}")
        self._status.setStyleSheet("color:#27ae60;")
        self._btn_save.setEnabled(False)

        QMessageBox.information(
            self, "保存成功",
            f"已为以下章节创建新版本并激活:\n{', '.join(saved_ids)}\n\n"
            f"旧版本内容不受影响，可在节点详情中通过版本下拉切换。"
        )
        self.accept()
