# ============================================================
# ui/widgets/cp_settings_dialog.py
# CP 互动模板设置 & 预览对话框
# ============================================================

import json
import os

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QSplitter,
    QListWidget, QListWidgetItem, QPushButton, QLabel,
    QTextEdit, QLineEdit, QGroupBox, QWidget, QComboBox,
    QDialogButtonBox, QFrame,
)
from PySide6.QtCore import Qt


_TEMPLATE_PATH = "config/cp_interaction_templates.json"

_GENRE_LABEL = {
    "fantasy_thriller": "奇幻/悬疑",
    "rebirth_revenge":  "重生/复仇",
    "modern_sweet":     "现代甜宠",
    "urban_counterattack": "都市逆袭",
}


def _load_templates() -> dict:
    if not os.path.exists(_TEMPLATE_PATH):
        return {}
    try:
        with open(_TEMPLATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _parse_adapt_tags(tags: list) -> dict:
    result = {}
    for tag in (tags or []):
        if not isinstance(tag, str):
            continue
        for sep in ("：", ":"):
            if sep in tag:
                k, _, v = tag.partition(sep)
                result[k.strip()] = v.strip()
                break
    return result


def _collect_all_templates(data: dict) -> list:
    """从完整 JSON 中提取所有模板，返回 list of (section_label, tpl)"""
    result = []
    core = data.get("core_basic_library", {})
    for cat, val in core.items():
        if isinstance(val, dict):
            for tpl in val.get("templates", []):
                result.append(("核心通用 · " + cat, tpl))
        elif isinstance(val, list):
            for tpl in val:
                result.append(("核心通用 · " + cat, tpl))

    genre_lib = data.get("genre_exclusive_library", {})
    for genre_key, genre_val in genre_lib.items():
        label = _GENRE_LABEL.get(genre_key, genre_key)
        if isinstance(genre_val, dict):
            for tpl in genre_val.get("templates", []):
                result.append((label, tpl))
        elif isinstance(genre_val, list):
            for tpl in genre_val:
                result.append((label, tpl))
    return result


class CPSettingsDialog(QDialog):
    """
    CP 互动模板设置 & 预览对话框。
    左侧：当前项目 CP 状态 + 模板列表（可按题材筛选）
    右侧：选中模板的完整内容预览
    """

    def __init__(self, project_data=None, parent=None):
        super().__init__(parent)
        self._project_data = project_data
        self._all_templates: list = []   # [(section_label, tpl_dict), ...]
        self._filtered: list = []

        self.setWindowTitle("CP 互动模板设置")
        self.setMinimumSize(960, 640)
        self._load_data()
        self._setup_ui()
        self._refresh_filter()

    # ------------------------------------------------------------------ #

    def _load_data(self):
        raw = _load_templates()
        self._all_templates = _collect_all_templates(raw)

    # ------------------------------------------------------------------ #
    # UI
    # ------------------------------------------------------------------ #
    def _setup_ui(self):
        root = QVBoxLayout(self)

        # 顶部说明
        tip = QLabel(
            "CP 互动模板库（来源：config/cp_interaction_templates.json）。\n"
            "血肉阶段生成时，系统自动从题材匹配的模板中抽取一条注入 AI Prompt，要求 AI 在本集内使用。"
        )
        tip.setWordWrap(True)
        tip.setStyleSheet("color:#636e72; padding:4px 0;")
        root.addWidget(tip)

        # ── 状态栏 ──
        status_group = QGroupBox("当前项目 CP 状态")
        sg_layout = QHBoxLayout(status_group)

        has_cp = bool(self._project_data and getattr(self._project_data, "has_cp_main_line", False))
        status_text = "✅ 已启用（在「创世」阶段勾选了「含男女主 CP 主线」）" if has_cp \
            else "❌ 未启用（若需开启，请在「创世」阶段勾选「含男女主 CP 主线」）"
        status_lbl = QLabel(status_text)
        status_lbl.setStyleSheet(
            "color:#27ae60;font-weight:bold;" if has_cp else "color:#e74c3c;"
        )
        sg_layout.addWidget(status_lbl)

        sg_layout.addSpacing(24)

        role_a = self._derive_role("A")
        role_b = self._derive_role("B")
        role_lbl = QLabel(f"CP角色：{role_a or '（未设定）'} × {role_b or '（未设定）'}")
        role_lbl.setStyleSheet("color:#2c3e50;")
        sg_layout.addWidget(role_lbl)
        sg_layout.addStretch()

        count_lbl = QLabel(f"模板库共 {len(self._all_templates)} 条")
        count_lbl.setStyleSheet("color:#7f8c8d;")
        sg_layout.addWidget(count_lbl)

        root.addWidget(status_group)

        # ── 主体分割 ──
        splitter = QSplitter(Qt.Horizontal)

        # ---- 左侧：筛选 + 列表 ----
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 4, 0)

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("题材筛选："))
        self._genre_combo = QComboBox()
        self._genre_combo.addItem("全部题材", "__all__")
        self._genre_combo.addItem("核心通用", "__core__")
        for k, v in _GENRE_LABEL.items():
            self._genre_combo.addItem(v, k)
        self._genre_combo.currentIndexChanged.connect(self._refresh_filter)
        filter_row.addWidget(self._genre_combo, 1)
        lv.addLayout(filter_row)

        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("关键词："))
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("搜索模板内容…")
        self._search_edit.textChanged.connect(self._refresh_filter)
        search_row.addWidget(self._search_edit, 1)
        lv.addLayout(search_row)

        self._count_lbl = QLabel("")
        self._count_lbl.setStyleSheet("color:#7f8c8d; font-size:11px;")
        lv.addWidget(self._count_lbl)

        self._list = QListWidget()
        self._list.setAlternatingRowColors(True)
        self._list.currentRowChanged.connect(self._on_selection_changed)
        lv.addWidget(self._list, 1)

        left.setMinimumWidth(320)
        splitter.addWidget(left)

        # ---- 右侧：预览 ----
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(4, 0, 0, 0)

        rv.addWidget(QLabel("模板详情："))

        self._id_lbl = QLabel("ID：—")
        self._id_lbl.setStyleSheet("color:#7f8c8d; font-size:11px;")
        rv.addWidget(self._id_lbl)

        self._section_lbl = QLabel("分类：—")
        self._section_lbl.setStyleSheet("color:#7f8c8d; font-size:11px;")
        rv.addWidget(self._section_lbl)

        self._tags_lbl = QLabel("标签：—")
        self._tags_lbl.setStyleSheet("color:#7f8c8d; font-size:11px;")
        self._tags_lbl.setWordWrap(True)
        rv.addWidget(self._tags_lbl)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color:#ddd;")
        rv.addWidget(sep)

        rv.addWidget(QLabel("模板原文（{role_a}/{role_b}/{scene} 为占位符）："))
        self._content_edit = QTextEdit()
        self._content_edit.setReadOnly(True)
        self._content_edit.setStyleSheet(
            "QTextEdit{background:#fafafa;border:1px solid #dcdde1;"
            "border-radius:4px;padding:8px;"
            "font-family:'Microsoft YaHei','Noto Sans CJK SC',sans-serif;}"
        )
        rv.addWidget(self._content_edit, 1)

        # 渲染预览（用项目角色名替换占位符）
        rv.addWidget(QLabel("渲染预览（使用项目 CP 角色名）："))
        self._rendered_edit = QTextEdit()
        self._rendered_edit.setReadOnly(True)
        self._rendered_edit.setMaximumHeight(120)
        self._rendered_edit.setStyleSheet(
            "QTextEdit{background:#eafaf1;border:1px solid #a9dfbf;"
            "border-radius:4px;padding:8px;"
            "font-family:'Microsoft YaHei','Noto Sans CJK SC',sans-serif;}"
        )
        rv.addWidget(self._rendered_edit)

        splitter.addWidget(right)
        splitter.setSizes([340, 580])
        root.addWidget(splitter, 1)

        # 底部按钮
        btn_box = QDialogButtonBox(QDialogButtonBox.Close)
        btn_box.rejected.connect(self.reject)
        root.addWidget(btn_box)

    # ------------------------------------------------------------------ #
    # 数据
    # ------------------------------------------------------------------ #
    def _derive_role(self, role: str) -> str:
        if not self._project_data:
            return ""
        attr = f"cp_role_{role.lower()}"
        explicit = getattr(self._project_data, attr, "") or ""
        if explicit:
            return explicit
        for c in (getattr(self._project_data, "characters", None) or []):
            cp_role = c.get("cp_role", "") if isinstance(c, dict) else getattr(c, "cp_role", "")
            name = c.get("name", "") if isinstance(c, dict) else getattr(c, "name", "")
            if cp_role == role:
                return name
        return ""

    def _refresh_filter(self):
        genre_key = self._genre_combo.currentData()
        keyword = self._search_edit.text().strip().lower()

        filtered = []
        for section, tpl in self._all_templates:
            if genre_key != "__all__":
                if genre_key == "__core__":
                    if "核心通用" not in section:
                        continue
                else:
                    label = _GENRE_LABEL.get(genre_key, genre_key)
                    if not section.startswith(label):
                        continue
            if keyword:
                content = tpl.get("content", tpl.get("template", ""))
                tags = " ".join(tpl.get("adapt_tags", []))
                if keyword not in content.lower() and keyword not in tags.lower():
                    continue
            filtered.append((section, tpl))

        self._filtered = filtered
        self._list.clear()
        for section, tpl in filtered:
            tpl_id = tpl.get("id", "unknown")
            tags_dict = _parse_adapt_tags(tpl.get("adapt_tags", []))
            hook_type = tags_dict.get("hook_type", "")
            phase = tags_dict.get("hauge_phase", "")
            label = f"[{section}] {tpl_id}"
            if hook_type:
                label += f"  ·{hook_type}"
            if phase:
                label += f"  P{phase}"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, len(self._list))
            self._list.addItem(item)

        self._count_lbl.setText(f"共 {len(filtered)} 条")
        if filtered:
            self._list.setCurrentRow(0)

    def _on_selection_changed(self, row: int):
        if row < 0 or row >= len(self._filtered):
            self._content_edit.clear()
            self._rendered_edit.clear()
            self._id_lbl.setText("ID：—")
            self._section_lbl.setText("分类：—")
            self._tags_lbl.setText("标签：—")
            return

        section, tpl = self._filtered[row]
        tpl_id = tpl.get("id", "unknown")
        content = tpl.get("content", tpl.get("template", ""))
        adapt_tags = tpl.get("adapt_tags", [])

        self._id_lbl.setText(f"ID：{tpl_id}")
        self._section_lbl.setText(f"分类：{section}")
        self._tags_lbl.setText(f"标签：{' | '.join(adapt_tags) if adapt_tags else '（无）'}")
        self._content_edit.setPlainText(content)

        role_a = self._derive_role("A") or "{role_a}"
        role_b = self._derive_role("B") or "{role_b}"
        rendered = content.replace("{role_a}", role_a).replace("{role_b}", role_b).replace("{scene}", "（场景）")
        self._rendered_edit.setPlainText(rendered)
