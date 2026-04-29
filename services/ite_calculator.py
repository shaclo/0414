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

    # ================================================================
    # v1.1.6 新增：骨架阶段事件级 τ 裁剪闭环
    # 利用 CPG 节点 event_units[i].tau_estimate（AI 自评）做离线裁剪，
    # 不需要再调一次 LLM，速度快、可在骨架生成完成后即时执行。
    # ================================================================

    REDUNDANT_TAU_THRESHOLD = 0.05      # τ < 0.05 视为冗余事件
    HIGH_IMPACT_TAU_THRESHOLD = 0.15    # 相邻 Hauge 阶段间至少 1 个 τ ≥ 0.15
    REDUNDANT_RUN_LENGTH = 3            # 连续 ≥3 个冗余事件即触发合并建议

    @classmethod
    def compress_redundant_nodes(cls, cpg_nodes: list) -> dict:
        """
        v1.1.6 骨架阶段 ITE 闭环裁剪。

        输入：扁平 CPG 节点列表（每个节点含 event_units[i].tau_estimate）
        输出：
          {
            "redundant_units": [...],      # τ<0.05 的事件级单元
            "merge_suggestions": [...],    # 连续 ≥3 个冗余 → 建议合并
            "stage_warnings": [...],       # 相邻 Hauge 阶段无高冲击事件警告
            "summary": {
              "total_units": N,
              "redundant_count": K,
              "redundant_ratio": K/N,
              "high_impact_count": H,
            }
          }
        """
        all_units: list[dict] = []
        # 展开为带元信息的事件单元序列（保留集级与 Hauge 阶段信息）
        for node in cpg_nodes or []:
            node_id = node.get("node_id", "")
            stage_id = node.get("hauge_stage_id", 0)
            for u in node.get("event_units", []) or []:
                all_units.append({
                    "node_id": node_id,
                    "stage_id": stage_id,
                    "unit_id": u.get("unit_id", ""),
                    "action": u.get("action", ""),
                    "tau": float(u.get("tau_estimate", -1.0)),
                    "twist_type": u.get("twist_type", "none"),
                })

        redundant: list[dict] = []
        for u in all_units:
            if 0 <= u["tau"] < cls.REDUNDANT_TAU_THRESHOLD:
                redundant.append(u)

        # 检测连续 ≥REDUNDANT_RUN_LENGTH 个冗余 unit（按 all_units 排列顺序）
        merge_suggestions: list[dict] = []
        run_start: Optional[int] = None
        for i, u in enumerate(all_units):
            is_redundant = 0 <= u["tau"] < cls.REDUNDANT_TAU_THRESHOLD
            if is_redundant:
                if run_start is None:
                    run_start = i
            else:
                if run_start is not None and (i - run_start) >= cls.REDUNDANT_RUN_LENGTH:
                    merge_suggestions.append({
                        "from_unit": all_units[run_start]["unit_id"],
                        "to_unit": all_units[i - 1]["unit_id"],
                        "from_node": all_units[run_start]["node_id"],
                        "to_node": all_units[i - 1]["node_id"],
                        "count": i - run_start,
                        "reason": (
                            f"连续 {i - run_start} 个事件 τ<{cls.REDUNDANT_TAU_THRESHOLD}，"
                            f"建议压缩为 1 个事件以提升信息密度。"
                        ),
                    })
                run_start = None
        if run_start is not None and (len(all_units) - run_start) >= cls.REDUNDANT_RUN_LENGTH:
            merge_suggestions.append({
                "from_unit": all_units[run_start]["unit_id"],
                "to_unit": all_units[-1]["unit_id"],
                "from_node": all_units[run_start]["node_id"],
                "to_node": all_units[-1]["node_id"],
                "count": len(all_units) - run_start,
                "reason": (
                    f"末尾连续 {len(all_units) - run_start} 个事件 τ<{cls.REDUNDANT_TAU_THRESHOLD}，"
                    f"建议压缩。"
                ),
            })

        # 相邻 Hauge 阶段间的高冲击事件覆盖检查
        stage_warnings: list[str] = []
        stages_seen = sorted({u["stage_id"] for u in all_units if u["stage_id"]})
        for sid in stages_seen:
            stage_units = [u for u in all_units if u["stage_id"] == sid]
            high_impact = [u for u in stage_units
                           if u["tau"] >= cls.HIGH_IMPACT_TAU_THRESHOLD
                           or u.get("twist_type", "none") not in ("none", "")]
            if not high_impact and stage_units:
                stage_warnings.append(
                    f"Hauge 阶段 {sid} 缺少高冲击事件（所有 τ<{cls.HIGH_IMPACT_TAU_THRESHOLD} 且无 twist）"
                )

        high_impact_count = sum(
            1 for u in all_units
            if u["tau"] >= cls.HIGH_IMPACT_TAU_THRESHOLD or u.get("twist_type", "none") not in ("none", "")
        )

        total = len(all_units)
        ratio = (len(redundant) / total) if total else 0.0

        return {
            "redundant_units": redundant,
            "merge_suggestions": merge_suggestions,
            "stage_warnings": stage_warnings,
            "summary": {
                "total_units": total,
                "redundant_count": len(redundant),
                "redundant_ratio": round(ratio, 3),
                "high_impact_count": high_impact_count,
            },
        }


# 全局单例
ite_calculator = ITECalculator()
