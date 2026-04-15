# ============================================================
# services/worker.py
# QThread 工作线程 — 所有 AI 调用都在这里后台执行
# 确保 UI 不卡顿，每个 AI-Call 对应一个 Worker 类
# ============================================================

import json
import asyncio
import logging
from PySide6.QtCore import QThread, Signal

from services.ai_service import ai_service
from services.persona_engine import persona_engine
from services.ite_calculator import ite_calculator
from services.rag_controller import rag_controller
from env import (
    SYSTEM_PROMPT_SOCRATIC, USER_PROMPT_SOCRATIC,
    SYSTEM_PROMPT_WORLD_EXTRACT, USER_PROMPT_WORLD_EXTRACT,
    SYSTEM_PROMPT_CPG_SKELETON, USER_PROMPT_CPG_SKELETON,
    USER_PROMPT_ITE, USER_PROMPT_RAG_CHECK,
    SYSTEM_PROMPT_CHARACTER_GEN, USER_PROMPT_CHARACTER_GEN,
    SYSTEM_PROMPT_EXPANSION, USER_PROMPT_EXPANSION,
    SUGGESTED_TEMPERATURES, TEMPERATURE_CHARACTER_GEN, TEMPERATURE_EXPANSION,
)

logger = logging.getLogger(__name__)


class BaseWorker(QThread):
    """所有 Worker 的基类，提供标准完成/错误信号"""
    finished = Signal(dict)   # 成功：携带结果 dict
    error = Signal(str)       # 失败：携带错误信息字符串
    progress = Signal(str)    # 进度提示（显示在状态栏）


# ============================================================
# AI-Call-1: 苏格拉底盘问
# ============================================================
class SocraticWorker(BaseWorker):
    """
    后台执行 AI-Call-1。
    输入: sparkle (一句话), AI 参数
    输出: {"questions": [...]}
    """
    def __init__(self, sparkle: str, ai_params: dict):
        super().__init__()
        self.sparkle = sparkle
        self.ai_params = ai_params

    def run(self):
        try:
            self.progress.emit("🔍 正在生成追问问题，请稍候…")
            user_prompt = USER_PROMPT_SOCRATIC.replace("{sparkle}", self.sparkle)
            result = ai_service.generate_json(
                user_prompt=user_prompt,
                system_prompt=SYSTEM_PROMPT_SOCRATIC,
                temperature=self.ai_params.get("temperature", SUGGESTED_TEMPERATURES["socratic"]),
                top_p=self.ai_params.get("top_p", 0.9),
                top_k=self.ai_params.get("top_k", 40),
                max_tokens=self.ai_params.get("max_tokens", 4096),
            )
            self.finished.emit(result)
        except Exception as e:
            logger.error("SocraticWorker 失败: %s", e, exc_info=True)
            self.error.emit(f"苏格拉底盘问失败：{str(e)}")


# ============================================================
# AI-Call-2: 世界观变量提炼
# ============================================================
class WorldExtractWorker(BaseWorker):
    """
    后台执行 AI-Call-2。
    输入: sparkle, qa_pairs (list of dicts), AI 参数
    输出: {"story_title_suggestion": ..., "finale_condition": ..., "variables": [...], "conflicts": [...]}
    """
    def __init__(self, sparkle: str, qa_pairs: list, ai_params: dict):
        super().__init__()
        self.sparkle = sparkle
        self.qa_pairs = qa_pairs
        self.ai_params = ai_params

    def run(self):
        try:
            self.progress.emit("📋 正在提炼世界观变量，请稍候…")

            # 格式化 Q&A 对
            qa_formatted_lines = []
            for p in self.qa_pairs:
                qa_formatted_lines.append(
                    f"Q{p['question_id']} [{p.get('dimension', '')}]: {p['question']}\n"
                    f"A: {p.get('answer', '（未回答）')}"
                )
            qa_pairs_formatted = "\n\n".join(qa_formatted_lines)

            user_prompt = (
                USER_PROMPT_WORLD_EXTRACT
                .replace("{sparkle}", self.sparkle)
                .replace("{qa_pairs_formatted}", qa_pairs_formatted)
            )
            result = ai_service.generate_json(
                user_prompt=user_prompt,
                system_prompt=SYSTEM_PROMPT_WORLD_EXTRACT,
                temperature=self.ai_params.get("temperature", SUGGESTED_TEMPERATURES["world_extract"]),
                top_p=self.ai_params.get("top_p", 0.9),
                top_k=self.ai_params.get("top_k", 40),
                max_tokens=self.ai_params.get("max_tokens", 4096),
            )
            self.finished.emit(result)
        except Exception as e:
            logger.error("WorldExtractWorker 失败: %s", e, exc_info=True)
            self.error.emit(f"世界观提炼失败：{str(e)}")


# ============================================================
# AI-Call-3: CPG 骨架生成
# ============================================================
class CPGSkeletonWorker(BaseWorker):
    """
    后台执行 AI-Call-3。
    输入: sparkle, world_variables (list), finale_condition, characters (list),
           total_episodes, episode_duration, AI 参数
    输出: {"cpg_title": ..., "hauge_stages": [...], "causal_edges": [...]}
    """
    def __init__(self, sparkle: str, world_variables: list, finale_condition: str,
                 ai_params: dict, characters: list = None,
                 total_episodes: int = 20, episode_duration: int = 3):
        super().__init__()
        self.sparkle = sparkle
        self.world_variables = world_variables
        self.finale_condition = finale_condition
        self.ai_params = ai_params
        self.characters = characters or []
        self.total_episodes = total_episodes
        self.episode_duration = episode_duration

    def run(self):
        try:
            self.progress.emit(f"🏗️ 正在生成 {self.total_episodes} 集 CPG 骨架，请稍候…")
            # 组装角色概要注入 prompt
            chars_summary = "\n".join(
                f"- [{c.get('role_type','配角')}] {c.get('name','')}: "
                f"{c.get('personality','')} / 动机: {c.get('motivation','')}"
                for c in self.characters
            ) or "（未设定角色）"

            # 替换 system prompt 中的集数/时长占位符
            system_prompt = (
                SYSTEM_PROMPT_CPG_SKELETON
                .replace("{total_episodes}", str(self.total_episodes))
                .replace("{episode_duration}", str(self.episode_duration))
            )

            user_prompt = (
                USER_PROMPT_CPG_SKELETON
                .replace("{sparkle}", self.sparkle)
                .replace("{world_variables_json}",
                         json.dumps(self.world_variables, ensure_ascii=False, indent=2))
                .replace("{finale_condition}", self.finale_condition)
                .replace("{characters_summary}", chars_summary)
                .replace("{total_episodes}", str(self.total_episodes))
                .replace("{episode_duration}", str(self.episode_duration))
            )
            result = ai_service.generate_json(
                user_prompt=user_prompt,
                system_prompt=system_prompt,
                temperature=self.ai_params.get("temperature", SUGGESTED_TEMPERATURES["cpg_skeleton"]),
                top_p=self.ai_params.get("top_p", 0.9),
                top_k=self.ai_params.get("top_k", 40),
                max_tokens=self.ai_params.get("max_tokens", 16384),
            )
            self.finished.emit(result)
        except Exception as e:
            logger.error("CPGSkeletonWorker 失败: %s", e, exc_info=True)
            self.error.emit(f"CPG 骨架生成失败：{str(e)}")


# ============================================================
# AI-Call-4: 盲视变异（多人格并行）
# ============================================================
class VariationWorker(BaseWorker):
    """
    后台执行 AI-Call-4（并行多人格）。
    结果按人格逐一通过 beat_ready 信号发出（流式体验）。
    全部完成后发出 finished。

    信号:
        beat_ready: 单个人格完成时发出 {"persona_key": str, "beat": dict|None, "error": str|None}
    """
    beat_ready = Signal(dict)

    def __init__(
        self,
        sparkle: str,
        world_variables: list,
        cpg_nodes: list,
        cpg_edges: list,
        target_node: dict,
        confirmed_beats: dict,
        selected_persona_keys: list,
        ai_params: dict,
        characters: list = None,
    ):
        super().__init__()
        self.sparkle = sparkle
        self.world_variables = world_variables
        self.cpg_nodes = cpg_nodes
        self.cpg_edges = cpg_edges
        self.target_node = target_node
        self.confirmed_beats = confirmed_beats
        self.selected_persona_keys = selected_persona_keys
        self.ai_params = ai_params
        self.characters = characters or []

    def run(self):
        try:
            self.progress.emit(
                f"🚀 正在并行生成 {len(self.selected_persona_keys)} 个人格变体，请稍候…"
            )

            # 用于构建完整 CPG 骨架结构（供 context）
            cpg_skeleton_json = json.dumps(
                {"nodes": self.cpg_nodes, "edges": self.cpg_edges},
                ensure_ascii=False, indent=2,
            )
            world_variables_json = json.dumps(self.world_variables, ensure_ascii=False, indent=2)

            # 已确认的前序 Beat（不包含当前节点）
            node_id = self.target_node.get("node_id", "")
            prev_beats = {k: v for k, v in self.confirmed_beats.items()
                          if v is not None and k != node_id}
            prev_beats_json = json.dumps(prev_beats, ensure_ascii=False, indent=2)

            # 事件摘要
            node_event_summaries = "\n".join(
                f"- {s}" for s in self.target_node.get("event_summaries", [])
            )

            # 角色概要注入
            characters_summary = "\n".join(
                f"- [{c.get('role_type','配角')}] {c.get('name','')}: "
                f"{c.get('personality','')} / 动机: {c.get('motivation','')}"
                for c in self.characters
            ) or "（未设定角色）"

            # 设置激活的人格
            persona_engine.set_active_personas(self.selected_persona_keys)

            # 在本线程运行 asyncio 事件循环（QThread 里没有 event loop）
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                results = loop.run_until_complete(
                    persona_engine.generate_variations(
                        sparkle=self.sparkle,
                        world_variables_json=world_variables_json,
                        cpg_skeleton_json=cpg_skeleton_json,
                        target_node_id=node_id,
                        target_node_title=self.target_node.get("title", ""),
                        hauge_stage_name=self.target_node.get("hauge_stage_name", ""),
                        node_event_summaries=node_event_summaries,
                        previous_confirmed_beats_json=prev_beats_json,
                        temperature=self.ai_params.get("temperature", SUGGESTED_TEMPERATURES["variation"]),
                        top_p=self.ai_params.get("top_p", 0.9),
                        top_k=self.ai_params.get("top_k", 40),
                        max_tokens=self.ai_params.get("max_tokens", 8192),
                    )
                )
            finally:
                loop.close()

            # 逐个发射结果信号
            for r in results:
                self.beat_ready.emit(r)

            self.finished.emit({"total": len(results), "success": sum(1 for r in results if r.get("beat"))})

        except Exception as e:
            logger.error("VariationWorker 失败: %s", e, exc_info=True)
            self.error.emit(f"盲视变异失败：{str(e)}")


# ============================================================
# AI-Call-5: ITE 因果蒸馏
# ============================================================
class ITEWorker(BaseWorker):
    """
    后台执行 AI-Call-5。
    """
    def __init__(self, finale_condition: str, confirmed_beats: dict, cpg_edges: list, ai_params: dict):
        super().__init__()
        self.finale_condition = finale_condition
        self.confirmed_beats = confirmed_beats
        self.cpg_edges = cpg_edges
        self.ai_params = ai_params

    def run(self):
        try:
            self.progress.emit("📊 正在执行 ITE 因果分析…")
            result = ite_calculator.analyze(
                finale_condition=self.finale_condition,
                all_confirmed_beats_json=json.dumps(self.confirmed_beats, ensure_ascii=False, indent=2),
                causal_edges_json=json.dumps(self.cpg_edges, ensure_ascii=False, indent=2),
                temperature=self.ai_params.get("temperature", SUGGESTED_TEMPERATURES["ite"]),
                top_p=self.ai_params.get("top_p", 0.9),
                top_k=self.ai_params.get("top_k", 40),
                max_tokens=self.ai_params.get("max_tokens", 8192),
            )
            self.finished.emit(result)
        except Exception as e:
            logger.error("ITEWorker 失败: %s", e, exc_info=True)
            self.error.emit(f"ITE 分析失败：{str(e)}")


# ============================================================
# AI-Call-6: RAG 一致性审查
# ============================================================
class RAGWorker(BaseWorker):
    """
    后台执行 AI-Call-6。
    """
    def __init__(self, new_beat: dict, world_variables: list, confirmed_beats: dict, ai_params: dict):
        super().__init__()
        self.new_beat = new_beat
        self.world_variables = world_variables
        self.confirmed_beats = confirmed_beats
        self.ai_params = ai_params

    def run(self):
        try:
            self.progress.emit("🔍 正在执行 RAG 一致性审查…")
            result = rag_controller.check_consistency(
                new_beat_json=json.dumps(self.new_beat, ensure_ascii=False, indent=2),
                world_variables_json=json.dumps(self.world_variables, ensure_ascii=False, indent=2),
                confirmed_beats_json=json.dumps(self.confirmed_beats, ensure_ascii=False, indent=2),
                temperature=self.ai_params.get("temperature", SUGGESTED_TEMPERATURES["rag_check"]),
                top_p=self.ai_params.get("top_p", 0.9),
                top_k=self.ai_params.get("top_k", 40),
                max_tokens=self.ai_params.get("max_tokens", 4096),
            )
            self.finished.emit(result)
        except Exception as e:
            logger.error("RAGWorker 失败: %s", e, exc_info=True)
            self.error.emit(f"RAG 审查失败：{str(e)}")


# ============================================================
# AI-Call-1.5: 角色自动生成
# ============================================================
class CharacterGenWorker(BaseWorker):
    """
    后台执行 AI-Call-1.5：角色自动生成。
    输入: sparkle, world_variables (list), finale_condition, AI 参数
    输出: {"characters": [...], "relations": [...], "design_notes": "..."}
    """
    def __init__(self, sparkle: str, world_variables: list, finale_condition: str, ai_params: dict):
        super().__init__()
        self.sparkle = sparkle
        self.world_variables = world_variables
        self.finale_condition = finale_condition
        self.ai_params = ai_params

    def run(self):
        try:
            self.progress.emit("🎭 正在生成角色建议，请稍候…")
            user_prompt = (
                USER_PROMPT_CHARACTER_GEN
                .replace("{sparkle}", self.sparkle)
                .replace("{world_variables_json}",
                         json.dumps(self.world_variables, ensure_ascii=False, indent=2))
                .replace("{finale_condition}", self.finale_condition)
            )
            result = ai_service.generate_json(
                user_prompt=user_prompt,
                system_prompt=SYSTEM_PROMPT_CHARACTER_GEN,
                temperature=self.ai_params.get("temperature", TEMPERATURE_CHARACTER_GEN),
                top_p=self.ai_params.get("top_p", 0.9),
                top_k=self.ai_params.get("top_k", 40),
                max_tokens=self.ai_params.get("max_tokens", 4096),
            )
            self.finished.emit(result)
        except Exception as e:
            logger.error("CharacterGenWorker 失败: %s", e, exc_info=True)
            self.error.emit(f"角色生成失败：{str(e)}")


# ============================================================
# AI-Call-7: 剧本扩写
# ============================================================
class ExpansionWorker(BaseWorker):
    """
    后台执行 AI-Call-7：剧本扩写。
    将已确认的 Beat 扩写为标准短剧剧本格式。
    输出: {"text": "剧本正文..."}
    """
    def __init__(
        self,
        sparkle: str,
        finale_condition: str,
        characters_summary: str,
        previous_hook: str,
        node_id: str,
        node_title: str,
        hauge_stage_name: str,
        setting: str,
        entities: str,
        causal_events_text: str,
        hook: str,
        target_word_count: str,
        ai_params: dict,
        episode_duration: int = 3,
    ):
        super().__init__()
        self.sparkle = sparkle
        self.finale_condition = finale_condition
        self.characters_summary = characters_summary
        self.previous_hook = previous_hook
        self.node_id = node_id
        self.node_title = node_title
        self.hauge_stage_name = hauge_stage_name
        self.setting = setting
        self.entities = entities
        self.causal_events_text = causal_events_text
        self.hook = hook
        self.target_word_count = target_word_count
        self.ai_params = ai_params
        self.episode_duration = episode_duration

    def run(self):
        try:
            self.progress.emit(f"🎬 正在扩写 {self.node_id}：{self.node_title}…")

            # 注意：SYSTEM_PROMPT_EXPANSION 含有占位符
            system_prompt = (
                SYSTEM_PROMPT_EXPANSION
                .replace("{target_word_count}", self.target_word_count)
                .replace("{episode_duration}", str(self.episode_duration))
            )
            user_prompt = (
                USER_PROMPT_EXPANSION
                .replace("{sparkle}", self.sparkle)
                .replace("{finale_condition}", self.finale_condition)
                .replace("{characters_summary}", self.characters_summary)
                .replace("{previous_hook}", self.previous_hook)
                .replace("{node_id}", self.node_id)
                .replace("{node_title}", self.node_title)
                .replace("{hauge_stage_name}", self.hauge_stage_name)
                .replace("{setting}", self.setting)
                .replace("{entities}", self.entities)
                .replace("{causal_events_text}", self.causal_events_text)
                .replace("{hook}", self.hook)
                .replace("{target_word_count}", self.target_word_count)
            )

            # 扩写用纯文本模式（不用 generate_json）
            raw_text = ai_service.generate(
                user_prompt=user_prompt,
                system_prompt=system_prompt,
                temperature=self.ai_params.get("temperature", TEMPERATURE_EXPANSION),
                top_p=self.ai_params.get("top_p", 0.9),
                top_k=self.ai_params.get("top_k", 40),
                max_tokens=self.ai_params.get("max_tokens", 8192),
            )
            self.finished.emit({"text": raw_text or ""})
        except Exception as e:
            logger.error("ExpansionWorker 失败: %s", e, exc_info=True)
            self.error.emit(f"剧本扩写失败：{str(e)}")
