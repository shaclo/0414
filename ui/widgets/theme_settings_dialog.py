# ============================================================
# ui/widgets/theme_settings_dialog.py
# 主题设置对话框：字体选择 + 配色方案选择（热切换）
# ============================================================

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QSpinBox, QGroupBox, QScrollArea,
    QWidget, QFrame, QComboBox, QSizePolicy,
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QFont, QColor, QPainter, QBrush, QFontDatabase

from services.theme_manager import theme_manager, THEME_PRESETS


class ColorSwatchWidget(QFrame):
    """显示一组色块的小预览条"""

    def __init__(self, colors: list, parent=None):
        super().__init__(parent)
        self._colors = colors
        self.setFixedHeight(22)
        self.setMinimumWidth(80)

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self._colors:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w = self.width() // len(self._colors)
        for i, color in enumerate(self._colors):
            painter.fillRect(i * w, 0, w, self.height(), QColor(color))
        painter.end()


class ThemeCard(QFrame):
    """单个主题的卡片（名称 + 色条预览 + 选中高亮）"""

    def __init__(self, theme_key: str, theme_data: dict, parent=None):
        super().__init__(parent)
        self.theme_key = theme_key
        self._selected = False
        self.setFixedSize(150, 80)
        self.setCursor(Qt.PointingHandCursor)
        self.setFrameShape(QFrame.StyledPanel)
        self._setup_ui(theme_data)
        self._update_style()

    def _setup_ui(self, theme_data: dict):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        name_lbl = QLabel(theme_data["label"])
        name_lbl.setAlignment(Qt.AlignCenter)
        name_lbl.setStyleSheet(" font-weight: bold; background: transparent;")
        name_lbl.setWordWrap(True)
        layout.addWidget(name_lbl)

        swatch = ColorSwatchWidget(theme_data.get("preview_colors", []))
        layout.addWidget(swatch)

        dark_tag = QLabel("🌙 暗色" if theme_data.get("dark") else "☀️ 浅色")
        dark_tag.setAlignment(Qt.AlignCenter)
        dark_tag.setStyleSheet(" color: #888; background: transparent;")
        layout.addWidget(dark_tag)

    def set_selected(self, selected: bool):
        self._selected = selected
        self._update_style()

    def _update_style(self):
        if self._selected:
            self.setStyleSheet(
                "ThemeCard {"
                "  border: 2px solid #3498db;"
                "  border-radius: 8px;"
                "  background-color: rgba(52, 152, 219, 0.15);"
                "}"
            )
        else:
            self.setStyleSheet(
                "ThemeCard {"
                "  border: 1px solid #dcdde1;"
                "  border-radius: 8px;"
                "  background-color: transparent;"
                "}"
                "ThemeCard:hover {"
                "  border: 1px solid #3498db;"
                "}"
            )

    def mousePressEvent(self, event):
        self.parent_dialog().on_theme_card_clicked(self.theme_key)

    def parent_dialog(self):
        w = self.parent()
        while w:
            if isinstance(w, ThemeSettingsDialog):
                return w
            w = w.parent()
        return None


class ThemeSettingsDialog(QDialog):
    """
    主题设置对话框。

    布局：
        上方 — 字体设置（字体选择 + 字号 + 实时预览）
        下方 — 配色方案（10个主题卡片，点击即热切换）
        底部 — 确定 / 重置默认 / 取消
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🎨 主题设置")
        # 添加最大化按钮
        self.setWindowFlags(
            Qt.Window |
            Qt.WindowTitleHint |
            Qt.WindowCloseButtonHint |
            Qt.WindowMaximizeButtonHint |
            Qt.WindowMinimizeButtonHint
        )
        self.resize(900, 660)
        self.setMinimumSize(700, 520)

        # 记录打开时的原始设置，以便"取消"时恢复
        self._original_theme = theme_manager.get_current_theme_key()
        self._original_font_family, self._original_font_size = theme_manager.get_current_font()

        # 当前选中的卡片 key
        self._selected_key = self._original_theme
        self._theme_cards: dict = {}

        self._setup_ui()
        self._restore_current()

    # ------------------------------------------------------------------ #
    # UI 构建
    # ------------------------------------------------------------------ #
    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        # 标题
        title = QLabel("🎨 界面主题与字体设置")
        title.setStyleSheet(" font-weight: bold; background: transparent;")
        root.addWidget(title)

        desc = QLabel("所有设置立即生效，无需重启程序。")
        desc.setStyleSheet("color: #7f8c8d; background: transparent;")
        root.addWidget(desc)

        # ===== 字体设置 =====
        font_group = QGroupBox("✏️ 字体设置")
        font_layout = QVBoxLayout(font_group)
        font_layout.setSpacing(8)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("字体:"))

        # 从本地字体库获取所有字体，常用中文字体排首
        self._font_combo = QComboBox()
        self._font_combo.setMinimumWidth(220)
        self._font_combo.setMaximumWidth(320)
        self._font_combo.setEditable(False)  # 纯下拉菜单，不可手动输入
        self._font_combo.setMaxVisibleItems(20)

        # 优先显示的常用中文字体
        priority_fonts = [
            "Microsoft YaHei", "微软雅黑",
            "SimSun", "宋体",
            "SimHei", "黑体",
            "KaiTi", "楷体",
            "FangSong", "仳宋",
            "Source Han Sans CN", "Noto Sans CJK SC",
            "Microsoft JhengHei",
        ]
        db = QFontDatabase()
        all_families = set(db.families())

        added = set()
        # 先添加常用中文字体（如果系统存在）
        for f in priority_fonts:
            if f in all_families and f not in added:
                self._font_combo.addItem(f)
                added.add(f)

        if added:
            self._font_combo.insertSeparator(len(added))

        # 再添加其他字体（按字母排序）
        for f in sorted(all_families):
            if f not in added:
                self._font_combo.addItem(f)

        # 定位到当前字体
        idx = self._font_combo.findText(self._original_font_family)
        self._font_combo.setCurrentIndex(idx if idx >= 0 else 0)

        self._font_combo.currentIndexChanged.connect(self._on_font_changed)
        row1.addWidget(self._font_combo)

        row1.addWidget(QLabel("  字号:"))
        self._size_spin = QSpinBox()
        self._size_spin.setRange(8, 24)
        self._size_spin.setValue(self._original_font_size)
        self._size_spin.setSuffix(" pt")
        self._size_spin.setFixedWidth(200)
        self._size_spin.valueChanged.connect(self._on_font_changed)
        row1.addWidget(self._size_spin)
        row1.addStretch()
        font_layout.addLayout(row1)

        # 预览文本
        preview_box = QFrame()
        preview_box.setFrameShape(QFrame.StyledPanel)
        preview_box.setFixedHeight(52)
        preview_layout = QVBoxLayout(preview_box)
        preview_layout.setContentsMargins(8, 4, 8, 4)
        self._preview_label = QLabel("预览文字 — 短剧剧本生成器  Preview Text 0123456789")
        self._preview_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        self._preview_label.setStyleSheet("background: transparent;")
        preview_layout.addWidget(self._preview_label)
        font_layout.addWidget(preview_box)

        root.addWidget(font_group)

        # ===== 配色方案 =====
        theme_group = QGroupBox("🎨 配色主题（点击即时切换）")
        theme_v = QVBoxLayout(theme_group)

        # 滚动区域 + 卡片网格（两行，每行10个主题）
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setFixedHeight(290)

        from PySide6.QtWidgets import QGridLayout
        cards_widget = QWidget()
        cards_layout = QGridLayout(cards_widget)
        cards_layout.setContentsMargins(4, 4, 4, 4)
        cards_layout.setSpacing(10)

        theme_keys = list(THEME_PRESETS.keys())
        cols = 5  # 每行5个
        for idx, (key, data) in enumerate(THEME_PRESETS.items()):
            card = ThemeCard(key, data, parent=self)
            self._theme_cards[key] = card
            row, col = divmod(idx, cols)
            cards_layout.addWidget(card, row, col)

        scroll.setWidget(cards_widget)
        theme_v.addWidget(scroll)

        # 当前主题名称显示
        self._current_theme_label = QLabel()
        self._current_theme_label.setStyleSheet(
            " color: #2980b9; font-weight: bold; background: transparent;"
        )
        theme_v.addWidget(self._current_theme_label)

        root.addWidget(theme_group)
        root.addStretch()

        # ===== 底部按钮 =====
        bottom = QHBoxLayout()

        btn_reset = QPushButton("🔄 恢复默认")
        btn_reset.setFixedWidth(110)
        btn_reset.clicked.connect(self._on_reset)
        bottom.addWidget(btn_reset)

        bottom.addStretch()

        btn_ok = QPushButton("✅ 确定")
        btn_ok.setFixedWidth(90)
        btn_ok.setStyleSheet(
            "QPushButton{background:#27ae60;color:white;border:none;"
            "border-radius:4px;padding:6px 14px;font-weight:bold;}"
            "QPushButton:hover{background:#229954;}"
        )
        btn_ok.clicked.connect(self.accept)
        bottom.addWidget(btn_ok)

        btn_cancel = QPushButton("取消")
        btn_cancel.setFixedWidth(70)
        btn_cancel.clicked.connect(self._on_cancel)
        bottom.addWidget(btn_cancel)

        root.addLayout(bottom)

    # ------------------------------------------------------------------ #
    # 恢复当前状态到 UI
    # ------------------------------------------------------------------ #
    def _restore_current(self):
        # 更新卡片选中状态
        self._select_card(self._selected_key)
        # 更新预览字体
        self._update_preview_font()

    def _select_card(self, key: str):
        for k, card in self._theme_cards.items():
            card.set_selected(k == key)
        self._selected_key = key
        theme_data = THEME_PRESETS.get(key, {})
        self._current_theme_label.setText(
            f"当前主题: {theme_data.get('label', key)}"
        )

    # ------------------------------------------------------------------ #
    # 事件处理
    # ------------------------------------------------------------------ #
    def on_theme_card_clicked(self, key: str):
        """卡片点击 → 热切换主题"""
        self._select_card(key)
        theme_manager.apply_theme(key)

    def _on_font_changed(self):
        """字体/字号变化 → 热切换字体"""
        family = self._font_combo.currentText()
        size = self._size_spin.value()
        if family and not family.startswith("-"):  # 跳过分隔符
            theme_manager.apply_font(family, size)
            self._update_preview_font()

    def _update_preview_font(self):
        family = self._font_combo.currentText()
        size = self._size_spin.value()
        if family and not family.startswith("-"):
            self._preview_label.setFont(QFont(family, size))

    def _on_reset(self):
        """重置为默认设置"""
        idx = self._font_combo.findText("Microsoft YaHei")
        self._font_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._size_spin.setValue(10)
        self.on_theme_card_clicked("default_light")
        theme_manager.apply_font("Microsoft YaHei", 10)

    def _on_cancel(self):
        """取消 → 恢复原始设置"""
        theme_manager.apply_theme(self._original_theme, save=False)
        theme_manager.apply_font(self._original_font_family, self._original_font_size, save=False)
        self.reject()

    def closeEvent(self, event):
        """关闭窗口时保存当前设置（等同于确定）"""
        theme_manager.save_settings()
        super().closeEvent(event)
