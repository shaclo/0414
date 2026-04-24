import json
import logging
import os
from typing import List, Dict, Optional

from env import (
    PERSONA_DEFINITIONS,
    SYSTEM_PROMPT_VARIATION_FRAME,
    USER_PROMPT_VARIATION,
    SUGGESTED_TEMPERATURES,
)
from services.ai_service import ai_service

logger = logging.getLogger(__name__)

# 持久化文件路径（与项目同级的用户配置）
_CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config")
_PERSONA_FILE = os.path.join(_CONFIG_DIR, "bvsr_personas.json")


class PersonaEngine:
    """
    多人格生成引擎 (NarrativeLoom BVSR 论文中的 Multi-Persona Ensemble)。

    职责：
    1. 管理 10 个预设人格的激活/停用状态
    2. 为指定 CPG 节点组装每个人格的完整 prompt
    3. 发起并行 AI 调用（通过 ai_service.parallel_generate）
    4. 收集并返回多人格的 StoryBeat 结果

    持久化：
    - 自动保存到 config/bvsr_personas.json
    - 启动时自动加载，若文件不存在则使用 env.py 默认值
    """

    def __init__(self):
        self._personas: Dict[str, dict] = {}
        self._active_personas: set = set()
        self._load()

    # ------------------------------------------------------------------ #
    # 持久化
    # ------------------------------------------------------------------ #
    def _load(self):
        """从配置文件加载，失败时使用 env.py 默认值"""
        if os.path.exists(_PERSONA_FILE):
            try:
                with open(_PERSONA_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self._personas = data.get("personas", {})
                self._active_personas = set(data.get("active", list(self._personas.keys())))
                logger.info("从 %s 加载了 %d 个人格", _PERSONA_FILE, len(self._personas))
                return
            except Exception as e:
                logger.warning("加载人格配置失败: %s, 使用默认值", e)

        # 使用默认值
        self._personas = dict(PERSONA_DEFINITIONS)
        self._active_personas = set(self._personas.keys())

    def _save(self):
        """保存到配置文件"""
        try:
            os.makedirs(_CONFIG_DIR, exist_ok=True)
            data = {
                "personas": self._personas,
                "active": list(self._active_personas),
            }
            with open(_PERSONA_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info("人格配置已保存到 %s", _PERSONA_FILE)
        except Exception as e:
            logger.error("保存人格配置失败: %s", e)

    def get_all_personas(self) -> Dict[str, dict]:
        """获取所有人格定义"""
        return dict(self._personas)

    def get_active_personas(self) -> Dict[str, dict]:
        """获取当前激活的人格"""
        return {k: v for k, v in self._personas.items() if k in self._active_personas}

    def set_active_personas(self, keys: List[str]):
        """设置激活的人格列表（由用户在 UI 中选择）"""
        self._active_personas = set(keys)
        self._save()
        logger.info("激活人格: %s", keys)

    def add_persona(self, key: str, name: str, category: str, identity_block: str):
        """添加新人格"""
        if key in self._personas:
            raise ValueError(f"人格 key '{key}' 已存在")
        self._personas[key] = {
            "name": name,
            "category": category,
            "identity_block": identity_block,
        }
        self._active_personas.add(key)
        self._save()
        logger.info("添加人格: %s", key)

    def update_persona(self, key: str, name: str, category: str, identity_block: str):
        """更新已有人格定义"""
        if key not in self._personas:
            raise KeyError(f"人格 key '{key}' 不存在")
        self._personas[key] = {
            "name": name,
            "category": category,
            "identity_block": identity_block,
        }
        self._save()
        logger.info("更新人格: %s", key)

    def remove_persona(self, key: str):
        """删除人格"""
        if key not in self._personas:
            return
        del self._personas[key]
        self._active_personas.discard(key)
        self._save()
        logger.info("删除人格: %s", key)

    def is_active(self, key: str) -> bool:
        return key in self._active_personas

    def toggle_active(self, key: str, active: bool):
        if active:
            self._active_personas.add(key)
        else:
            self._active_personas.discard(key)
        self._save()

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
        drama_style_block: str = "",
        protagonist_goal: str = "",
        characters_summary: str = "",
        satisfaction_prompt_injection: str = "",
        hook_prompt_injection: str = "",
        previous_episode_hook: str = "",
    ) -> list:
        """
        为每个激活的人格构建 AI 调用参数。

        Returns:
            调用参数列表，每个元素是 ai_service.parallel_generate 需要的 dict
        """
        if temperature is None:
            temperature = SUGGESTED_TEMPERATURES["variation"]

        # 组装公共 User Prompt（所有人格共用同一个 User Prompt）
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
            .replace("{protagonist_goal}", protagonist_goal or "（未设定主角目标）")
            .replace("{characters_summary}", characters_summary or "（未设定角色）")
            .replace("{previous_episode_hook}", previous_episode_hook or "（本集为开篇，无前集钩子）")
        )

        calls = []
        for key, persona in self.get_active_personas().items():
            # 每个人格有自己的 System Prompt（身份块不同）
            system_prompt = SYSTEM_PROMPT_VARIATION_FRAME.replace(
                "{persona_identity_block}", persona["identity_block"]
            )
            # 注入风格块
            if drama_style_block:
                system_prompt += "\n" + drama_style_block
            # 注入用户配置的爽感公式
            if satisfaction_prompt_injection:
                system_prompt += "\n\n" + satisfaction_prompt_injection
            # 注入用户配置的钩子公式
            if hook_prompt_injection:
                system_prompt += "\n\n" + hook_prompt_injection
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
        drama_style_block: str = "",
        protagonist_goal: str = "",
        characters_summary: str = "",
        provider_pool: list = None,
        satisfaction_prompt_injection: str = "",
        hook_prompt_injection: str = "",
        previous_episode_hook: str = "",
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
            drama_style_block=drama_style_block,
            protagonist_goal=protagonist_goal,
            characters_summary=characters_summary,
            satisfaction_prompt_injection=satisfaction_prompt_injection,
            hook_prompt_injection=hook_prompt_injection,
            previous_episode_hook=previous_episode_hook,
        )

        raw_results = await ai_service.parallel_generate(calls, provider_pool=provider_pool)

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
