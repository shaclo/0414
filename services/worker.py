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
from services.cp_interaction_engine import CPInteractionEngine
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

from services.logger_service import app_logger


# ============================================================
# v1.1.6 Schema 归一化辅助函数
# 用途：把 AI 返回的 event_units 同步生成 event_summaries（旧字段兼容），
#       同时验证场景多样性、钩子配比、阶段隔离铁律。
# ============================================================

# 阶段隔离铁律：骨架阶段禁用的 CP 关键词
_BANNED_CP_KEYWORDS_IN_SKELETON = [
    "撩拨", "吃醋", "调情", "亲吻", "拥抱", "护妻揽腰",
    "双向奔赴", "贴耳低语", "情侣式互动", "缠绵热吻",
    "搂着腰", "捏脸", "撒娇", "心动",
]


def _format_chars_summary(characters: list) -> str:
    """
    v1.1.6 — 角色摘要格式化（注入到 prompt 中）。
    在原有信息的基础上加入 signature_traits / arc_outline / cp_role。
    """
    if not characters:
        return "（未设定角色）"
    lines: list[str] = []
    for c in characters:
        base = (
            f"- [{c.get('importance_level','C')}/{c.get('role_type','配角')}] "
            f"{c.get('name','')}（{c.get('gender','未知')}，"
            f"{c.get('age','未知')}岁，{c.get('position','')}）: "
            f"{c.get('personality','')} / 动机: {c.get('motivation','')}"
        )
        traits = c.get("signature_traits") or []
        if traits:
            base += f" / 极致人设: {' + '.join(traits)}"
        arc = c.get("arc_outline") or ""
        if arc:
            base += f" / 弧线: {arc}"
        cp_role = c.get("cp_role") or ""
        if cp_role:
            base += f" / 冲突关系角色: {cp_role}"
        lines.append(base)
    return "\n".join(lines)


def _normalize_skeleton_v1_1_6(result: dict) -> dict:
    """
    将 AI 返回的骨架结果归一化到 v1.1.6 schema：
      1. 若节点含 event_units 而 event_summaries 为空，从 event_units.action 同步生成；
      2. 给结果打上 cpg_schema_version=2 标识；
      3. 扫描骨架阶段是否含 CP 关键词（仅日志警告，不阻塞流程，避免误杀）；
      4. 同场景停留校验（main_scene 连续 ≥3 集相同时给出警告）；
      5. ITE 闭环裁剪报告（基于 event_units[i].tau_estimate 离线扫描）。

    返回归一化后的结果（原地修改并返回，附加 _ite_report / _scene_warnings / _cp_violations）。
    """
    if not isinstance(result, dict):
        return result

    cp_violations: list[str] = []
    has_event_units = False
    flat_nodes: list[dict] = []  # 扁平节点列表，用于 ITE 裁剪

    for stage in result.get("hauge_stages", []) or []:
        for node in stage.get("nodes", []) or []:
            units = node.get("event_units") or []
            summaries = node.get("event_summaries") or []
            if units:
                has_event_units = True
                # 旧字段同步：从 event_units 抽取 action 文本
                if not summaries:
                    node["event_summaries"] = [
                        (u.get("action") or "").strip()
                        for u in units
                        if u.get("action")
                    ]
            # 阶段隔离铁律扫描（仅警告）
            scan_text = " ".join([
                node.get("opening_hook", "") or "",
                node.get("episode_hook", "") or "",
                " ".join(node.get("event_summaries", []) or []),
                " ".join(
                    (u.get("action") or "") for u in units
                ),
            ])
            for kw in _BANNED_CP_KEYWORDS_IN_SKELETON:
                if kw in scan_text:
                    cp_violations.append(
                        f"{node.get('node_id', '?')} 含 CP 关键词「{kw}」"
                    )
                    break
            # 收集扁平节点（带 hauge_stage_id 信息）
            flat = dict(node)
            flat["hauge_stage_id"] = stage.get("stage_id", flat.get("hauge_stage_id", 0))
            flat_nodes.append(flat)

    # 标记 schema 版本
    if has_event_units:
        result["cpg_schema_version"] = 2

    # 同场景停留校验（v1.1.6 P0-3）
    scene_warnings = _detect_scene_continuity_violations(flat_nodes)

    # ITE 闭环裁剪（v1.1.6 P0-2）
    ite_report = None
    if has_event_units:
        try:
            ite_report = ite_calculator.compress_redundant_nodes(flat_nodes)
        except Exception as exc:
            logger.warning("ITE 离线裁剪失败：%s", exc)

    # 把元数据附加到结果上（不影响 AI 调用，仅供 UI 消费）
    result["_meta"] = result.get("_meta") or {}
    if ite_report is not None:
        result["_meta"]["ite_report"] = ite_report
    if scene_warnings:
        result["_meta"]["scene_warnings"] = scene_warnings
    if cp_violations:
        result["_meta"]["cp_violations"] = cp_violations[:20]

    if cp_violations:
        logger.warning(
            "骨架阶段隔离铁律警告：检测到 %d 个节点含 CP 关键词（应在血肉阶段补充）：\n%s",
            len(cp_violations), "\n".join(cp_violations[:10])
        )
    if scene_warnings:
        logger.warning(
            "骨架场景多样性警告（共 %d 项）：\n%s",
            len(scene_warnings), "\n".join(scene_warnings[:10])
        )
    if ite_report and ite_report.get("merge_suggestions"):
        logger.info(
            "ITE 闭环：%d 个冗余事件、%d 处合并建议、%d 处阶段警告",
            ite_report["summary"]["redundant_count"],
            len(ite_report["merge_suggestions"]),
            len(ite_report["stage_warnings"]),
        )

    return result


def _detect_scene_continuity_violations(flat_nodes: list[dict]) -> list[str]:
    """
    v1.1.6 P0-3 — 检测同一 main_scene 连续 ≥3 集出现的情况，返回警告列表。
    """
    warnings: list[str] = []
    run_start = -1
    run_scene = ""
    for i, node in enumerate(flat_nodes):
        scene = (node.get("main_scene") or "").strip()
        if not scene:
            run_start = -1
            run_scene = ""
            continue
        if scene == run_scene:
            length = i - run_start + 1
            if length == 3:
                warnings.append(
                    f"{flat_nodes[run_start].get('node_id','?')} ~ "
                    f"{node.get('node_id','?')} 共 {length} 集停留在「{scene}」"
                    "，请切换地点（同一主场景最多跨 2 集）"
                )
            elif length > 3:
                warnings[-1] = (
                    f"{flat_nodes[run_start].get('node_id','?')} ~ "
                    f"{node.get('node_id','?')} 共 {length} 集停留在「{scene}」"
                    "，请切换地点（同一主场景最多跨 2 集）"
                )
        else:
            run_start = i
            run_scene = scene
    return warnings


def _normalize_skeleton_segment_v1_1_6(result: dict) -> dict:
    """
    分段生成的归一化（result 顶层是 {"nodes": [...]} 结构）。
    """
    if not isinstance(result, dict):
        return result
    has_event_units = False
    for node in result.get("nodes", []) or []:
        units = node.get("event_units") or []
        if units:
            has_event_units = True
            if not node.get("event_summaries"):
                node["event_summaries"] = [
                    (u.get("action") or "").strip()
                    for u in units
                    if u.get("action")
                ]
    if has_event_units:
        result.setdefault("_meta", {})["cpg_schema_version"] = 2
    return result


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
                 total_episodes: int = 20, episode_duration: str = "3",
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

        app_logger.log_ai_call(
            module="骨架生成-Worker（单次）",
            action=f"AI 调用：生成 {self.total_episodes} 集 CPG 骨架（单次模式）",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            extra_params={
                "总集数": self.total_episodes,
                "每集时长": self.episode_duration,
                "温度": self.ai_params.get("temperature"),
                "max_tokens": self.ai_params.get("max_tokens"),
            },
        )

        result = ai_service.generate_json(
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=self.ai_params.get("temperature", SUGGESTED_TEMPERATURES["cpg_skeleton"]),
            top_p=self.ai_params.get("top_p", 0.9),
            top_k=self.ai_params.get("top_k", 40),
            max_tokens=self.ai_params.get("max_tokens", 65536),
        )

        # v1.1.6 schema 归一化：event_units → event_summaries 同步 + 阶段隔离扫描
        result = _normalize_skeleton_v1_1_6(result)

        stages = result.get("hauge_stages", [])
        node_count = sum(len(s.get("nodes", [])) for s in stages)
        schema_ver = result.get("cpg_schema_version", 1)
        app_logger.log_ai_result(
            module="骨架生成-Worker（单次）",
            action="CPG 骨架生成完成",
            result_summary=f"生成 {node_count} 个节点，{len(result.get('causal_edges', []))} 条因果边，schema v{schema_ver}",
            result_detail=json.dumps(result, ensure_ascii=False, indent=2),
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
        # v1.1.6 schema 归一化
        merged = _normalize_skeleton_v1_1_6(merged)
        self.finished.emit(merged)

    def _build_chars_summary(self) -> str:
        return _format_chars_summary(self.characters)

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
# AI-Call-3b: 分段骨架生成（逐段确认模式）
# ============================================================
class SegmentSkeletonWorker(BaseWorker):
    """
    分段骨架生成 Worker。
    根据 start_ep ~ end_ep 范围生成骨架节点，
    支持钩子链（传入前一章 episode_hook）和章节特殊指令。
    """
    def __init__(self, sparkle, world_variables, finale_condition,
                 characters, ai_params, start_ep, end_ep,
                 total_episodes, episode_duration,
                 confirmed_nodes=None, drama_style_block="",
                 hook_ids=None):
        super().__init__()
        self.sparkle = sparkle
        self.world_variables = world_variables
        self.finale_condition = finale_condition
        self.characters = characters or []
        self.ai_params = ai_params
        self.start_ep = start_ep
        self.end_ep = end_ep
        self.total_episodes = total_episodes
        self.episode_duration = episode_duration
        self.confirmed_nodes = confirmed_nodes or []
        self.drama_style_block = drama_style_block
        self.hook_ids = hook_ids or []

    def run(self):
        try:
            from env import (
                SYSTEM_PROMPT_SKELETON_SEGMENT, USER_PROMPT_SKELETON_SEGMENT,
                CHAPTER1_INSTRUCTION, CHAPTER_EARLY_INSTRUCTION,
            )

            segment_count = self.end_ep - self.start_ep + 1
            position_percent = int(self.start_ep / self.total_episodes * 100)
            self.progress.emit(
                f"正在生成第 {self.start_ep}~{self.end_ep} 集骨架（共{segment_count}集）..."
            )

            # 构建章节特殊指令
            chapter_instruction = ""
            if self.start_ep == 1:
                chapter_instruction = CHAPTER1_INSTRUCTION
            elif self.start_ep <= 3:
                chapter_instruction = CHAPTER_EARLY_INSTRUCTION.replace(
                    "{current_ep}", str(self.start_ep)
                )

            # 构建已确认上下文
            confirmed_context = self._build_confirmed_context()

            # 构建前一章钩子（程序化传入，非AI自行查找）
            previous_hook_block = ""
            if self.confirmed_nodes:
                last_node = self.confirmed_nodes[-1]
                last_hook = last_node.get("episode_hook", "")
                last_id = last_node.get("node_id", "")
                last_title = last_node.get("title", "")
                if last_hook:
                    previous_hook_block = (
                        f"## ⚠️ 上一集的结尾悬念钩子（必须紧密承接！）\n"
                        f"上一集 {last_id}「{last_title}」的结尾悬念：\n"
                        f"「{last_hook}」\n\n"
                        f"### 强制衔接要求：\n"
                        f"1. 第 {self.start_ep} 集的 opening_hook 必须是对上述悬念的**直接续写**，"
                        f"同一场景、同一时间线、同一紧张状态\n"
                        f"2. 第 {self.start_ep} 集的第一个 event_summary 必须**立即回应**这个悬念——"
                        f"不允许跳过、不允许时间跳跃、不允许换场景开始\n"
                        f"3. 观众看到第 {self.start_ep} 集开头时，必须感觉是上一集最后一秒的**无缝延续**"
                    )

            # 构建角色摘要（v1.1.6：含 signature_traits / arc_outline）
            chars_summary = _format_chars_summary(self.characters)

            system_prompt = (
                SYSTEM_PROMPT_SKELETON_SEGMENT
                .replace("{total_episodes}", str(self.total_episodes))
                .replace("{episode_duration}", str(self.episode_duration))
                .replace("{start_ep}", str(self.start_ep))
                .replace("{end_ep}", str(self.end_ep))
                .replace("{segment_count}", str(segment_count))
                .replace("{position_percent}", str(position_percent))
                .replace("{chapter_specific_instruction}", chapter_instruction)
            )
            if self.drama_style_block:
                system_prompt += "\n" + self.drama_style_block

            # 注入用户选择的钩子公式（随机抽 1 个）
            if self.hook_ids:
                import random as _rnd
                from config.prompt_templates import prompt_template_manager
                pick = _rnd.sample(self.hook_ids, 1)
                hook_inj = prompt_template_manager.build_hook_prompt_by_ids(pick)
                if hook_inj:
                    system_prompt += "\n\n" + hook_inj

            world_vars_json = json.dumps(
                self.world_variables, ensure_ascii=False, indent=2
            ) if self.world_variables else "{}"

            user_prompt = (
                USER_PROMPT_SKELETON_SEGMENT
                .replace("{sparkle}", self.sparkle)
                .replace("{world_variables_json}", world_vars_json)
                .replace("{finale_condition}", self.finale_condition)
                .replace("{characters_summary}", chars_summary)
                .replace("{total_episodes}", str(self.total_episodes))
                .replace("{episode_duration}", str(self.episode_duration))
                .replace("{start_ep}", str(self.start_ep))
                .replace("{end_ep}", str(self.end_ep))
                .replace("{confirmed_context}", confirmed_context)
                .replace("{previous_hook_block}", previous_hook_block)
            )

            app_logger.log_ai_call(
                module="骨架-分段生成",
                action=f"AI 调用：生成第 {self.start_ep}~{self.end_ep} 集骨架",
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                extra_params={
                    "起始集": self.start_ep, "结束集": self.end_ep,
                    "总集数": self.total_episodes,
                    "已确认节点数": len(self.confirmed_nodes),
                    "温度": self.ai_params.get("temperature"),
                },
            )

            result = ai_service.generate_json(
                user_prompt=user_prompt,
                system_prompt=system_prompt,
                temperature=self.ai_params.get("temperature", 0.5),
                top_p=self.ai_params.get("top_p", 0.9),
                top_k=self.ai_params.get("top_k", 40),
                max_tokens=self.ai_params.get("max_tokens", 16384),
            )

            # v1.1.6 schema 归一化（分段版）
            result = _normalize_skeleton_segment_v1_1_6(result)
            nodes = result.get("nodes", [])
            schema_ver = result.get("_meta", {}).get("cpg_schema_version", 1)
            app_logger.log_ai_result(
                module="骨架-分段生成",
                action=f"分段骨架完成：第 {self.start_ep}~{self.end_ep} 集",
                result_summary=f"生成 {len(nodes)} 个节点，schema v{schema_ver}",
                result_detail=json.dumps(result, ensure_ascii=False, indent=2),
            )
            self.finished.emit(result)
        except Exception as e:
            logger.error("SegmentSkeletonWorker 失败: %s", e, exc_info=True)
            app_logger.error("骨架-分段生成", f"分段骨架生成失败: {str(e)}")
            self.error.emit(f"分段骨架生成失败：{str(e)}")

    def _build_confirmed_context(self):
        """将已确认节点构建为结构化上下文（完整内容，不截断）"""
        if not self.confirmed_nodes:
            return ""
        lines = ["## 已确认章节（前文上下文 — 请严格保持剧情一致性）"]
        for n in self.confirmed_nodes:
            nid = n.get("node_id", "")
            title = n.get("title", "")
            stage = n.get("hauge_stage_name", "")
            setting = n.get("setting", "")
            chars = ", ".join(n.get("characters", []))
            events = n.get("event_summaries", [])
            events_text = "\n".join(f"  {i+1}. {e}" for i, e in enumerate(events))
            tone = n.get("emotional_tone", "")
            hook = n.get("episode_hook", "")
            opening = n.get("opening_hook", "")

            lines.append(f"\n### {nid}: {title} [{stage}]")
            if setting:
                lines.append(f"环境: {setting}")
            if chars:
                lines.append(f"角色: {chars}")
            if tone:
                lines.append(f"情感基调: {tone}")
            if opening:
                lines.append(f"开篇衔接: {opening}")
            if events_text:
                lines.append(f"事件:\n{events_text}")
            if hook:
                lines.append(f"🎣 结尾悬念钩子: {hook}")
        return "\n".join(lines)


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
        provider_pool: list = None,
        satisfaction_prompt_injection: str = "",
        hook_prompt_injection: str = "",
        previous_episode_hook: str = "",
        cp_engine: CPInteractionEngine = None,
        project_data=None,
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
        self.provider_pool = provider_pool
        self.satisfaction_prompt_injection = satisfaction_prompt_injection
        self.hook_prompt_injection = hook_prompt_injection
        self.previous_episode_hook = previous_episode_hook
        self.cp_engine = cp_engine
        self.project_data = project_data

    def _build_character_micro_change_requirement(self, target_node):
        # Build character micro change requirement dynamically
        char_lines = []
        for char in self.characters:
            if char.get("importance_level") == "A":
                arc = char.get("arc_outline") if char.get("arc_outline") else "未知"
                char_lines.append(f"- A级角色「{char.get('name')}」当前 arc_outline: {arc}")
        if char_lines:
            char_lines.append("- 必须有 1 处微变化，通过具体动作或台词外化，禁止内心独白。")
            return "## 本集人物变化要求\n" + "\n".join(char_lines)
        return "## 本集人物变化要求\n- 无A级角色，按设定发挥"

    def _build_hook_history_constraint(self):
        if not self.project_data:
            return "## 钩子配比约束\n- 自由发挥，但注意后续需记录"
        hook_history = getattr(self.project_data, "cp_hook_history", [])
        if not hook_history:
            return "## 钩子配比约束\n- 自由发挥，但注意后续需记录"
        last_hooks = ", ".join(hook_history[-3:])
        return f"## 钩子配比约束\n- 最近 3 集已用钩子类型: [{last_hooks}]\n- 本集需避开最近连续出现的类型"

    def _build_scene_continuity_constraint(self):
        # find recent scenes from cpg nodes
        recent_scenes = []
        for node in reversed(self.cpg_nodes):
            if node.get("node_id") == self.target_node.get("node_id"):
                continue
            if node.get("main_scene"):
                recent_scenes.append(node.get("main_scene"))
            if len(recent_scenes) >= 2:
                break
        if len(recent_scenes) >= 2 and recent_scenes[0] == recent_scenes[1]:
            return f"## 场景切换硬约束\n- 最近 2 集主场景: [{recent_scenes[0]}, {recent_scenes[1]}]\n- 本集禁止使用主场景: {recent_scenes[0]}（已连续 2 集），必须切换到新地点。"
        elif recent_scenes:
            scenes_str = ", ".join(recent_scenes)
            return f"## 场景切换硬约束\n- 最近 1-2 集主场景: [{scenes_str}]\n- 如无必要，可不切换，但注意上限 2 集。"
        return "## 场景切换硬约束\n- 自由选择主场景，注意连贯性。"

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

            # 角色概要注入（v1.1.6：含 signature_traits / arc_outline）
            characters_summary_with_traits = _format_chars_summary(self.characters)
            
            cp_suggestion_block = ""
            if self.project_data and getattr(self.project_data, "has_cp_main_line", False) and self.cp_engine:
                cp_suggestion = self.cp_engine.sample(self.target_node, self.project_data, stage="flesh")
                if cp_suggestion:
                    cp_suggestion_block = f"## 人物关系互动建议（必须采用，可改写不可省略）\n- 模板 ID: {cp_suggestion['id']}\n- 模板原文: {cp_suggestion['raw_template']}\n- 已渲染: {cp_suggestion['rendered_text']}\n- 钩子类型: {cp_suggestion['hook_type']}\n- 嵌入要求: 必须嵌入本集某个具体因果事件，占本集篇幅 ≤30%"

            character_micro_change_requirement = self._build_character_micro_change_requirement(self.target_node)
            hook_history_constraint = self._build_hook_history_constraint()
            scene_continuity_constraint = self._build_scene_continuity_constraint()

            # 提取主角核心目标（从角色表中找 importance_level=A 的主角）
            protagonist_goal = ""
            for c in self.characters:
                if c.get("importance_level") == "A" or c.get("role_type") == "主角":
                    name = c.get("name", "")
                    motivation = c.get("motivation", "")
                    protagonist_goal = f"{name}：{motivation}" if motivation else ""
                    break

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
                        protagonist_goal=protagonist_goal,
                        characters_summary_with_traits=characters_summary_with_traits,
                        provider_pool=self.provider_pool,
                        satisfaction_prompt_injection=self.satisfaction_prompt_injection,
                        hook_prompt_injection=self.hook_prompt_injection,
                        previous_episode_hook=self.previous_episode_hook,
                        cp_suggestion_block=cp_suggestion_block,
                        character_micro_change_requirement=character_micro_change_requirement,
                        hook_history_constraint=hook_history_constraint,
                        scene_continuity_constraint=scene_continuity_constraint,
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
            app_logger.error("血肉-变异Worker", f"盲视变异失败: {str(e)}")
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
        episode_duration: str = "3",
        scenes_per_episode: str = "1-2",
        drama_style_block: str = "",
        satisfaction_prompt_injection: str = "",
        hook_prompt_injection: str = "",
        world_variables_json: str = "",
        opening_hook: str = "",
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
        self.scenes_per_episode = scenes_per_episode
        self.drama_style_block = drama_style_block
        self.satisfaction_prompt_injection = satisfaction_prompt_injection
        self.hook_prompt_injection = hook_prompt_injection
        self.world_variables_json = world_variables_json
        self.opening_hook = opening_hook

    def run(self):
        try:
            self.progress.emit(f"🎬 正在扩写 {self.node_id}：{self.node_title}…")

            # 注意：SYSTEM_PROMPT_EXPANSION 含有占位符
            system_prompt = (
                SYSTEM_PROMPT_EXPANSION
                .replace("{target_word_count}", self.target_word_count)
                .replace("{episode_duration}", str(self.episode_duration))
                .replace("{scenes_per_episode}", self.scenes_per_episode)
            )
            if self.drama_style_block:
                system_prompt += "\n" + self.drama_style_block

            # 注入爽感公式（UI 选择 或 随机抽样）
            if self.satisfaction_prompt_injection:
                system_prompt += "\n\n" + self.satisfaction_prompt_injection
            else:
                from config.prompt_templates import prompt_template_manager
                sat_inj = prompt_template_manager.sample_satisfaction_prompt(3)
                if sat_inj:
                    system_prompt += "\n\n" + sat_inj

            # 注入钩子公式（UI 选择 或 随机抽样）
            if self.hook_prompt_injection:
                system_prompt += "\n\n" + self.hook_prompt_injection
            else:
                from config.prompt_templates import prompt_template_manager
                hook_inj = prompt_template_manager.sample_hook_prompt(3)
                if hook_inj:
                    system_prompt += "\n\n" + hook_inj

            user_prompt = (
                USER_PROMPT_EXPANSION
                .replace("{sparkle}", self.sparkle)
                .replace("{finale_condition}", self.finale_condition)
                .replace("{world_variables_json}", self.world_variables_json)
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
                .replace("{opening_hook}", self.opening_hook)
                .replace("{hook}", self.hook)
                .replace("{target_word_count}", self.target_word_count)
            )

            app_logger.log_ai_call(
                module=f"扩写-Worker（{self.node_id}）",
                action=f"AI 调用：扩写 {self.node_id}《{self.node_title}》",
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                extra_params={
                    "节点": self.node_id,
                    "标题": self.node_title,
                    "目标字数": self.target_word_count,
                    "温度": self.ai_params.get("temperature"),
                    "max_tokens": self.ai_params.get("max_tokens"),
                },
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

            char_count = len(raw_text) if raw_text else 0
            app_logger.log_ai_result(
                module=f"扩写-Worker（{self.node_id}）",
                action=f"扩写完成：{self.node_id}《{self.node_title}》",
                result_summary=f"返回剧本文本 {char_count} 字",
                result_detail=raw_text or "（空）",
            )
            self.finished.emit({"text": raw_text or ""})
        except Exception as e:
            logger.error("ExpansionWorker 失败: %s", e, exc_info=True)
            app_logger.error(f"扩写-Worker（{self.node_id}）", f"剧本扩写失败: {str(e)}")
            self.error.emit(f"剧本扩写失败：{str(e)}")


# ====================================================================
# HookRewriteWorker — 单集钩子重写
# ====================================================================

class HookRewriteWorker(BaseWorker):
    """
    为指定集重新生成结尾钩子（episode_hook）。
    可选地参考下一集的 opening_hook 和事件摘要以保持连贯。
    """
    def __init__(self, node_id, event_summaries, setting, characters,
                 emotional_tone, hook_ids, ai_params,
                 next_node_id="", next_opening_hook="", next_events=None):
        super().__init__()
        self.node_id = node_id
        self.event_summaries = event_summaries or []
        self.setting = setting
        self.characters = characters or []
        self.emotional_tone = emotional_tone
        self.hook_ids = hook_ids or []
        self.ai_params = ai_params
        self.next_node_id = next_node_id
        self.next_opening_hook = next_opening_hook
        self.next_events = next_events or []

    def run(self):
        try:
            from config.prompt_templates import prompt_template_manager

            events_text = "\n".join(
                f"  {i+1}. {e}" for i, e in enumerate(self.event_summaries)
            )
            chars_text = ", ".join(self.characters) if self.characters else "（未设定）"

            # 钩子公式注入
            hook_prompt = ""
            if self.hook_ids:
                hook_prompt = prompt_template_manager.build_hook_prompt_by_ids(self.hook_ids)

            # 后续章节参考
            next_context = ""
            if self.next_node_id and self.next_opening_hook:
                next_events_text = "\n".join(
                    f"  {i+1}. {e}" for i, e in enumerate(self.next_events[:3])
                )
                next_context = (
                    f"\n## 后续章节参考（必须保持连贯！）\n"
                    f"下一集 {self.next_node_id} 的开头衔接：\n"
                    f"「{self.next_opening_hook}」\n"
                )
                if next_events_text:
                    next_context += f"\n下一集的前几个事件：\n{next_events_text}\n"
                next_context += (
                    f"\n→ 新钩子必须能**自然引向**上述下一集的开头，"
                    f"观众看完钩子后对下一集开头的内容不会感到意外。"
                )

            system_prompt = (
                f"你是一位专业的短剧编剧，精通各种悬念钩子写作技巧。\n"
                f"请为第 {self.node_id} 集重新生成一个结尾悬念钩子（episode_hook）。\n\n"
                f"## 本集内容\n"
                f"- 环境: {self.setting}\n"
                f"- 角色: {chars_text}\n"
                f"- 情感基调: {self.emotional_tone}\n"
                f"- 事件摘要:\n{events_text}\n"
            )

            if hook_prompt:
                system_prompt += f"\n{hook_prompt}\n"

            if next_context:
                system_prompt += next_context

            system_prompt += (
                f"\n\n## 钩子写作要求\n"
                f"1. 钩子必须是「正在发生的动作被中断」，而非「已经结束的事情被描述」\n"
                f"2. 必须包含具体角色名 + 具体动作 + 悬念\n"
                f"3. 字数控制在 80-150 字之间\n"
                f"4. 画面感要强，可以用「画面定格」「镜头」等电影语言\n"
            )

            user_prompt = (
                f"请为第 {self.node_id} 集生成一个全新的结尾悬念钩子。\n\n"
                f"严格输出以下 JSON 格式：\n"
                f'{{"episode_hook": "你的钩子文本"}}'
            )

            app_logger.log_ai_call(
                module="钩子重写",
                action=f"重写 {self.node_id} 的结尾钩子",
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )

            result = ai_service.generate_json(
                user_prompt=user_prompt,
                system_prompt=system_prompt,
                temperature=self.ai_params.get("temperature", 0.7),
                top_p=self.ai_params.get("top_p", 0.9),
                top_k=self.ai_params.get("top_k", 40),
                max_tokens=self.ai_params.get("max_tokens", 2048),
            )

            hook_text = result.get("episode_hook", "")
            app_logger.log_ai_result(
                module="钩子重写",
                action=f"{self.node_id} 钩子重写完成",
                result_summary=f"新钩子: {hook_text[:50]}...",
                result_detail=hook_text,
            )
            self.finished.emit({"episode_hook": hook_text})

        except Exception as e:
            logger.error("HookRewriteWorker 失败: %s", e, exc_info=True)
            app_logger.error("钩子重写", f"重写失败: {str(e)}")
            self.error.emit(f"钩子重写失败：{str(e)}")


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
            app_logger.error(f"骨架节点精炼-Worker（{self.mode}）", f"AI 调用失败: {str(e)}")
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


# ============================================================
# AI-Call-1b/1c: 苏格拉底问答自动回答 + 逻辑校验
# ============================================================
class AutoAnswerWorker(BaseWorker):
    """
    后台执行自动回答流程（两步）：
      Step 1 — 按选定风格策略生成所有问题的答案
      Step 2 — AI 逻辑校验，不合理的答案自动修正

    输入:
        sparkle      — 故事种子
        questions    — [{id, dimension, question, rationale}, ...]
        strategy_key — 风格策略键
        ai_params    — AI 参数
    """

    def __init__(self, sparkle: str, questions: list, strategy_key: str, ai_params: dict):
        super().__init__()
        self.sparkle = sparkle
        self.questions = questions
        self.strategy_key = strategy_key
        self.ai_params = ai_params

    def run(self):
        try:
            from services.answer_strategy_manager import answer_strategy_manager
            from env import (
                SYSTEM_PROMPT_AUTO_ANSWER, USER_PROMPT_AUTO_ANSWER,
                SYSTEM_PROMPT_ANSWER_VERIFY, USER_PROMPT_ANSWER_VERIFY,
                SUGGESTED_TEMPERATURES,
            )

            strategy_info = answer_strategy_manager.get(self.strategy_key)
            strategy_instruction = strategy_info.get("instruction", "")
            strategy_label = strategy_info.get("label", self.strategy_key)

            # ── Step 1: 生成答案 ──
            self.progress.emit(f"✍️ 正在以「{strategy_label}」风格生成答案…")

            questions_json = json.dumps(
                [{"id": q.get("id"), "question": q.get("question"),
                  "dimension": q.get("dimension", "")}
                 for q in self.questions],
                ensure_ascii=False, indent=2,
            )

            system_gen = SYSTEM_PROMPT_AUTO_ANSWER.replace(
                "{strategy_instruction}", strategy_instruction
            )
            user_gen = (
                USER_PROMPT_AUTO_ANSWER
                .replace("{sparkle}", self.sparkle)
                .replace("{questions_json}", questions_json)
            )

            app_logger.log_ai_call(
                module="创世-自动回答",
                action=f"AI 生成答案（策略：{strategy_label}）",
                system_prompt=system_gen,
                user_prompt=user_gen,
                extra_params={
                    "策略": strategy_label,
                    "问题数": len(self.questions),
                    "温度": self.ai_params.get("temperature"),
                    "max_tokens": self.ai_params.get("max_tokens"),
                },
            )

            gen_result = ai_service.generate_json(
                user_prompt=user_gen,
                system_prompt=system_gen,
                temperature=self.ai_params.get("temperature",
                                                SUGGESTED_TEMPERATURES["auto_answer"]),
                top_p=self.ai_params.get("top_p", 0.9),
                top_k=self.ai_params.get("top_k", 40),
                max_tokens=self.ai_params.get("max_tokens", 4096),
            )
            raw_answers = gen_result.get("answers", [])
            answer_map = {a["id"]: a["answer"] for a in raw_answers if "id" in a}

            app_logger.log_ai_result(
                module="创世-自动回答",
                action=f"Step 1 完成（{strategy_label}）",
                result_summary=f"生成 {len(raw_answers)} 条答案",
                result_detail=str(gen_result),
            )

            # ── Step 2: 逻辑校验 ──
            self.progress.emit("🔍 正在校验答案逻辑一致性…")

            qa_for_verify = [
                {"id": q.get("id"), "question": q.get("question"),
                 "dimension": q.get("dimension", ""),
                 "answer": answer_map.get(q.get("id"), "")}
                for q in self.questions
            ]
            qa_pairs_json = json.dumps(qa_for_verify, ensure_ascii=False, indent=2)

            user_verify = (
                USER_PROMPT_ANSWER_VERIFY
                .replace("{sparkle}", self.sparkle)
                .replace("{qa_pairs_json}", qa_pairs_json)
            )

            app_logger.log_ai_call(
                module="创世-自动回答",
                action="AI 逻辑校验答案",
                system_prompt=SYSTEM_PROMPT_ANSWER_VERIFY,
                user_prompt=user_verify,
                extra_params={
                    "校验问答对数": len(qa_for_verify),
                    "温度": self.ai_params.get("temperature"),
                },
            )

            verify_result = ai_service.generate_json(
                user_prompt=user_verify,
                system_prompt=SYSTEM_PROMPT_ANSWER_VERIFY,
                temperature=self.ai_params.get("temperature",
                                                SUGGESTED_TEMPERATURES["answer_verify"]),
                top_p=self.ai_params.get("top_p", 0.9),
                top_k=self.ai_params.get("top_k", 40),
                max_tokens=self.ai_params.get("max_tokens", 4096),
            )

            verified = verify_result.get("verified_answers", [])
            revised_count = sum(1 for v in verified if v.get("revised"))

            app_logger.log_ai_result(
                module="创世-自动回答",
                action="Step 2 校验完成",
                result_summary=f"校验 {len(verified)} 条答案，其中 {revised_count} 条被修正",
                result_detail=str(verify_result),
            )

            final_answers = [
                {"id": v["id"], "answer": v["answer"], "revised": v.get("revised", False)}
                for v in verified
            ]

            self.finished.emit({
                "answers": final_answers,
                "revised_count": revised_count,
                "strategy_label": strategy_label,
            })

        except Exception as e:
            logger.error("AutoAnswerWorker 失败: %s", e, exc_info=True)
            app_logger.error("创世-自动回答", f"自动回答失败: {str(e)}")
            self.error.emit(f"自动回答失败：{str(e)}")
