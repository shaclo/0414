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
    dirs = ["projects", "vector_db", "key", "config"]
    for d in dirs:
        os.makedirs(d, exist_ok=True)


def main():
    setup_logging()
    ensure_directories()

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    # 加载并应用主题（字体 + 配色），支持持久化恢复上次设置
    from services.theme_manager import theme_manager
    theme_manager.load_settings()
    theme_manager.apply_all()

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
