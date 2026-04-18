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
                max_tokens=self.ai_params.get("max_tokens", 8192),
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
                max_tokens=self.ai_params.get("max_tokens", 8192),
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
                 total_episodes: int = 20, episode_duration: int = 3,
                 drama_style_block: str = ""):
        super().__init__()
        self.sparkle = sparkle
        self.world_variables = world_variables
        self.finale_condition = finale_condition
        self.ai_params = ai_params
        self.characters = characters or []
        self.total_episodes = total_episodes
        self.episode_duration = episode_duration
        self.drama_style_block = drama_style_block

    def run(self):
        try:
            if self.total_episodes <= 30:
                self._run_single_shot()
            else:
                self._run_staged()
        except Exception as e:
            logger.error("CPGSkeletonWorker 失败: %s", e, exc_info=True)
            self.error.emit(f"CPG 骨架生成失败：{str(e)}")

    def _run_single_shot(self):
        """单次生成（≤30 集）"""
        self.progress.emit(f"🏗️ 正在生成 {self.total_episodes} 集 CPG 骨架，请稍候…")
        chars_summary = self._build_chars_summary()
        system_prompt = self._build_system_prompt()
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
            max_tokens=self.ai_params.get("max_tokens", 65536),
        )
        self.finished.emit(result)

    def _run_staged(self):
        """两遍生成法（>30 集）: 全局大纲 → 逐阶段展开"""
        from env import (SYSTEM_PROMPT_CPG_OUTLINE, USER_PROMPT_CPG_OUTLINE,
                         SYSTEM_PROMPT_CPG_EXPAND, USER_PROMPT_CPG_EXPAND)

        STAGE_NAMES_MAP = {
            1: "机会 (Opportunity)", 2: "变点 (Change of Plans)",
            3: "无路可退 (Point of No Return)", 4: "主攻/挫折 (Major Setback)",
            5: "高潮 (Climax)", 6: "终局 (Aftermath)",
        }

        chars_summary = self._build_chars_summary()
        world_json = json.dumps(self.world_variables, ensure_ascii=False, indent=2)

        # ========== Pass 1: 全局大纲 ==========
        self.progress.emit(
            f"📋 [Pass 1/2] 正在生成 {self.total_episodes} 集全局大纲…"
        )

        outline_sys = (
            SYSTEM_PROMPT_CPG_OUTLINE
            .replace("{total_episodes}", str(self.total_episodes))
            .replace("{episode_duration}", str(self.episode_duration))
        )
        if self.drama_style_block:
            outline_sys += "\n" + self.drama_style_block

        outline_usr = (
            USER_PROMPT_CPG_OUTLINE
            .replace("{sparkle}", self.sparkle)
            .replace("{world_variables_json}", world_json)
            .replace("{finale_condition}", self.finale_condition)
            .replace("{characters_summary}", chars_summary)
            .replace("{total_episodes}", str(self.total_episodes))
            .replace("{episode_duration}", str(self.episode_duration))
        )

        outline_result = ai_service.generate_json(
            user_prompt=outline_usr,
            system_prompt=outline_sys,
            temperature=self.ai_params.get("temperature", SUGGESTED_TEMPERATURES["cpg_skeleton"]),
            top_p=self.ai_params.get("top_p", 0.9),
            top_k=self.ai_params.get("top_k", 40),
            max_tokens=self.ai_params.get("max_tokens", 65536),
        )

        outline_items = outline_result.get("outline", [])
        cpg_title = outline_result.get("cpg_title", "骨架")
        logger.info("Pass 1 完成: 大纲 %d 条 (目标 %d)", len(outline_items), self.total_episodes)
        self.progress.emit(
            f"📋 大纲已生成 {len(outline_items)} 条，开始逐阶段展开…"
        )

        # 按 hauge_stage_id 分组
        from collections import defaultdict
        stage_groups = defaultdict(list)
        for item in outline_items:
            sid = item.get("hauge_stage_id", 1)
            stage_groups[sid].append(item)

        full_outline_json = json.dumps(outline_items, ensure_ascii=False, indent=1)

        # ========== Pass 2: 逐阶段展开 ==========
        all_stages = []
        all_edges = []

        for sid in range(1, 7):
            items = stage_groups.get(sid, [])
            if not items:
                continue  # 该阶段无节点
            stage_name = STAGE_NAMES_MAP[sid]
            short_name = stage_name.split("(")[0].strip()

            self.progress.emit(
                f"🏗️ [Pass 2 — {sid}/6] 展开「{short_name}」"
                f"（{len(items)} 集: {items[0]['node_id']}~{items[-1]['node_id']}）…"
            )

            # 本阶段大纲摘录
            excerpt_lines = []
            for item in items:
                excerpt_lines.append(
                    f"- {item['node_id']}: {item.get('title','')} — "
                    f"{item.get('one_line_summary','')} "
                    f"[钩子: {item.get('episode_hook','')}]"
                )
            stage_excerpt = "\n".join(excerpt_lines)

            expand_sys = (
                SYSTEM_PROMPT_CPG_EXPAND
                .replace("{stage_id}", str(sid))
                .replace("{stage_name}", stage_name)
            )
            if self.drama_style_block:
                expand_sys += "\n" + self.drama_style_block

            expand_usr = (
                USER_PROMPT_CPG_EXPAND
                .replace("{sparkle}", self.sparkle)
                .replace("{characters_summary}", chars_summary)
                .replace("{full_outline_json}", full_outline_json)
                .replace("{stage_id}", str(sid))
                .replace("{stage_name}", stage_name)
                .replace("{stage_outline_excerpt}", stage_excerpt)
            )

            result = ai_service.generate_json(
                user_prompt=expand_usr,
                system_prompt=expand_sys,
                temperature=self.ai_params.get("temperature", SUGGESTED_TEMPERATURES["cpg_skeleton"]),
                top_p=self.ai_params.get("top_p", 0.9),
                top_k=self.ai_params.get("top_k", 40),
                max_tokens=self.ai_params.get("max_tokens", 16384),
            )

            for stage in result.get("hauge_stages", []):
                stage["stage_id"] = sid
                stage["stage_name"] = stage_name
                all_stages.append(stage)
            all_edges.extend(result.get("causal_edges", []))

        # 组装最终结果
        merged = {
            "cpg_title": cpg_title,
            "total_episodes": self.total_episodes,
            "hauge_stages": all_stages,
            "causal_edges": all_edges,
        }
        self.finished.emit(merged)

    def _build_chars_summary(self) -> str:
        return "\n".join(
            f"- [{c.get('importance_level','C')}/{c.get('role_type','配角')}] {c.get('name','')}: "
            f"{c.get('personality','')} / 动机: {c.get('motivation','')}"
            for c in self.characters
        ) or "（未设定角色）"

    def _build_system_prompt(self) -> str:
        system_prompt = (
            SYSTEM_PROMPT_CPG_SKELETON
            .replace("{total_episodes}", str(self.total_episodes))
            .replace("{episode_duration}", str(self.episode_duration))
        )
        if self.drama_style_block:
            system_prompt += "\n" + self.drama_style_block
        return system_prompt


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
        drama_style_block: str = "",
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
        self.drama_style_block = drama_style_block

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

            # 构建当前节点的因果连线上下文
            node_title_map = {n["node_id"]: n.get("title", "") for n in self.cpg_nodes}
            edge_lines = []
            for e in self.cpg_edges:
                if e.get("to_node") == node_id:
                    from_title = node_title_map.get(e["from_node"], "")
                    ct = e.get("causal_type", "直接因果")
                    desc = e.get("description", "")
                    line = f"← 入边: {e['from_node']}({from_title}) --[{ct}]--> 本节点"
                    if desc:
                        line += f"  说明: {desc}"
                    edge_lines.append(line)
                if e.get("from_node") == node_id:
                    to_title = node_title_map.get(e["to_node"], "")
                    ct = e.get("causal_type", "直接因果")
                    desc = e.get("description", "")
                    line = f"→ 出边: 本节点 --[{ct}]--> {e['to_node']}({to_title})"
                    if desc:
                        line += f"  说明: {desc}"
                    edge_lines.append(line)
            edge_relations_context = "\n".join(edge_lines) if edge_lines else "（本节点无连线）"

            # 角色概要注入
            characters_summary = "\n".join(
                f"- [{c.get('importance_level','C')}/{c.get('role_type','配角')}] {c.get('name','')}: "
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
                        edge_relations_context=edge_relations_context,
                        temperature=self.ai_params.get("temperature", SUGGESTED_TEMPERATURES["variation"]),
                        top_p=self.ai_params.get("top_p", 0.9),
                        top_k=self.ai_params.get("top_k", 40),
                        max_tokens=self.ai_params.get("max_tokens", 8192),
                        drama_style_block=self.drama_style_block,
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
                max_tokens=self.ai_params.get("max_tokens", 8192),
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
    输入: sparkle, world_variables (list), finale_condition, AI 参数, existing_characters
    输出: {"characters": [...], "relations": [...], "design_notes": "..."}
    """
    def __init__(self, sparkle: str, world_variables: list, finale_condition: str,
                 ai_params: dict, char_count: int = 5,
                 existing_characters: list = None):
        super().__init__()
        self.sparkle = sparkle
        self.world_variables = world_variables
        self.finale_condition = finale_condition
        self.ai_params = ai_params
        self.char_count = char_count
        self.existing_characters = existing_characters or []

    def run(self):
        try:
            self.progress.emit(f"🎭 正在生成 {self.char_count} 个角色建议，请稍候…")

            # 构建已有角色排除块
            if self.existing_characters:
                lines = []
                for c in self.existing_characters:
                    lines.append(
                        f"- {c.get('name','?')} [{c.get('role_type','?')}/{c.get('importance_level','C')}]: "
                        f"{c.get('personality','')} / 动机: {c.get('motivation','')}"
                    )
                existing_block = (
                    "## ⚠️ 已有角色（严禁重复）\n"
                    "以下角色已经存在，你新生成的角色必须：\n"
                    "1. 名字完全不同（不能相同或相似）\n"
                    "2. 身份/职位/背景不能雷同\n"
                    "3. 应与已有角色形成互补或新的冲突关系\n\n"
                    + "\n".join(lines)
                )
            else:
                existing_block = ""

            system_prompt = SYSTEM_PROMPT_CHARACTER_GEN.replace(
                "{char_count}", str(self.char_count)
            )

            user_prompt = (
                USER_PROMPT_CHARACTER_GEN
                .replace("{sparkle}", self.sparkle)
                .replace("{world_variables_json}",
                         json.dumps(self.world_variables, ensure_ascii=False, indent=2))
                .replace("{finale_condition}", self.finale_condition)
                .replace("{char_count}", str(self.char_count))
                .replace("{existing_characters_block}", existing_block)
            )
            result = ai_service.generate_json(
                user_prompt=user_prompt,
                system_prompt=system_prompt,
                temperature=self.ai_params.get("temperature", TEMPERATURE_CHARACTER_GEN),
                top_p=self.ai_params.get("top_p", 0.9),
                top_k=self.ai_params.get("top_k", 40),
                max_tokens=self.ai_params.get("max_tokens", 8192),
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
        episode_number: int,
        incoming_edges_context: str,
        previous_screenplay_excerpt: str,
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
        drama_style_block: str = "",
    ):
        super().__init__()
        self.sparkle = sparkle
        self.finale_condition = finale_condition
        self.characters_summary = characters_summary
        self.episode_number = episode_number
        self.incoming_edges_context = incoming_edges_context
        self.previous_screenplay_excerpt = previous_screenplay_excerpt
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
        self.drama_style_block = drama_style_block

    def run(self):
        try:
            self.progress.emit(f"🎬 正在扩写 {self.node_id}：{self.node_title}…")

            # 注意：SYSTEM_PROMPT_EXPANSION 含有占位符
            system_prompt = (
                SYSTEM_PROMPT_EXPANSION
                .replace("{target_word_count}", self.target_word_count)
                .replace("{episode_duration}", str(self.episode_duration))
            )
            if self.drama_style_block:
                system_prompt += "\n" + self.drama_style_block
            user_prompt = (
                USER_PROMPT_EXPANSION
                .replace("{sparkle}", self.sparkle)
                .replace("{finale_condition}", self.finale_condition)
                .replace("{characters_summary}", self.characters_summary)
                .replace("{episode_number}", str(self.episode_number))
                .replace("{incoming_edges_context}", self.incoming_edges_context)
                .replace("{previous_screenplay_excerpt}", self.previous_screenplay_excerpt)
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


# ====================================================================
# NodeRefineWorker — 骨架节点 AI 优化
# 支持模式:
#   "chat"         — 单次对话，检测返回中是否含修改 JSON
#   "quick_regen"  — 单次或多人格并行重生成
#   "bvsr_rewrite" — 多人格并行重写，返回每个人格的候选版本
#   "split_refine" — 拆分后补全/扩写
#   "merge"        — 合并两个节点
# ====================================================================

class NodeRefineWorker(QThread):
    finished = Signal(dict)   # 根据 mode 不同内容不同，见下
    error    = Signal(str)
    progress = Signal(str)

    def __init__(
        self,
        mode: str,
        system_prompt: str,
        user_prompt: str,
        ai_params: dict,
        # BVSR 多人格专用
        persona_calls: list = None,   # [{"persona_key":str,"system_prompt":str,"user_prompt":str}]
    ):
        super().__init__()
        self.mode           = mode
        self.system_prompt  = system_prompt
        self.user_prompt    = user_prompt
        self.ai_params      = ai_params
        self.persona_calls  = persona_calls or []

    def run(self):
        import asyncio, json, re
        try:
            if self.mode in ("bvsr_rewrite", "quick_regen") and self.persona_calls:
                # 多人格并行调用
                self.progress.emit(f"正在启动 {len(self.persona_calls)} 个人格并行调用…")
                calls = [{
                    "user_prompt":   c["user_prompt"],
                    "system_prompt": c["system_prompt"],
                    "temperature":   self.ai_params.get("temperature", 1.0),
                    "top_p":         self.ai_params.get("top_p", 0.9),
                    "top_k":         self.ai_params.get("top_k", 40),
                    "max_tokens":    self.ai_params.get("max_tokens", 8192),
                    "persona_key":   c["persona_key"],
                } for c in self.persona_calls]

                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    raw_results = loop.run_until_complete(
                        ai_service.parallel_generate(calls)
                    )
                finally:
                    loop.close()

                candidates = []
                for r in raw_results:
                    if r.get("error"):
                        candidates.append({
                            "persona_key": r["persona_key"],
                            "node": None,
                            "error": r["error"],
                        })
                    else:
                        node = self._parse_node_json(r.get("result", ""))
                        candidates.append({
                            "persona_key": r["persona_key"],
                            "node": node,
                            "error": None if node else "JSON 解析失败",
                        })
                self.finished.emit({"mode": self.mode, "candidates": candidates})

            elif self.mode == "chat":
                # 单次对话调用（generate 是同步方法）
                raw = ai_service.generate(
                    user_prompt=self.user_prompt,
                    system_prompt=self.system_prompt,
                    temperature=self.ai_params.get("temperature", 0.8),
                    top_p=self.ai_params.get("top_p", 0.9),
                    top_k=self.ai_params.get("top_k", 40),
                    max_tokens=self.ai_params.get("max_tokens", 8192),
                )
                # 检测返回中是否含 {"action":"modify"} JSON
                modify_node = self._extract_modify_json(raw or "")
                self.finished.emit({
                    "mode": "chat",
                    "response": raw or "",
                    "modify_node": modify_node,   # None 表示仅讨论
                })

            else:
                # 单次调用（quick_regen 无人格 / split_refine / merge）
                mime = "application/json" if self.mode in ("split_refine", "merge", "quick_regen", "cascade_rewrite") else None
                raw = ai_service.generate(
                    user_prompt=self.user_prompt,
                    system_prompt=self.system_prompt,
                    temperature=self.ai_params.get("temperature", 0.7),
                    top_p=self.ai_params.get("top_p", 0.9),
                    top_k=self.ai_params.get("top_k", 40),
                    max_tokens=self.ai_params.get("max_tokens", 8192),
                    response_mime_type=mime,
                )

                if self.mode in ("split_refine", "cascade_rewrite"):
                    # 期望返回 JSON 数组
                    nodes = self._parse_nodes_array(raw or "")
                    self.finished.emit({"mode": self.mode, "nodes": nodes, "raw_text": raw or ""})
                else:
                    # quick_regen / merge — 期望单个节点 JSON
                    node = self._parse_node_json(raw or "")
                    self.finished.emit({"mode": self.mode, "node": node, "raw_text": raw or ""})

        except Exception as e:
            logger.error("NodeRefineWorker[%s] 失败: %s", self.mode, e, exc_info=True)
            self.error.emit(f"AI 调用失败: {str(e)}")

    # ---- 解析工具 ----

    @staticmethod
    def _parse_node_json(text: str) -> dict | None:
        """从 AI 返回文本中提取单个节点 JSON"""
        import json, re
        if not text or not text.strip():
            logger.warning("_parse_node_json: 输入为空")
            return None
        # 先尝试代码块
        m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if m:
            raw = m.group(1)
        else:
            # 找第一个 { ... }
            m = re.search(r'\{.*\}', text, re.DOTALL)
            raw = m.group(0) if m else ""
        if not raw:
            logger.warning("_parse_node_json: 未找到 JSON 块, 原始文本: %s", text[:300])
            return None
        try:
            data = json.loads(raw)
            # 验证必要字段
            if "title" in data or "event_summaries" in data:
                return data
            else:
                logger.warning("_parse_node_json: JSON 缺少 title/event_summaries, keys=%s, raw=%s",
                               list(data.keys()), text[:300])
        except json.JSONDecodeError as e:
            logger.warning("_parse_node_json: JSON 解析失败: %s, raw=%s", e, raw[:300])
        return None

    @staticmethod
    def _parse_nodes_array(text: str) -> list:
        """从 AI 返回文本中提取节点 JSON 数组"""
        import json, re
        if not text or not text.strip():
            logger.warning("_parse_nodes_array: 输入为空")
            return []
        m = re.search(r'```(?:json)?\s*(\[.*?\])\s*```', text, re.DOTALL)
        if m:
            raw = m.group(1)
        else:
            m = re.search(r'\[.*\]', text, re.DOTALL)
            raw = m.group(0) if m else ""
        if not raw:
            # 可能整个响应就是一个被截断的数组（以 [ 开头但没有 ]）
            stripped = text.strip()
            if stripped.startswith('['):
                raw = stripped
                logger.warning("_parse_nodes_array: 未找到完整数组，尝试修复截断的 JSON")
            else:
                logger.warning("_parse_nodes_array: 未找到 JSON 数组, 原始文本: %s", text[:300])
                return []
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                logger.info("_parse_nodes_array: 成功解析 %d 个节点", len(data))
                return data
        except json.JSONDecodeError as e:
            logger.warning("_parse_nodes_array: 解析失败(%s)，尝试修复截断的 JSON", e)
            # 尝试修复截断的 JSON
            try:
                from services.ai_service import AIService
                repaired = AIService._repair_truncated_json(raw)
                data = json.loads(repaired)
                if isinstance(data, list):
                    logger.info("_parse_nodes_array: 修复后成功解析 %d 个节点", len(data))
                    return data
            except Exception as e2:
                logger.warning("_parse_nodes_array: 修复后仍失败: %s", e2)
        return []

    @staticmethod
    def _extract_modify_json(text: str) -> dict | None:
        """检测 Chat 回复中是否含 {"action":"modify",...} JSON"""
        import json, re
        m = re.search(r'```(?:json)?\s*(\{.*?"action"\s*:\s*"modify".*?\})\s*```',
                      text, re.DOTALL)
        if m:
            raw = m.group(1)
        else:
            m = re.search(r'\{[^{}]*"action"\s*:\s*"modify"[^{}]*\}', text, re.DOTALL)
            if not m:
                # 宽松匹配包含嵌套的情况
                m = re.search(r'\{.*?"action"\s*:\s*"modify".*?\}', text, re.DOTALL)
            raw = m.group(0) if m else ""
        if not raw:
            return None
        try:
            data = json.loads(raw)
            if data.get("action") == "modify" and "node" in data:
                return data["node"]
        except json.JSONDecodeError:
            pass
        return None

