# ============================================================
# ui/widgets/character_editor.py
# 角色详情编辑器 — Phase 2 右侧使用
# 选中角色后在此编辑姓名、性格、职位等属性
# ============================================================

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QComboBox, QTextEdit, QPushButton,
    QGroupBox, QFrame,
)
from PySide6.QtCore import Qt, Signal


class CharacterEditor(QWidget):
    """
    角色详情编辑器。
    联动角色列表：点击列表中的角色后，此处显示/编辑该角色属性。

    信号:
        character_changed: 任何字段修改后发出，参数为更新后的角色 dict
    """

    character_changed = Signal(dict)

    ROLE_TYPES  = ["主角", "反派", "辅助", "配角", "群演"]
    GENDERS     = ["男", "女", "其他", "未知"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_char_id: str = ""
        self._block_signals = False
        self._setup_ui()
        self._set_enabled(False)

    # ------------------------------------------------------------------ #
    # UI
    # ------------------------------------------------------------------ #
    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        group = QGroupBox("角色详情编辑")
        gl = QVBoxLayout(group)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        # 姓名
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("必填，如：李明")
        self._name_edit.textChanged.connect(self._emit_change)
        form.addRow("姓名：", self._name_edit)

        # 角色类型
        self._role_combo = QComboBox()
        self._role_combo.addItems(self.ROLE_TYPES)
        self._role_combo.currentIndexChanged.connect(self._emit_change)
        form.addRow("类型：", self._role_combo)

        # 性别 + 年龄（同行）
        ga_row = QHBoxLayout()
        self._gender_combo = QComboBox()
        self._gender_combo.addItems(self.GENDERS)
        self._gender_combo.currentIndexChanged.connect(self._emit_change)
        ga_row.addWidget(self._gender_combo)
        ga_row.addWidget(QLabel("年龄："))
        self._age_edit = QLineEdit()
        self._age_edit.setPlaceholderText("如 25 或 中年")
        self._age_edit.setMaximumWidth(80)
        self._age_edit.textChanged.connect(self._emit_change)
        ga_row.addWidget(self._age_edit)
        form.addRow("性别：", ga_row)

        # 职位/身份
        self._position_edit = QLineEdit()
        self._position_edit.setPlaceholderText(
            "如：宫廷侍卫长、前朝公主、废土猎人……"
        )
        self._position_edit.textChanged.connect(self._emit_change)
        form.addRow("职位/身份：", self._position_edit)

        # 性格特征
        self._personality_edit = QLineEdit()
        self._personality_edit.setPlaceholderText(
            "2-5个关键词，用顿号分隔，如：机敏、隐忍、内心矛盾"
        )
        self._personality_edit.textChanged.connect(self._emit_change)
        form.addRow("性格特征：", self._personality_edit)

        # 核心动机
        self._motivation_edit = QTextEdit()
        self._motivation_edit.setPlaceholderText(
            "这个角色最想达成什么？如：推翻父亲的暴政，为母亲复仇"
        )
        self._motivation_edit.setMaximumHeight(60)
        self._motivation_edit.textChanged.connect(self._emit_change)
        form.addRow("核心动机：", self._motivation_edit)

        # 外貌特征
        self._appearance_edit = QLineEdit()
        self._appearance_edit.setPlaceholderText(
            "关键外貌特征，如：清瘦少年，左手有烧伤疤痕"
        )
        self._appearance_edit.textChanged.connect(self._emit_change)
        form.addRow("外貌特征：", self._appearance_edit)

        # 备注
        self._notes_edit = QTextEdit()
        self._notes_edit.setPlaceholderText("其他补充说明（自然语言，随意填写）")
        self._notes_edit.setMaximumHeight(72)
        self._notes_edit.textChanged.connect(self._emit_change)
        form.addRow("备注：", self._notes_edit)

        gl.addLayout(form)

        # 分隔提示
        tip = QLabel(
            "💡 提示：角色信息将自动注入到骨架生成和剧本扩写的 AI 提示词中"
        )
        tip.setStyleSheet("color: #7f8c8d; font-size: 11px; margin-top: 4px;")
        tip.setWordWrap(True)
        gl.addWidget(tip)

        root.addWidget(group)

    # ------------------------------------------------------------------ #
    # 公开接口
    # ------------------------------------------------------------------ #
    def load_character(self, char_dict: dict):
        """从 dict 加载角色数据到表单"""
        self._current_char_id = char_dict.get("char_id", "")
        self._block_signals = True

        self._name_edit.setText(char_dict.get("name", ""))

        role = char_dict.get("role_type", "配角")
        idx = self.ROLE_TYPES.index(role) if role in self.ROLE_TYPES else 3
        self._role_combo.setCurrentIndex(idx)

        gender = char_dict.get("gender", "未知")
        gidx = self.GENDERS.index(gender) if gender in self.GENDERS else 3
        self._gender_combo.setCurrentIndex(gidx)

        self._age_edit.setText(char_dict.get("age", ""))
        self._position_edit.setText(char_dict.get("position", ""))
        self._personality_edit.setText(char_dict.get("personality", ""))
        self._motivation_edit.setPlainText(char_dict.get("motivation", ""))
        self._appearance_edit.setText(char_dict.get("appearance", ""))
        self._notes_edit.setPlainText(char_dict.get("notes", ""))

        self._block_signals = False
        self._set_enabled(True)

    def clear(self):
        """清空表单"""
        self._current_char_id = ""
        self._block_signals = True
        self._name_edit.clear()
        self._role_combo.setCurrentIndex(3)
        self._gender_combo.setCurrentIndex(3)
        self._age_edit.clear()
        self._position_edit.clear()
        self._personality_edit.clear()
        self._motivation_edit.clear()
        self._appearance_edit.clear()
        self._notes_edit.clear()
        self._block_signals = False
        self._set_enabled(False)

    def get_current_dict(self) -> dict:
        """读取表单当前值，返回 dict"""
        return {
            "char_id":      self._current_char_id,
            "name":         self._name_edit.text().strip(),
            "role_type":    self._role_combo.currentText(),
            "gender":       self._gender_combo.currentText(),
            "age":          self._age_edit.text().strip(),
            "position":     self._position_edit.text().strip(),
            "personality":  self._personality_edit.text().strip(),
            "motivation":   self._motivation_edit.toPlainText().strip(),
            "appearance":   self._appearance_edit.text().strip(),
            "notes":        self._notes_edit.toPlainText().strip(),
        }

    # ------------------------------------------------------------------ #
    # 内部
    # ------------------------------------------------------------------ #
    def _emit_change(self):
        if self._block_signals or not self._current_char_id:
            return
        self.character_changed.emit(self.get_current_dict())

    def _set_enabled(self, enabled: bool):
        for w in [
            self._name_edit, self._role_combo, self._gender_combo,
            self._age_edit, self._position_edit, self._personality_edit,
            self._motivation_edit, self._appearance_edit, self._notes_edit,
        ]:
            w.setEnabled(enabled)
