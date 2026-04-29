# ============================================================
# ui/phase2_characters.py
# Phase 2: 人物设定 — 角色创建/编辑/AI建议 + 关系管理
# ============================================================

import json
import uuid
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QSplitter, QListWidget, QListWidgetItem,
    QMessageBox, QInputDialog, QSpinBox,
)
from PySide6.QtCore import Qt, Signal

from env import (
    SYSTEM_PROMPT_CHARACTER_GEN, USER_PROMPT_CHARACTER_GEN,
    TEMPERATURE_CHARACTER_GEN,
)
from services.worker import CharacterGenWorker
from services.logger_service import app_logger
from ui.widgets.character_editor import CharacterEditor
from ui.widgets.character_relation_panel import CharacterRelationPanel
from ui.widgets.character_graph_widget import CharacterGraphWidget
from ui.widgets.ai_settings_panel import AISettingsPanel
from ui.widgets.prompt_viewer import PromptViewer


ROLE_TYPE_ICONS = {
    "主角": "⭐",
    "反派": "💀",
    "辅助": "🤝",
    "配角": "👤",
    "群演": "👥",
}

IMPORTANCE_ICONS = {"A": "★★★", "B": "★★☆", "C": "★☆☆"}


class Phase2Characters(QWidget):
    """
    Phase 2: 人物设定阶段。

    流程:
      [AI建议角色] 或 [手动添加] → 编辑角色属性 → 添加人物关系 → 确认进入Phase 3

    信号:
        phase_completed: 人物设定完成，进入骨架阶段
        go_back: 返回Phase 1
        status_message: 状态栏消息
    """

    phase_completed = Signal()
    go_back         = Signal()
    status_message  = Signal(str)

    def __init__(self, project_data, parent=None):
        super().__init__(parent)
        self.project_data = project_data
        self._worker = None
        self._setup_ui()

    # ------------------------------------------------------------------ #
    # UI
    # ------------------------------------------------------------------ #
    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(8)

        # 标题
        title = QLabel("👥 人物设定")
        title.setStyleSheet(" font-weight: bold;")
        root.addWidget(title)

        # === 主内容区（左右分割） ===
        h_splitter = QSplitter(Qt.Horizontal)

        # 左侧：角色列表
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)

        list_label = QLabel("角色列表")
        list_label.setStyleSheet("font-weight: bold;")
        ll.addWidget(list_label)

        # 列表操作按钮行
        btn_row = QHBoxLayout()
        self._btn_add = QPushButton("＋ 添加角色")
        self._btn_add.clicked.connect(self._on_add_character)
        btn_row.addWidget(self._btn_add)

        self._btn_ai = QPushButton("🤖 AI 建议角色")
        self._btn_ai.clicked.connect(self._on_ai_suggest)
        self._btn_ai.setStyleSheet(
            "QPushButton{background:#8e44ad;color:white;border:none;"
            "border-radius:4px;padding:4px 10px;}"
            "QPushButton:hover{background:#7d3c98;}"
            "QPushButton:disabled{background:#bdc3c7;}"
        )
        btn_row.addWidget(self._btn_ai)

        btn_row.addWidget(QLabel("数量:"))
        self._char_count_spin = QSpinBox()
        self._char_count_spin.setRange(1, 99)
        self._char_count_spin.setValue(15)
        self._char_count_spin.setToolTip("希望 AI 生成的角色数量")
        self._char_count_spin.setMinimumWidth(60)
        btn_row.addWidget(self._char_count_spin)

        self._btn_delete = QPushButton("－ 删除选中")
        self._btn_delete.clicked.connect(self._on_delete_character)
        self._btn_delete.setEnabled(False)
        btn_row.addWidget(self._btn_delete)

        ll.addLayout(btn_row)

        self._char_list = QListWidget()
        self._char_list.setSelectionMode(QListWidget.ExtendedSelection)
        self._char_list.currentItemChanged.connect(self._on_char_selected)
        ll.addWidget(self._char_list, 1)

        # AI设置（AI建议时用）
        self._ai_settings = AISettingsPanel(suggested_temp=TEMPERATURE_CHARACTER_GEN)
        ll.addWidget(self._ai_settings)

        self._prompt_viewer = PromptViewer()
        self._prompt_viewer.set_prompt(SYSTEM_PROMPT_CHARACTER_GEN, USER_PROMPT_CHARACTER_GEN)
        ll.addWidget(self._prompt_viewer)

        h_splitter.addWidget(left)

        # 右侧：角色详情编辑器
        self._char_editor = CharacterEditor()
        self._char_editor.character_changed.connect(self._on_character_changed)
        h_splitter.addWidget(self._char_editor)

        h_splitter.setSizes([400, 600])
        h_splitter.setStretchFactor(0, 4)
        h_splitter.setStretchFactor(1, 6)
        root.addWidget(h_splitter, 1)

        # === 关系图 + 列表双视图 ===
        self._relation_graph = CharacterGraphWidget()
        self._relation_graph.relations_changed.connect(self._on_relations_changed_graph)
        root.addWidget(self._relation_graph)

        # 保留表格面板作为 fallback（默认隐藏）
        self._relation_panel = CharacterRelationPanel()
        self._relation_panel.relations_changed.connect(self._on_relations_changed)
        self._relation_panel.setVisible(False)
        root.addWidget(self._relation_panel)

        # === 底部按钮 ===
        btn_bottom = QHBoxLayout()
        self._btn_back = QPushButton("← 返回创世")
        self._btn_back.clicked.connect(self.go_back.emit)
        btn_bottom.addWidget(self._btn_back)
        btn_bottom.addStretch()

        self._btn_skip = QPushButton("跳过（不设定角色）")
        self._btn_skip.setStyleSheet("color: #7f8c8d;")
        self._btn_skip.clicked.connect(self._on_skip)
        btn_bottom.addWidget(self._btn_skip)

        self._btn_next = QPushButton("确认人物设定，进入骨架 →")
        self._btn_next.setMinimumHeight(36)
        self._btn_next.setStyleSheet(
            "QPushButton{background:#27ae60;color:white;font-weight:bold;"
            "border-radius:5px;border:none;}"
            "QPushButton:hover{background:#229954;}"
        )
        self._btn_next.clicked.connect(self._on_proceed)
        btn_bottom.addWidget(self._btn_next)

        root.addLayout(btn_bottom)

    # ------------------------------------------------------------------ #
    # 生命周期
    # ------------------------------------------------------------------ #
    def on_enter(self):
        """从项目数据恢复角色列表"""
        self._refresh_list()
        self._relation_panel.set_characters(self.project_data.characters)
        self._relation_panel.set_relations(self.project_data.character_relations)
        self._refresh_graph()

    # ------------------------------------------------------------------ #
    # 列表操作
    # ------------------------------------------------------------------ #
    def _refresh_list(self):
        """重新构建角色列表控件"""
        self._char_list.blockSignals(True)
        self._char_list.clear()
        for char in self.project_data.characters:
            icon = ROLE_TYPE_ICONS.get(char.get("role_type", "配角"), "👤")
            imp = IMPORTANCE_ICONS.get(char.get("importance_level", "C"), "★☆☆")
            item = QListWidgetItem(f"{icon} {imp} {char.get('name', '未命名')}")
            item.setData(Qt.UserRole, char.get("char_id", ""))
            self._char_list.addItem(item)
        self._char_list.blockSignals(False)
        self._update_relation_panel_chars()

    def _update_relation_panel_chars(self):
        self._relation_panel.set_characters(self.project_data.characters)

    def _refresh_graph(self):
        """刷新力导向关系图"""
        self._relation_graph.set_data(
            self.project_data.characters,
            self.project_data.character_relations,
        )

    def _on_char_selected(self, current, previous):
        if current is None:
            self._char_editor.clear()
            self._btn_delete.setEnabled(len(self._char_list.selectedItems()) > 0)
            return
        char_id = current.data(Qt.UserRole)
        char = next((c for c in self.project_data.characters if c.get("char_id") == char_id), None)
        if char:
            self._char_editor.load_character(char)
            self._btn_delete.setEnabled(True)

    def _on_character_changed(self, updated: dict):
        """编辑器中任何字段变化时同步到数据"""
        char_id = updated.get("char_id", "")
        for i, c in enumerate(self.project_data.characters):
            if c.get("char_id") == char_id:
                self.project_data.characters[i] = updated
                # 同步刷新列表文字（名字可能变了）
                item = self._char_list.currentItem()
                if item:
                    icon = ROLE_TYPE_ICONS.get(updated.get("role_type", "配角"), "👤")
                    imp = IMPORTANCE_ICONS.get(updated.get("importance_level", "C"), "★☆☆")
                    item.setText(f"{icon} {imp} {updated.get('name', '未命名')}")
                self._update_relation_panel_chars()
                break

    def _on_add_character(self):
        new_id = f"char_{uuid.uuid4().hex[:6]}"
        new_char = {
            "char_id": new_id, "name": "新角色",
            "role_type": "配角", "importance_level": "C",
            "gender": "未知",
            "age": "", "position": "", "personality": "",
            "motivation": "", "appearance": "", "notes": "",
            # v1.1.6 新增字段
            "signature_traits": [], "arc_outline": "", "cp_role": "",
        }
        self.project_data.characters.append(new_char)
        self._refresh_list()
        # 选中新角色
        self._char_list.setCurrentRow(self._char_list.count() - 1)
        self.status_message.emit(f"已添加角色 (ID: {new_id})")

    def _on_delete_character(self):
        selected = self._char_list.selectedItems()
        if not selected:
            return
        # 收集选中的角色ID和名字
        ids_to_delete = []
        names = []
        for item in selected:
            cid = item.data(Qt.UserRole)
            ids_to_delete.append(cid)
            char = next((c for c in self.project_data.characters if c.get("char_id") == cid), None)
            names.append(char.get("name", "未命名") if char else "未命名")

        if len(names) == 1:
            msg = f"确定删除角色「{names[0]}」？"
        else:
            msg = f"确定批量删除以下 {len(names)} 个角色？\n" + "、".join(names)

        reply = QMessageBox.question(
            self, "确认删除", msg,
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.No:
            return
        delete_set = set(ids_to_delete)
        self.project_data.characters = [
            c for c in self.project_data.characters if c.get("char_id") not in delete_set
        ]
        # 删除相关关系
        self.project_data.character_relations = [
            r for r in self.project_data.character_relations
            if r.get("from_char_id") not in delete_set and r.get("to_char_id") not in delete_set
        ]
        self._char_editor.clear()
        self._btn_delete.setEnabled(False)
        self._refresh_list()
        self._relation_panel.set_relations(self.project_data.character_relations)
        self._refresh_graph()

    # ------------------------------------------------------------------ #
    # AI 建议角色
    # ------------------------------------------------------------------ #
    def _on_ai_suggest(self):
        if not self.project_data.sparkle:
            QMessageBox.warning(self, "提示", "请先完成创世阶段！")
            return
        if self.project_data.characters:
            reply = QMessageBox.question(
                self, "确认",
                "当前已有角色，AI建议的角色会追加到列表中，不会覆盖现有角色。确认继续？",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply == QMessageBox.No:
                return

        self._btn_ai.setEnabled(False)
        self._btn_ai.setText("生成中...")

        ai_params = self._ai_settings.get_all_settings()
        char_count = self._char_count_spin.value()

        # 构建实际 User Prompt（替换占位符）
        import json
        existing_block = ""
        if self.project_data.characters:
            lines = []
            for c in self.project_data.characters:
                lines.append(
                    f"- {c.get('name','?')} [{c.get('role_type','?')}/{c.get('importance_level','C')}]: "
                    f"{c.get('personality','')} / 动机: {c.get('motivation','')}"
                )
            existing_block = "## ⚠️ 已有角色（严禁重复）\n" + "\n".join(lines)

        actual_user_prompt = (
            USER_PROMPT_CHARACTER_GEN
            .replace("{sparkle}", self.project_data.sparkle)
            .replace("{world_variables_json}",
                     json.dumps(self.project_data.world_variables, ensure_ascii=False, indent=2))
            .replace("{finale_condition}", self.project_data.finale_condition)
            .replace("{char_count}", str(char_count))
            .replace("{existing_characters_block}", existing_block)
        )
        actual_system_prompt = SYSTEM_PROMPT_CHARACTER_GEN.replace("{char_count}", str(char_count))

        app_logger.log_ai_call(
            module="人物-AI建议角色",
            action=f"开始 AI 建议角色（目标数量: {char_count}）",
            system_prompt=actual_system_prompt,
            user_prompt=actual_user_prompt,
            extra_params={
                "目标角色数": char_count,
                "已有角色数": len(self.project_data.characters),
                "温度": ai_params.get("temperature"),
                "max_tokens": ai_params.get("max_tokens"),
            },
        )

        self._worker = CharacterGenWorker(
            sparkle=self.project_data.sparkle,
            world_variables=self.project_data.world_variables,
            finale_condition=self.project_data.finale_condition,
            ai_params=ai_params,
            char_count=char_count,
            existing_characters=self.project_data.characters,
        )
        self._worker.progress.connect(self.status_message)
        self._worker.finished.connect(self._on_ai_suggest_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_ai_suggest_done(self, result: dict):
        self._btn_ai.setEnabled(True)
        self._btn_ai.setText("🤖 AI 建议角色")

        new_chars = result.get("characters", [])
        new_relations = result.get("relations", [])
        notes = result.get("design_notes", "")

        # 追加角色（重新生成 ID 避免冲突，同时记录映射表）
        id_map = {}  # old_temp_id -> new_uuid_id
        for c in new_chars:
            old_id = c.get("char_id", "")
            new_id = f"char_{uuid.uuid4().hex[:6]}"
            id_map[old_id] = new_id
            # 也按名称映射（AI有时用名称作 char_id）
            id_map[c.get("name", "")] = new_id
            c["char_id"] = new_id
            # v1.1.6：补全 AI 生成角色可能缺失的新字段
            c.setdefault("signature_traits", [])
            c.setdefault("arc_outline", "")
            c.setdefault("cp_role", "")
            self.project_data.characters.append(c)

        # 追加关系 — 用映射表修正 from_char_id / to_char_id
        for r in new_relations:
            old_from = r.get("from_char_id", "")
            old_to = r.get("to_char_id", "")
            r["from_char_id"] = id_map.get(old_from, old_from)
            r["to_char_id"] = id_map.get(old_to, old_to)
            self.project_data.character_relations.append(r)

        self._refresh_list()
        self._relation_panel.set_relations(self.project_data.character_relations)
        self._refresh_graph()

        msg = f"AI 建议了 {len(new_chars)} 个角色"
        if notes:
            msg += f"\n设计说明：{notes}"
        self.status_message.emit(msg)
        QMessageBox.information(self, "AI 建议完成", msg)

        import json
        chars_detail = json.dumps(new_chars, ensure_ascii=False, indent=2)
        relations_detail = json.dumps(new_relations, ensure_ascii=False, indent=2)
        app_logger.log_ai_result(
            module="人物-AI建议角色",
            action="AI 角色建议完成",
            result_summary=f"生成 {len(new_chars)} 个角色，{len(new_relations)} 条关系" + (f"\n设计说明：{notes}" if notes else ""),
            result_detail=f"【角色列表】\n{chars_detail}\n\n【人物关系】\n{relations_detail}",
        )

    # ------------------------------------------------------------------ #
    # 关系变化
    # ------------------------------------------------------------------ #
    def _on_relations_changed(self):
        self.project_data.character_relations = self._relation_panel.get_relations()
        self._refresh_graph()

    def _on_relations_changed_graph(self):
        """关系图中编辑了关系"""
        self.project_data.character_relations = self._relation_graph.get_relations()
        self._relation_panel.set_relations(self.project_data.character_relations)

    # ------------------------------------------------------------------ #
    # 进入下一阶段 / 跳过
    # ------------------------------------------------------------------ #
    def _on_skip(self):
        reply = QMessageBox.question(
            self, "确认跳过",
            "跳过人物设定后，AI生成的剧本将使用通用角色描述，\n"
            "无法针对性地呈现角色个性。确定跳过吗？",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.project_data.current_phase = "skeleton"
            app_logger.warning("人物-跳过", "用户跳过人物设定阶段，直接进入骨架")
            self.phase_completed.emit()

    def _on_proceed(self):
        chars = self.project_data.characters
        if not chars:
            reply = QMessageBox.question(
                self, "确认",
                "当前没有设定任何角色，建议至少添加主角。\n确定进入骨架阶段吗？",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply == QMessageBox.No:
                return

        self.project_data.current_phase = "skeleton"
        self.project_data.push_history("confirm_characters")
        self.status_message.emit(
            f"人物设定完成：{len(chars)} 个角色，"
            f"{len(self.project_data.character_relations)} 条关系"
        )

        import json
        chars_summary = json.dumps(
            [{"name": c.get("name"), "role_type": c.get("role_type"),
              "importance_level": c.get("importance_level"),
              "personality": c.get("personality"), "motivation": c.get("motivation")}
             for c in chars],
            ensure_ascii=False, indent=2
        )
        relations_summary = json.dumps(self.project_data.character_relations, ensure_ascii=False, indent=2)
        app_logger.success(
            "人物-确认",
            f"人物设定已确认：{len(chars)} 个角色，{len(self.project_data.character_relations)} 条关系",
            f"【角色列表】\n{chars_summary}\n\n【人物关系】\n{relations_summary}",
        )
        self.phase_completed.emit()

    # ------------------------------------------------------------------ #
    # 错误处理
    # ------------------------------------------------------------------ #
    def _on_error(self, msg: str):
        self._btn_ai.setEnabled(True)
        self._btn_ai.setText("🤖 AI 建议角色")
        QMessageBox.critical(self, "AI 调用失败", msg)
        self.status_message.emit("错误: " + msg)
        app_logger.error("人物", f"AI 建议角色失败: {msg}")
