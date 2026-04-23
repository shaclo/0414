# ============================================================
# services/answer_strategy_manager.py
# 回答风格策略管理器（单例）
# 持久化：config/answer_strategies.json
# 默认值来自 env.AUTO_ANSWER_STRATEGIES
# ============================================================

import json
import os

_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "config", "answer_strategies.json"
)


def _default_strategies() -> dict:
    """从 env.AUTO_ANSWER_STRATEGIES 加载默认策略"""
    from env import AUTO_ANSWER_STRATEGIES
    return {
        key: {
            "label": info["label"],
            "instruction": info["instruction"],
        }
        for key, info in AUTO_ANSWER_STRATEGIES.items()
    }


class AnswerStrategyManager:
    """
    回答风格策略管理器（单例）。

    数据结构：
        {
            key: {
                "label":       "🏠 写实现实",
                "instruction": "请以写实主义视角回答……"
            },
            ...
        }

    功能：
        - 加载/保存到 config/answer_strategies.json
        - 增删改查策略
        - 提供给 qa_panel.py 下拉框和 AutoAnswerWorker
    """

    def __init__(self):
        self._strategies: dict = {}
        self._load()

    # ------------------------------------------------------------------ #
    # 持久化
    # ------------------------------------------------------------------ #
    def _load(self):
        try:
            if os.path.exists(_CONFIG_PATH):
                with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
                    self._strategies = json.load(f)
            else:
                self._strategies = _default_strategies()
        except Exception:
            self._strategies = _default_strategies()

    def _save(self):
        try:
            os.makedirs(os.path.dirname(_CONFIG_PATH), exist_ok=True)
            with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(self._strategies, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    # 查询
    # ------------------------------------------------------------------ #
    def get_all(self) -> dict:
        """返回全部策略 {key: {label, instruction}}"""
        return dict(self._strategies)

    def get(self, key: str) -> dict:
        """返回指定策略，不存在则返回第一个或空"""
        if key in self._strategies:
            return dict(self._strategies[key])
        if self._strategies:
            return dict(next(iter(self._strategies.values())))
        return {"label": "", "instruction": ""}

    def get_instruction(self, key: str) -> str:
        """返回指定策略的 instruction 文本"""
        return self.get(key).get("instruction", "")

    def get_label(self, key: str) -> str:
        """返回指定策略的显示标签"""
        return self.get(key).get("label", key)

    # ------------------------------------------------------------------ #
    # 增删改
    # ------------------------------------------------------------------ #
    def update(self, key: str, label: str, instruction: str):
        """新建或更新策略"""
        if not key:
            raise ValueError("策略 Key 不能为空")
        if not label:
            raise ValueError("标签不能为空")
        if not instruction:
            raise ValueError("Prompt 指令不能为空")
        self._strategies[key] = {"label": label, "instruction": instruction}
        self._save()

    def remove(self, key: str):
        """删除策略（至少保留 1 个）"""
        if len(self._strategies) <= 1:
            raise ValueError("至少需要保留一个策略")
        self._strategies.pop(key, None)
        self._save()

    def reset_to_defaults(self):
        """恢复到内置默认策略"""
        self._strategies = _default_strategies()
        self._save()

    def list_keys(self) -> list:
        """返回有序 key 列表"""
        return list(self._strategies.keys())


# 全局单例
answer_strategy_manager = AnswerStrategyManager()
