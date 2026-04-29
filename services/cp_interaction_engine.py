import json
import random
import os
from typing import Dict, Any, List

class CPInteractionEngine:
    """CP 互动模板抽样引擎。仅在血肉阶段（Phase 4）被 worker 调用。"""

    STAGE_WHITELIST = {"flesh"}  # 仅血肉阶段允许调用

    GENRE_TO_CP_LIBRARY = {
        # project_state.story_genre -> cp_interaction_templates.genre_exclusive_library key
        "fantasy":   "fantasy_thriller",
        "suspense":  "fantasy_thriller",
        "revenge":   "rebirth_revenge",
        "romance":   "modern_sweet",
        "urban":     "urban_counterattack",
        "crime":     None,           # 未对应专属库 -> 仅用 core_basic_library
        "comedy":    None,           # 同上
        "custom":    None,           # 同上
    }

    def __init__(self, template_path="config/cp_interaction_templates.json"):
        self.template_path = template_path
        self.templates = {}
        self._load_templates()

    def _load_templates(self):
        if not os.path.exists(self.template_path):
            self.templates = {}
            return
        
        try:
            with open(self.template_path, "r", encoding="utf-8") as f:
                self.templates = json.load(f)
        except json.JSONDecodeError as e:
            # 兼容旧版本 JSON 可能的语法错误
            print(f"Error loading CP templates: {e}")
            self.templates = {}

    def sample(self, episode_node: Dict[str, Any], project_data: Any, stage="flesh") -> Dict[str, Any]:
        # 阶段守卫：非血肉阶段调用 -> 抛出 RuntimeError
        if stage not in self.STAGE_WHITELIST:
            raise RuntimeError(
                f"CP 互动模板库禁止在 {stage} 阶段调用。"
                f"仅允许在 {self.STAGE_WHITELIST} 中使用。"
            )

        if not self.templates:
            return None

        role_a = getattr(project_data, "cp_role_a", "")
        role_b = getattr(project_data, "cp_role_b", "")
        if not role_a or not role_b:
            return None

        # 1. 题库选择
        genre_key = self.GENRE_TO_CP_LIBRARY.get(project_data.story_genre)
        candidates = []

        # 核心通用库
        core_lib = self.templates.get("core_basic_library", {})
        for category, items in core_lib.items():
            if isinstance(items, list):
                candidates.extend(items)

        # 专属题库
        if genre_key:
            genre_lib = self.templates.get("genre_exclusive_library", {}).get(genre_key, [])
            if isinstance(genre_lib, list):
                candidates.extend(genre_lib)

        # 2. 过滤 Hauge 阶段
        hauge_stage_id = episode_node.get("hauge_stage_id", 1)
        valid_candidates = []
        for item in candidates:
            stages = item.get("hauge_stages", [])
            if not stages or hauge_stage_id in stages:
                valid_candidates.append(item)

        if not valid_candidates:
            return None

        # 随机抽取一个
        selected = random.choice(valid_candidates)
        
        # 占位符替换
        raw_text = selected.get("template", "")
        rendered_text = raw_text.replace("{role_a}", role_a).replace("{role_b}", role_b)
        
        # 简单替换场景（如果有 main_scene，否则用默认）
        scene = episode_node.get("main_scene", "当前场景")
        rendered_text = rendered_text.replace("{scene}", scene)

        return {
            "id": selected.get("id", "unknown"),
            "raw_template": raw_text,
            "rendered_text": rendered_text,
            "hook_type": selected.get("hook_type", "互动片段"),
            "hauge_stages": selected.get("hauge_stages", [])
        }
