# ============================================================
# services/persona_engine.py
# 多人格并行生成引擎
# 职责：管理10个人格，组装prompt，发起并行盲视变异调用
# ============================================================

import json
import logging
from typing import List, Dict, Optional

from env import (
    PERSONA_DEFINITIONS,
    SYSTEM_PROMPT_VARIATION_FRAME,
    USER_PROMPT_VARIATION,
    SUGGESTED_TEMPERATURES,
)
from services.ai_service import ai_service

logger = logging.getLogger(__name__)


class PersonaEngine:
    """
    多人格生成引擎 (NarrativeLoom BVSR 论文中的 Multi-Persona Ensemble)。

    职责：
    1. 管理 10 个预设人格的激活/停用状态
    2. 为指定 CPG 节点组装每个人格的完整 prompt
    3. 发起并行 AI 调用（通过 ai_service.parallel_generate）
    4. 收集并返回多人格的 StoryBeat 结果
    """

    def __init__(self):
        self._personas = dict(PERSONA_DEFINITIONS)
        # 默认全部激活
        self._active_personas: set = set(self._personas.keys())

    def get_all_personas(self) -> Dict[str, dict]:
        """获取所有人格定义"""
        return dict(self._personas)

    def get_active_personas(self) -> Dict[str, dict]:
        """获取当前激活的人格"""
        return {k: v for k, v in self._personas.items() if k in self._active_personas}

    def set_active_personas(self, keys: List[str]):
        """设置激活的人格列表（由用户在 UI 中选择）"""
        self._active_personas = set(keys)
        logger.info("激活人格: %s", keys)

    def build_variation_calls(
        self,
        sparkle: str,
        world_variables_json: str,
        cpg_skeleton_json: str,
        target_node_id: str,
        target_node_title: str,
        hauge_stage_name: str,
        node_event_summaries: str,
        previous_confirmed_beats_json: str,
        edge_relations_context: str = "",
        temperature: float = None,
        top_p: float = 0.9,
        top_k: int = 40,
        max_tokens: int = 8192,
    ) -> list:
        """
        为每个激活的人格构建 AI 调用参数。

        Returns:
            调用参数列表，每个元素是 ai_service.parallel_generate 需要的 dict
        """
        if temperature is None:
            temperature = SUGGESTED_TEMPERATURES["variation"]

        # 组装公共 User Prompt（所有人格共用同一个 User Prompt）
        # 注意：prompt 里含有 JSON 示例的 {} 花括号，不能用 .format()，改用 str.replace()
        user_prompt = (
            USER_PROMPT_VARIATION
            .replace("{sparkle}", sparkle)
            .replace("{world_variables_json}", world_variables_json)
            .replace("{cpg_skeleton_json}", cpg_skeleton_json)
            .replace("{target_node_id}", target_node_id)
            .replace("{target_node_title}", target_node_title)
            .replace("{hauge_stage_name}", hauge_stage_name)
            .replace("{node_event_summaries}", node_event_summaries)
            .replace("{edge_relations_context}", edge_relations_context or "（本节点无连线）")
            .replace("{previous_confirmed_beats_json}", previous_confirmed_beats_json)
        )

        calls = []
        for key, persona in self.get_active_personas().items():
            # 每个人格有自己的 System Prompt（身份块不同）
            # 同样用 str.replace 替代 .format()，避免 JSON 花括号问题
            system_prompt = SYSTEM_PROMPT_VARIATION_FRAME.replace(
                "{persona_identity_block}", persona["identity_block"]
            )
            calls.append({
                "user_prompt": user_prompt,
                "system_prompt": system_prompt,
                "temperature": temperature,
                "top_p": top_p,
                "top_k": top_k,
                "max_tokens": max_tokens,
                "persona_key": key,
            })

        logger.info("构建了 %d 个人格的变异调用", len(calls))
        return calls

    async def generate_variations(
        self,
        sparkle: str,
        world_variables_json: str,
        cpg_skeleton_json: str,
        target_node_id: str,
        target_node_title: str,
        hauge_stage_name: str,
        node_event_summaries: str,
        previous_confirmed_beats_json: str,
        edge_relations_context: str = "",
        temperature: float = None,
        top_p: float = 0.9,
        top_k: int = 40,
        max_tokens: int = 8192,
    ) -> List[dict]:
        """
        执行盲视变异：并行调用所有激活人格。

        Returns:
            结果列表：[{"persona_key": str, "beat": dict|None, "error": str|None}]
        """
        calls = self.build_variation_calls(
            sparkle=sparkle,
            world_variables_json=world_variables_json,
            cpg_skeleton_json=cpg_skeleton_json,
            target_node_id=target_node_id,
            target_node_title=target_node_title,
            hauge_stage_name=hauge_stage_name,
            node_event_summaries=node_event_summaries,
            previous_confirmed_beats_json=previous_confirmed_beats_json,
            edge_relations_context=edge_relations_context,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            max_tokens=max_tokens,
        )

        raw_results = await ai_service.parallel_generate(calls)

        # 解析每个结果的 JSON
        parsed_results = []
        for r in raw_results:
            if r["error"]:
                parsed_results.append({
                    "persona_key": r["persona_key"],
                    "beat": None,
                    "error": r["error"],
                })
            else:
                try:
                    beat_data = json.loads(r["result"])
                    parsed_results.append({
                        "persona_key": r["persona_key"],
                        "beat": beat_data,
                        "error": None,
                    })
                except json.JSONDecodeError as e:
                    parsed_results.append({
                        "persona_key": r["persona_key"],
                        "beat": None,
                        "error": f"JSON 解析失败: {str(e)}",
                    })

        return parsed_results


# 全局单例
persona_engine = PersonaEngine()
