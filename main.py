# ============================================================
# main.py
# 程序入口：初始化 QApplication，启动主窗口
# ============================================================

import sys
import os
import logging

# 将项目根目录加入 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont

from ui.main_window import MainWindow


def setup_logging():
    """配置日志"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def ensure_directories():
    """确保必要的目录存在"""
    dirs = ["projects", "vector_db", "key"]
    for d in dirs:
        os.makedirs(d, exist_ok=True)


def main():
    setup_logging()
    ensure_directories()

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    # 设置默认字体
    font = QFont("Microsoft YaHei", 10)
    app.setFont(font)

    # 设置全局样式
    app.setStyleSheet("""
        QMainWindow {
            background-color: #f5f6fa;
        }
        QGroupBox {
            font-weight: bold;
            border: 1px solid #dcdde1;
            border-radius: 6px;
            margin-top: 8px;
            padding-top: 16px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 12px;
            padding: 0 4px;
        }
        QPushButton {
            padding: 6px 16px;
            border-radius: 4px;
            border: 1px solid #dcdde1;
            background-color: white;
        }
        QPushButton:hover {
            background-color: #f0f0f0;
        }
        QComboBox {
            padding: 4px 8px;
            border: 1px solid #dcdde1;
            border-radius: 4px;
        }
        QTextEdit {
            border: 1px solid #dcdde1;
            border-radius: 4px;
            padding: 4px;
        }
        QLineEdit {
            padding: 4px 8px;
            border: 1px solid #dcdde1;
            border-radius: 4px;
        }
    """)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
