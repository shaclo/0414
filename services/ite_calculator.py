# ============================================================
# services/ite_calculator.py
# ITE (个体处理效应) 因果蒸馏计算器
# 职责：调用 AI-Call-5，解析 ITE 分析结果，标记冗余事件
# ============================================================

import json
import logging
from typing import Optional

from env import (
    SYSTEM_PROMPT_ITE,
    USER_PROMPT_ITE,
    SUGGESTED_TEMPERATURES,
)
from services.ai_service import ai_service

logger = logging.getLogger(__name__)


class ITECalculator:
    """
    ITE 因果蒸馏计算器（Causal Graph 论文中的核心算法）。

    原理：
      τᵢ = Ŷᵢ(1) - Ŷᵢ(0)
      τᵢ < 0.05 → 冗余事件，建议剔除
      每两个 Hauge 阶段之间至少一个 τᵢ > 0.15

    实现方式：
      使用 LLM-as-Judge 方案——让 Gemini 模拟因果推断，
      评估每个事件对终局达成的贡献度。
    """

    def analyze(
        self,
        finale_condition: str,
        all_confirmed_beats_json: str,
        causal_edges_json: str,
        temperature: float = None,
        top_p: float = 0.9,
        top_k: int = 40,
        max_tokens: int = 8192,
    ) -> dict:
        """
        执行 ITE 分析。

        Args:
            finale_condition: 终局条件描述
            all_confirmed_beats_json: 所有已确认 Beat 的 JSON 字符串
            causal_edges_json: CPG 因果边的 JSON 字符串
            temperature: 温度值（默认 0.3）

        Returns:
            ITE 分析结果 dict，包含：
            - event_evaluations: 每个事件的 ITE 评分
            - pruning_suggestions: 剔除建议
            - structural_warnings: 结构警告
        """
        if temperature is None:
            temperature = SUGGESTED_TEMPERATURES["ite"]

        user_prompt = (
            USER_PROMPT_ITE
            .replace("{finale_condition}", finale_condition)
            .replace("{all_confirmed_beats_json}", all_confirmed_beats_json)
            .replace("{causal_edges_json}", causal_edges_json)
        )

        result = ai_service.generate_json(
            user_prompt=user_prompt,
            system_prompt=SYSTEM_PROMPT_ITE,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            max_tokens=max_tokens,
        )

        logger.info(
            "ITE 分析完成: %d 个事件评估, %d 个剔除建议, %d 个结构警告",
            len(result.get("event_evaluations", [])),
            len(result.get("pruning_suggestions", [])),
            len(result.get("structural_warnings", [])),
        )
        return result

    @staticmethod
    def get_prunable_events(ite_result: dict, threshold: float = 0.05) -> list:
        """
        从 ITE 结果中筛选可剔除的事件。

        Args:
            ite_result: ITE 分析结果
            threshold: ITE 阈值，低于此值标记为冗余

        Returns:
            可剔除事件列表: [{"node_id": str, "event_id": int, "ite_score": float}]
        """
        prunable = []
        for ev in ite_result.get("event_evaluations", []):
            if ev.get("ite_score", 1.0) < threshold:
                prunable.append({
                    "node_id": ev["node_id"],
                    "event_id": ev["event_id"],
                    "ite_score": ev["ite_score"],
                    "reasoning": ev.get("reasoning", ""),
                })
        return prunable

    @staticmethod
    def get_structural_warnings(ite_result: dict) -> list:
        """提取结构性警告"""
        return ite_result.get("structural_warnings", [])


# 全局单例
ite_calculator = ITECalculator()
