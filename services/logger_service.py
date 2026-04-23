# ============================================================
# services/logger_service.py
# 应用日志服务 — 统一记录所有用户操作和 AI 调用
# 日志文件存储在 logs/YYYY-MM-DD.log，UTF-8 编码
# ============================================================

import os
import datetime
from collections import deque
from PySide6.QtCore import QObject, Signal


class AppLogger(QObject):
    """
    全局单例日志服务。

    用法:
        from services.logger_service import app_logger
        app_logger.info("创世", "用户输入种子：xxx")
        app_logger.success("骨架", "CPG 骨架生成完成，共 20 个节点")
        app_logger.error("血肉", "AI 调用失败：连接超时")

    日志文件: logs/YYYY-MM-DD.log
    """

    # 有新日志写入时通知 UI 刷新
    new_log_entry = Signal(str)   # 发出格式化后的日志行

    LEVELS = {
        "信息": "INFO",
        "成功": "SUCCESS",
        "警告": "WARNING",
        "错误": "ERROR",
    }

    # 每次会话最多在内存保留条数
    MAX_BUFFER = 1000

    def __init__(self):
        super().__init__()
        self._buffer: deque = deque(maxlen=self.MAX_BUFFER)
        self._log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
        os.makedirs(self._log_dir, exist_ok=True)

    # ------------------------------------------------------------------ #
    # 公开接口
    # ------------------------------------------------------------------ #
    def info(self, module: str, message: str, detail: str = ""):
        """记录信息级别日志"""
        self._write("信息", module, message, detail)

    def success(self, module: str, message: str, detail: str = ""):
        """记录成功级别日志"""
        self._write("成功", module, message, detail)

    def warning(self, module: str, message: str, detail: str = ""):
        """记录警告级别日志"""
        self._write("警告", module, message, detail)

    def error(self, module: str, message: str, detail: str = ""):
        """记录错误级别日志"""
        self._write("错误", module, message, detail)

    def log_ai_call(self, module: str, action: str,
                    system_prompt: str, user_prompt: str,
                    extra_params: dict = None):
        """
        记录完整的 AI 调用参数（System Prompt + User Prompt 完整内容）。

        参数:
            module:        模块名，如 "创世-苏格拉底盘问"
            action:        动作描述，如 "发起 AI 调用"
            system_prompt: 完整系统提示词
            user_prompt:   完整用户提示词（已替换占位符）
            extra_params:  额外参数字典（温度、max_tokens 等）
        """
        params_str = ""
        if extra_params:
            params_str = "  参数: " + ", ".join(f"{k}={v}" for k, v in extra_params.items())

        detail_lines = [
            "━" * 60,
            f"【系统提示词 System Prompt】",
            system_prompt.strip(),
            "━" * 40,
            f"【用户提示词 User Prompt】",
            user_prompt.strip(),
            "━" * 60,
        ]
        if params_str:
            detail_lines.insert(0, params_str)

        detail = "\n".join(detail_lines)
        self._write("信息", module, action, detail)

    def log_ai_result(self, module: str, action: str, result_summary: str, result_detail: str = ""):
        """
        记录 AI 返回结果摘要和（可选的）完整返回内容。

        参数:
            module:         模块名
            action:         动作描述
            result_summary: 简短摘要，如 "返回 10 个问题"
            result_detail:  完整返回内容（JSON 或文本）
        """
        detail = result_summary
        if result_detail:
            detail = result_summary + "\n" + "━" * 40 + "\n【完整返回内容】\n" + result_detail.strip()
        self._write("成功", module, action, detail)

    def get_buffer(self) -> list:
        """获取内存缓冲中的日志条目列表（供 UI 初始加载）"""
        return list(self._buffer)

    def get_log_files(self) -> list:
        """获取 logs/ 目录下所有日志文件路径列表，按日期倒序"""
        try:
            files = [
                os.path.join(self._log_dir, f)
                for f in os.listdir(self._log_dir)
                if f.endswith(".log")
            ]
            return sorted(files, reverse=True)
        except Exception:
            return []

    def get_log_dir(self) -> str:
        return self._log_dir

    # ------------------------------------------------------------------ #
    # 内部实现
    # ------------------------------------------------------------------ #
    def _write(self, level: str, module: str, message: str, detail: str = ""):
        now = datetime.datetime.now()
        time_str = now.strftime("%H:%M:%S")
        date_str = now.strftime("%Y-%m-%d")

        # 格式化主行
        header_line = f"[{time_str}] [{level}] [{module}] {message}"

        # 如果有 detail，附加缩进的详情块
        if detail:
            detail_indented = "\n".join("    " + line for line in detail.splitlines())
            full_entry = header_line + "\n" + detail_indented
        else:
            full_entry = header_line

        # 写入内存缓冲
        self._buffer.append(full_entry)

        # 写入磁盘
        log_path = os.path.join(self._log_dir, f"{date_str}.log")
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(full_entry + "\n")
        except Exception:
            pass  # 日志写入失败不影响主程序

        # 通知 UI
        try:
            self.new_log_entry.emit(full_entry)
        except Exception:
            pass


# 全局单例
app_logger = AppLogger()
