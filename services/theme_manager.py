# ============================================================
# services/theme_manager.py
# 主题管理器：10种配色方案 + 字体设置 + 热切换 + 持久化
# ============================================================

import json
import os
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont

# ====================================================================
# 15 种配色方案：8 浅色 + 7 暗色，均衡搭配
# ====================================================================
THEME_PRESETS = {

    # ==================== 浅色主题（8种）====================

    "default_light": {
        "label": "☀️ 默认浅色",
        "dark": False,
        "window_bg":       "#f5f6fa",
        "surface":         "#ffffff",
        "text_primary":    "#2c3e50",
        "text_secondary":  "#7f8c8d",
        "accent":          "#2980b9",
        "accent_hover":    "#1f6da8",
        "success":         "#27ae60",
        "success_hover":   "#229954",
        "warning":         "#e67e22",
        "danger":          "#e74c3c",
        "border":          "#dcdde1",
        "nav_bg":          "#1a252f",
        "nav_text":        "#7f8c8d",
        "nav_active":      "#3498db",
        "nav_sep":         "#4a6278",
        "statusbar_bg":    "#ecf0f1",
        "statusbar_text":  "#555555",
        "input_bg":        "#ffffff",
        "disabled_bg":     "#bdc3c7",
        "disabled_text":   "#888888",
        "groupbox_border": "#dcdde1",
        "list_selected_bg":"#3498db",
        "list_selected_fg":"#ffffff",
        "scroll_handle":   "#b2bec3",
        "preview_colors":  ["#f5f6fa", "#ffffff", "#2980b9", "#27ae60", "#1a252f"],
    },
    "github_light": {
        "label": "☀️ GitHub 浅色",
        "dark": False,
        "window_bg":       "#f6f8fa",
        "surface":         "#ffffff",
        "text_primary":    "#24292f",
        "text_secondary":  "#57606a",
        "accent":          "#0969da",
        "accent_hover":    "#0758c0",
        "success":         "#1a7f37",
        "success_hover":   "#146b2e",
        "warning":         "#9a6700",
        "danger":          "#cf222e",
        "border":          "#d0d7de",
        "nav_bg":          "#24292f",
        "nav_text":        "#8c959f",
        "nav_active":      "#58a6ff",
        "nav_sep":         "#3d444d",
        "statusbar_bg":    "#f6f8fa",
        "statusbar_text":  "#57606a",
        "input_bg":        "#ffffff",
        "disabled_bg":     "#d0d7de",
        "disabled_text":   "#8c959f",
        "groupbox_border": "#d0d7de",
        "list_selected_bg":"#0969da",
        "list_selected_fg":"#ffffff",
        "scroll_handle":   "#c8ccd0",
        "preview_colors":  ["#f6f8fa", "#ffffff", "#0969da", "#1a7f37", "#24292f"],
    },
    "solarized_light": {
        "label": "☀️ Solarized 暖光",
        "dark": False,
        "window_bg":       "#fdf6e3",
        "surface":         "#eee8d5",
        "text_primary":    "#586e75",
        "text_secondary":  "#93a1a1",
        "accent":          "#268bd2",
        "accent_hover":    "#1a7ac0",
        "success":         "#859900",
        "success_hover":   "#6b7b00",
        "warning":         "#b58900",
        "danger":          "#dc322f",
        "border":          "#ddd8c4",
        "nav_bg":          "#073642",
        "nav_text":        "#839496",
        "nav_active":      "#268bd2",
        "nav_sep":         "#0a4555",
        "statusbar_bg":    "#eee8d5",
        "statusbar_text":  "#657b83",
        "input_bg":        "#fdf6e3",
        "disabled_bg":     "#ddd8c4",
        "disabled_text":   "#93a1a1",
        "groupbox_border": "#ddd8c4",
        "list_selected_bg":"#268bd2",
        "list_selected_fg":"#fdf6e3",
        "scroll_handle":   "#ccc8b4",
        "preview_colors":  ["#fdf6e3", "#eee8d5", "#268bd2", "#859900", "#073642"],
    },
    "catppuccin": {
        "label": "☀️ Catppuccin 奶茶",
        "dark": False,
        "window_bg":       "#eff1f5",
        "surface":         "#e6e9ef",
        "text_primary":    "#4c4f69",
        "text_secondary":  "#8c8fa1",
        "accent":          "#1e66f5",
        "accent_hover":    "#0d59e8",
        "success":         "#40a02b",
        "success_hover":   "#318c21",
        "warning":         "#df8e1d",
        "danger":          "#d20f39",
        "border":          "#ccd0da",
        "nav_bg":          "#4c4f69",
        "nav_text":        "#9ca0b0",
        "nav_active":      "#1e66f5",
        "nav_sep":         "#6c6f85",
        "statusbar_bg":    "#e6e9ef",
        "statusbar_text":  "#6c6f85",
        "input_bg":        "#eff1f5",
        "disabled_bg":     "#ccd0da",
        "disabled_text":   "#8c8fa1",
        "groupbox_border": "#ccd0da",
        "list_selected_bg":"#1e66f5",
        "list_selected_fg":"#eff1f5",
        "scroll_handle":   "#bcc0cc",
        "preview_colors":  ["#eff1f5", "#e6e9ef", "#1e66f5", "#40a02b", "#4c4f69"],
    },
    "gruvbox_light": {
        "label": "☀️ Gruvbox 暖纸",
        "dark": False,
        "window_bg":       "#f9f5d7",
        "surface":         "#fbf1c7",
        "text_primary":    "#3c3836",
        "text_secondary":  "#7c6f64",
        "accent":          "#076678",
        "accent_hover":    "#044f5c",
        "success":         "#79740e",
        "success_hover":   "#5a5408",
        "warning":         "#b57614",
        "danger":          "#9d0006",
        "border":          "#d5c4a1",
        "nav_bg":          "#3c3836",
        "nav_text":        "#a89984",
        "nav_active":      "#458588",
        "nav_sep":         "#504945",
        "statusbar_bg":    "#ebdbb2",
        "statusbar_text":  "#7c6f64",
        "input_bg":        "#fbf1c7",
        "disabled_bg":     "#d5c4a1",
        "disabled_text":   "#a89984",
        "groupbox_border": "#d5c4a1",
        "list_selected_bg":"#076678",
        "list_selected_fg":"#fbf1c7",
        "scroll_handle":   "#bdae93",
        "preview_colors":  ["#f9f5d7", "#fbf1c7", "#076678", "#79740e", "#3c3836"],
    },
    "ayu_light": {
        "label": "☀️ Ayu 极简白",
        "dark": False,
        "window_bg":       "#fafafa",
        "surface":         "#ffffff",
        "text_primary":    "#575f66",
        "text_secondary":  "#abb0b6",
        "accent":          "#399ee6",
        "accent_hover":    "#2080cc",
        "success":         "#86b300",
        "success_hover":   "#6a8f00",
        "warning":         "#f29718",
        "danger":          "#f07171",
        "border":          "#d9d8d7",
        "nav_bg":          "#f8f9fa",
        "nav_text":        "#abb0b6",
        "nav_active":      "#399ee6",
        "nav_sep":         "#d9d8d7",
        "statusbar_bg":    "#f0f0f0",
        "statusbar_text":  "#8a9199",
        "input_bg":        "#ffffff",
        "disabled_bg":     "#e7e8e9",
        "disabled_text":   "#abb0b6",
        "groupbox_border": "#d9d8d7",
        "list_selected_bg":"#399ee6",
        "list_selected_fg":"#ffffff",
        "scroll_handle":   "#c8c8c8",
        "preview_colors":  ["#fafafa", "#ffffff", "#399ee6", "#86b300", "#f8f9fa"],
    },
    "warm_ivory": {
        "label": "☀️ 象牙米白",
        "dark": False,
        "window_bg":       "#faf8f2",
        "surface":         "#f2efe6",
        "text_primary":    "#3d3629",
        "text_secondary":  "#8a7e6a",
        "accent":          "#8b5e3c",
        "accent_hover":    "#6e4a2e",
        "success":         "#5a7a2e",
        "success_hover":   "#466020",
        "warning":         "#c48a1a",
        "danger":          "#b53a2a",
        "border":          "#d9d2c0",
        "nav_bg":          "#3d3629",
        "nav_text":        "#8a7e6a",
        "nav_active":      "#c49a6c",
        "nav_sep":         "#5a5040",
        "statusbar_bg":    "#ece8dc",
        "statusbar_text":  "#6a5e4a",
        "input_bg":        "#faf8f2",
        "disabled_bg":     "#d9d2c0",
        "disabled_text":   "#a09080",
        "groupbox_border": "#d9d2c0",
        "list_selected_bg":"#8b5e3c",
        "list_selected_fg":"#faf8f2",
        "scroll_handle":   "#c8c0aa",
        "preview_colors":  ["#faf8f2", "#f2efe6", "#8b5e3c", "#5a7a2e", "#3d3629"],
    },
    "high_contrast_light": {
        "label": "☀️ 高对比 白底黑字",
        "dark": False,
        "window_bg":       "#ffffff",
        "surface":         "#f0f0f0",
        "text_primary":    "#000000",
        "text_secondary":  "#333333",
        "accent":          "#0000cc",
        "accent_hover":    "#0000aa",
        "success":         "#006600",
        "success_hover":   "#004d00",
        "warning":         "#884400",
        "danger":          "#cc0000",
        "border":          "#000000",
        "nav_bg":          "#000000",
        "nav_text":        "#bbbbbb",
        "nav_active":      "#ffffff",
        "nav_sep":         "#555555",
        "statusbar_bg":    "#e0e0e0",
        "statusbar_text":  "#000000",
        "input_bg":        "#ffffff",
        "disabled_bg":     "#cccccc",
        "disabled_text":   "#666666",
        "groupbox_border": "#000000",
        "list_selected_bg":"#0000cc",
        "list_selected_fg":"#ffffff",
        "scroll_handle":   "#999999",
        "preview_colors":  ["#ffffff", "#f0f0f0", "#000000", "#0000cc", "#000000"],
    },

    # ==================== 暗色主题（7种）====================

    "one_dark": {
        "label": "🌙 One Dark Pro",
        "dark": True,
        "window_bg":       "#21252b",
        "surface":         "#282c34",
        "text_primary":    "#abb2bf",
        "text_secondary":  "#636d83",
        "accent":          "#61afef",
        "accent_hover":    "#4d9fdf",
        "success":         "#98c379",
        "success_hover":   "#82ad63",
        "warning":         "#e5c07b",
        "danger":          "#e06c75",
        "border":          "#3e4451",
        "nav_bg":          "#181a1f",
        "nav_text":        "#636d83",
        "nav_active":      "#61afef",
        "nav_sep":         "#3e4451",
        "statusbar_bg":    "#181a1f",
        "statusbar_text":  "#636d83",
        "input_bg":        "#282c34",
        "disabled_bg":     "#3e4451",
        "disabled_text":   "#636d83",
        "groupbox_border": "#3e4451",
        "list_selected_bg":"#61afef",
        "list_selected_fg":"#282c34",
        "scroll_handle":   "#3e4451",
        "preview_colors":  ["#21252b", "#282c34", "#61afef", "#98c379", "#181a1f"],
    },
    "nord": {
        "label": "🌙 Nord 极光",
        "dark": True,
        "window_bg":       "#2e3440",
        "surface":         "#3b4252",
        "text_primary":    "#eceff4",
        "text_secondary":  "#9099aa",
        "accent":          "#88c0d0",
        "accent_hover":    "#6db0c4",
        "success":         "#a3be8c",
        "success_hover":   "#8aaa72",
        "warning":         "#ebcb8b",
        "danger":          "#bf616a",
        "border":          "#4c566a",
        "nav_bg":          "#242933",
        "nav_text":        "#616e88",
        "nav_active":      "#88c0d0",
        "nav_sep":         "#4c566a",
        "statusbar_bg":    "#242933",
        "statusbar_text":  "#9099aa",
        "input_bg":        "#3b4252",
        "disabled_bg":     "#4c566a",
        "disabled_text":   "#616e88",
        "groupbox_border": "#4c566a",
        "list_selected_bg":"#88c0d0",
        "list_selected_fg":"#2e3440",
        "scroll_handle":   "#4c566a",
        "preview_colors":  ["#2e3440", "#3b4252", "#88c0d0", "#a3be8c", "#242933"],
    },
    "dracula": {
        "label": "🌙 Dracula 暗紫",
        "dark": True,
        "window_bg":       "#1e1f29",
        "surface":         "#282a36",
        "text_primary":    "#f8f8f2",
        "text_secondary":  "#6272a4",
        "accent":          "#bd93f9",
        "accent_hover":    "#a57fe8",
        "success":         "#50fa7b",
        "success_hover":   "#3de468",
        "warning":         "#ffb86c",
        "danger":          "#ff5555",
        "border":          "#44475a",
        "nav_bg":          "#191a21",
        "nav_text":        "#6272a4",
        "nav_active":      "#bd93f9",
        "nav_sep":         "#44475a",
        "statusbar_bg":    "#191a21",
        "statusbar_text":  "#6272a4",
        "input_bg":        "#282a36",
        "disabled_bg":     "#44475a",
        "disabled_text":   "#6272a4",
        "groupbox_border": "#44475a",
        "list_selected_bg":"#bd93f9",
        "list_selected_fg":"#282a36",
        "scroll_handle":   "#44475a",
        "preview_colors":  ["#1e1f29", "#282a36", "#bd93f9", "#50fa7b", "#191a21"],
    },
    "tokyo_night": {
        "label": "🌙 Tokyo Night",
        "dark": True,
        "window_bg":       "#1a1b26",
        "surface":         "#24283b",
        "text_primary":    "#c0caf5",
        "text_secondary":  "#565f89",
        "accent":          "#7aa2f7",
        "accent_hover":    "#5d87e8",
        "success":         "#9ece6a",
        "success_hover":   "#82b853",
        "warning":         "#e0af68",
        "danger":          "#f7768e",
        "border":          "#3b4261",
        "nav_bg":          "#16161e",
        "nav_text":        "#565f89",
        "nav_active":      "#7aa2f7",
        "nav_sep":         "#3b4261",
        "statusbar_bg":    "#16161e",
        "statusbar_text":  "#565f89",
        "input_bg":        "#24283b",
        "disabled_bg":     "#3b4261",
        "disabled_text":   "#565f89",
        "groupbox_border": "#3b4261",
        "list_selected_bg":"#7aa2f7",
        "list_selected_fg":"#1a1b26",
        "scroll_handle":   "#3b4261",
        "preview_colors":  ["#1a1b26", "#24283b", "#7aa2f7", "#9ece6a", "#16161e"],
    },
    "monokai": {
        "label": "🌙 Monokai 炫彩",
        "dark": True,
        "window_bg":       "#1e1e1e",
        "surface":         "#272822",
        "text_primary":    "#f8f8f2",
        "text_secondary":  "#75715e",
        "accent":          "#f92672",
        "accent_hover":    "#e0155e",
        "success":         "#a6e22e",
        "success_hover":   "#8fca1c",
        "warning":         "#e6db74",
        "danger":          "#f92672",
        "border":          "#3e3d32",
        "nav_bg":          "#191919",
        "nav_text":        "#75715e",
        "nav_active":      "#f92672",
        "nav_sep":         "#3e3d32",
        "statusbar_bg":    "#191919",
        "statusbar_text":  "#75715e",
        "input_bg":        "#272822",
        "disabled_bg":     "#3e3d32",
        "disabled_text":   "#75715e",
        "groupbox_border": "#3e3d32",
        "list_selected_bg":"#f92672",
        "list_selected_fg":"#f8f8f2",
        "scroll_handle":   "#3e3d32",
        "preview_colors":  ["#1e1e1e", "#272822", "#f92672", "#a6e22e", "#191919"],
    },
    "kanagawa": {
        "label": "🌙 Kanagawa 浮世绘",
        "dark": True,
        "window_bg":       "#1f1f28",
        "surface":         "#2a2a37",
        "text_primary":    "#dcd7ba",
        "text_secondary":  "#727169",
        "accent":          "#7e9cd8",
        "accent_hover":    "#6488c0",
        "success":         "#98bb6c",
        "success_hover":   "#7da055",
        "warning":         "#dca561",
        "danger":          "#c34043",
        "border":          "#363646",
        "nav_bg":          "#16161d",
        "nav_text":        "#54546d",
        "nav_active":      "#7e9cd8",
        "nav_sep":         "#363646",
        "statusbar_bg":    "#16161d",
        "statusbar_text":  "#727169",
        "input_bg":        "#2a2a37",
        "disabled_bg":     "#363646",
        "disabled_text":   "#54546d",
        "groupbox_border": "#363646",
        "list_selected_bg":"#7e9cd8",
        "list_selected_fg":"#1f1f28",
        "scroll_handle":   "#363646",
        "preview_colors":  ["#1f1f28", "#2a2a37", "#7e9cd8", "#98bb6c", "#16161d"],
    },
    "retro_green": {
        "label": "⚡ 高反差 黑底绿字",
        "dark": True,
        "window_bg":       "#0a0f0a",
        "surface":         "#0d140d",
        "text_primary":    "#33ff33",
        "text_secondary":  "#1a9e1a",
        "accent":          "#00ff41",
        "accent_hover":    "#00cc33",
        "success":         "#00ff41",
        "success_hover":   "#00cc33",
        "warning":         "#ffff00",
        "danger":          "#ff3333",
        "border":          "#1a4d1a",
        "nav_bg":          "#050a05",
        "nav_text":        "#1a6b1a",
        "nav_active":      "#00ff41",
        "nav_sep":         "#1a4d1a",
        "statusbar_bg":    "#050a05",
        "statusbar_text":  "#1a9e1a",
        "input_bg":        "#0d140d",
        "disabled_bg":     "#0d1a0d",
        "disabled_text":   "#1a4d1a",
        "groupbox_border": "#1a4d1a",
        "list_selected_bg":"#00ff41",
        "list_selected_fg":"#050a05",
        "scroll_handle":   "#1a4d1a",
        "preview_colors":  ["#0a0f0a", "#0d140d", "#33ff33", "#00ff41", "#050a05"],
    },
}


# 可选字体列表（中英文均常见）
FONT_FAMILIES = [
    "Microsoft YaHei",
    "微软雅黑",
    "SimSun",
    "SimHei",
    "KaiTi",
    "FangSong",
    "Source Han Sans CN",
    "Noto Sans CJK SC",
    "Arial",
    "Segoe UI",
    "Consolas",
    "Courier New",
    "Calibri",
    "Tahoma",
    "Verdana",
]

CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "config", "theme_settings.json"
)


def _generate_stylesheet(p: dict, font_family: str = "Microsoft YaHei", font_size: int = 10) -> str:
    """根据调色板 p 和字体参数生成全局 Qt stylesheet。
    
    字体规则说明：在每个具体控件选择器里都写明 font-family/font-size，
    而不只写在 QWidget 上——因为 widget.setStyleSheet() 的优先级高于
    app.setStyleSheet() 中的 QWidget 规则，只有同级别选择器（如 QLabel）
    才能正确覆盖。
    """
    return f"""
QMainWindow, QDialog {{
    background-color: {p['window_bg']};
}}
QWidget {{
    background-color: {p['window_bg']};
    color: {p['text_primary']};
    font-family: "{font_family}";
    font-size: {font_size}pt;
}}
QLabel {{
    color: {p['text_primary']};
    background-color: transparent;
    font-family: "{font_family}";
    font-size: {font_size}pt;
}}
QCheckBox {{
    color: {p['text_primary']};
    background-color: transparent;
    font-family: "{font_family}";
    font-size: {font_size}pt;
}}
QRadioButton {{
    color: {p['text_primary']};
    background-color: transparent;
    font-family: "{font_family}";
    font-size: {font_size}pt;
}}
QGroupBox {{
    font-weight: bold;
    font-family: "{font_family}";
    font-size: {font_size}pt;
    border: 1px solid {p['groupbox_border']};
    border-radius: 6px;
    margin-top: 8px;
    padding-top: 16px;
    color: {p['text_primary']};
    background-color: {p['window_bg']};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 4px;
    color: {p['text_primary']};
}}
QPushButton {{
    padding: 6px 16px;
    border-radius: 4px;
    border: 1px solid {p['border']};
    background-color: {p['surface']};
    color: {p['text_primary']};
    font-family: "{font_family}";
    font-size: {font_size}pt;
}}
QPushButton:hover {{
    background-color: {p['accent']};
    color: #ffffff;
    border: 1px solid {p['accent']};
}}
QPushButton:disabled {{
    background-color: {p['disabled_bg']};
    color: {p['disabled_text']};
    border: 1px solid {p['border']};
}}
QComboBox {{
    padding: 4px 8px;
    border: 1px solid {p['border']};
    border-radius: 4px;
    background-color: {p['input_bg']};
    color: {p['text_primary']};
    font-family: "{font_family}";
    font-size: {font_size}pt;
}}
QComboBox::drop-down {{
    border: none;
}}
QComboBox QAbstractItemView {{
    background-color: {p['surface']};
    color: {p['text_primary']};
    border: 1px solid {p['border']};
    selection-background-color: {p['list_selected_bg']};
    selection-color: {p['list_selected_fg']};
    font-family: "{font_family}";
    font-size: {font_size}pt;
}}
QTextEdit {{
    border: 1px solid {p['border']};
    border-radius: 4px;
    padding: 4px;
    background-color: {p['input_bg']};
    color: {p['text_primary']};
    font-family: "{font_family}";
    font-size: {font_size}pt;
}}
QPlainTextEdit {{
    border: 1px solid {p['border']};
    border-radius: 4px;
    padding: 4px;
    background-color: {p['input_bg']};
    color: {p['text_primary']};
    font-family: "{font_family}";
    font-size: {font_size}pt;
}}
QLineEdit {{
    padding: 4px 8px;
    border: 1px solid {p['border']};
    border-radius: 4px;
    background-color: {p['input_bg']};
    color: {p['text_primary']};
    font-family: "{font_family}";
    font-size: {font_size}pt;
}}
QSpinBox {{
    padding: 3px 6px;
    border: 1px solid {p['border']};
    border-radius: 4px;
    background-color: {p['input_bg']};
    color: {p['text_primary']};
    font-family: "{font_family}";
    font-size: {font_size}pt;
}}
QListWidget {{
    background-color: {p['surface']};
    color: {p['text_primary']};
    border: 1px solid {p['border']};
    border-radius: 4px;
    font-family: "{font_family}";
    font-size: {font_size}pt;
}}
QListWidget::item:selected {{
    background-color: {p['list_selected_bg']};
    color: {p['list_selected_fg']};
}}
QListWidget::item:hover {{
    background-color: {p['accent']};
    color: #ffffff;
}}
QTableWidget {{
    background-color: {p['surface']};
    color: {p['text_primary']};
    gridline-color: {p['border']};
    border: 1px solid {p['border']};
    font-family: "{font_family}";
    font-size: {font_size}pt;
}}
QTableWidget::item:selected {{
    background-color: {p['list_selected_bg']};
    color: {p['list_selected_fg']};
}}
QHeaderView::section {{
    background-color: {p['window_bg']};
    color: {p['text_primary']};
    border: 1px solid {p['border']};
    padding: 4px;
    font-family: "{font_family}";
    font-size: {font_size}pt;
}}
QScrollBar:vertical {{
    background: {p['window_bg']};
    width: 10px;
    border: none;
}}
QScrollBar::handle:vertical {{
    background: {p['scroll_handle']};
    border-radius: 5px;
    min-height: 20px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}
QScrollBar:horizontal {{
    background: {p['window_bg']};
    height: 10px;
    border: none;
}}
QScrollBar::handle:horizontal {{
    background: {p['scroll_handle']};
    border-radius: 5px;
    min-width: 20px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}
QSplitter::handle {{
    background: {p['border']};
}}
QTabWidget::pane {{
    border: 1px solid {p['border']};
    background-color: {p['surface']};
}}
QTabBar::tab {{
    background-color: {p['window_bg']};
    color: {p['text_secondary']};
    padding: 6px 14px;
    border: 1px solid {p['border']};
    border-bottom: none;
    font-family: "{font_family}";
    font-size: {font_size}pt;
}}
QTabBar::tab:selected {{
    background-color: {p['surface']};
    color: {p['text_primary']};
}}
QStatusBar {{
    background: {p['statusbar_bg']};
    color: {p['statusbar_text']};
    border-top: 1px solid {p['border']};
    font-family: "{font_family}";
    font-size: {font_size}pt;
}}
QMenuBar {{
    background-color: {p['nav_bg']};
    color: {p['nav_text']};
    font-family: "{font_family}";
    font-size: {font_size}pt;
}}
QMenuBar::item:selected {{
    background-color: {p['accent']};
    color: #ffffff;
}}
QMenu {{
    background-color: {p['surface']};
    color: {p['text_primary']};
    border: 1px solid {p['border']};
    font-family: "{font_family}";
    font-size: {font_size}pt;
}}
QMenu::item:selected {{
    background-color: {p['list_selected_bg']};
    color: {p['list_selected_fg']};
}}
QToolTip {{
    background-color: {p['surface']};
    color: {p['text_primary']};
    border: 1px solid {p['border']};
    padding: 4px;
    font-family: "{font_family}";
    font-size: {font_size}pt;
}}
QProgressBar {{
    border: 1px solid {p['border']};
    border-radius: 4px;
    text-align: center;
    background-color: {p['surface']};
    color: {p['text_primary']};
    font-family: "{font_family}";
    font-size: {font_size}pt;
}}
QProgressBar::chunk {{
    background-color: {p['success']};
    border-radius: 3px;
}}
QFontComboBox {{
    padding: 4px 8px;
    border: 1px solid {p['border']};
    border-radius: 4px;
    background-color: {p['input_bg']};
    color: {p['text_primary']};
    font-family: "{font_family}";
    font-size: {font_size}pt;
}}
"""


class ThemeManager:
    """
    全局主题管理器（单例）。
    负责管理配色方案和字体，支持热切换。
    """

    def __init__(self):
        self._current_theme: str = "default_light"
        self._current_font_family: str = "Microsoft YaHei"
        self._current_font_size: int = 10
        self._nav_style_callback = None   # 主窗口注册的导航栏刷新回调

    # ------------------------------------------------------------------ #
    # 主题切换
    # ------------------------------------------------------------------ #
    def apply_theme(self, theme_key: str, save: bool = True):
        """切换配色主题（热切换，无需重启）"""
        if theme_key not in THEME_PRESETS:
            theme_key = "default_light"
        self._current_theme = theme_key
        self._rebuild_stylesheet()
        if save:
            self.save_settings()

    def apply_font(self, family: str, size: int, save: bool = True):
        """切换字体（热切换，无需重启）——字体写入全局 stylesheet 确保所有 Widget 立即生效"""
        self._current_font_family = family
        self._current_font_size = size
        self._rebuild_stylesheet()
        if save:
            self.save_settings()

    def _rebuild_stylesheet(self):
        """重新生成包含当前字体的全局 stylesheet 并应用到 QApplication"""
        palette = THEME_PRESETS.get(self._current_theme, THEME_PRESETS["default_light"])
        stylesheet = _generate_stylesheet(
            palette,
            font_family=self._current_font_family,
            font_size=self._current_font_size,
        )
        app = QApplication.instance()
        if app:
            # 同时设置 QFont 保持 QDialog/QMessageBox 等原生控件一致
            app.setFont(QFont(self._current_font_family, self._current_font_size))
            app.setStyleSheet(stylesheet)
        # 通知导航栏刷新颜色
        if self._nav_style_callback:
            self._nav_style_callback(palette)

    def apply_all(self):
        """应用当前存储的主题和字体（启动时调用）"""
        self._rebuild_stylesheet()

    # ------------------------------------------------------------------ #
    # 导航栏回调注册
    # ------------------------------------------------------------------ #
    def register_nav_callback(self, callback):
        """主窗口注册导航栏颜色刷新回调，切换主题时自动调用"""
        self._nav_style_callback = callback

    # ------------------------------------------------------------------ #
    # 当前状态查询
    # ------------------------------------------------------------------ #
    def get_current_theme_key(self) -> str:
        return self._current_theme

    def get_current_theme(self) -> dict:
        return THEME_PRESETS.get(self._current_theme, THEME_PRESETS["default_light"])

    def get_current_font(self) -> tuple:
        return self._current_font_family, self._current_font_size

    def get_color(self, color_name: str) -> str:
        """返回当前主题的指定颜色值"""
        palette = self.get_current_theme()
        return palette.get(color_name, "#000000")

    # ------------------------------------------------------------------ #
    # 持久化
    # ------------------------------------------------------------------ #
    def save_settings(self):
        """保存当前设置到 config/theme_settings.json"""
        try:
            os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
            data = {
                "theme":       self._current_theme,
                "font_family": self._current_font_family,
                "font_size":   self._current_font_size,
            }
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def load_settings(self):
        """从 config/theme_settings.json 加载设置"""
        try:
            if os.path.exists(CONFIG_PATH):
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._current_theme = data.get("theme", "default_light")
                self._current_font_family = data.get("font_family", "Microsoft YaHei")
                self._current_font_size = int(data.get("font_size", 10))
        except Exception:
            pass


# 全局单例
theme_manager = ThemeManager()
