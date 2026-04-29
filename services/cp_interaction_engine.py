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

    @staticmethod
    def _parse_adapt_tags(adapt_tags: list) -> dict:
        """
        解析 adapt_tags 列表为字典。
        例：["hook_type：动机钩", "hauge_phase：1"] → {"hook_type": "动机钩", "hauge_phase": 1}
        分隔符支持全角冒号"："和半角冒号":"。
        """
        result = {}
        for tag in (adapt_tags or []):
            if not isinstance(tag, str):
                continue
            for sep in ("：", ":"):
                if sep in tag:
                    k, _, v = tag.partition(sep)
                    k = k.strip()
                    v = v.strip()
                    if k == "hauge_phase":
                        try:
                            result[k] = int(v)
                        except ValueError:
                            result[k] = v
                    else:
                        result[k] = v
                    break
        return result

    @staticmethod
    def _extract_templates_from_lib(lib_dict: dict) -> list:
        """
        从结构为 {category: {"description": ..., "templates": [...]}} 的库中
        提取所有模板列表（同时兼容 {category: [...]} 的旧式平铺结构）。
        """
        result = []
        for _cat, val in lib_dict.items():
            if isinstance(val, list):
                result.extend(val)
            elif isinstance(val, dict):
                result.extend(val.get("templates", []))
        return result

    def sample(self, episode_node: Dict[str, Any], project_data: Any, stage="flesh") -> Dict[str, Any]:
        # 阶段守卫：非血肉阶段调用 -> 抛出 RuntimeError
        if stage not in self.STAGE_WHITELIST:
            raise RuntimeError(
                f"CP 互动模板库禁止在 {stage} 阶段调用。"
                f"仅允许在 {self.STAGE_WHITELIST} 中使用。"
            )

        if not self.templates:
            return None

        role_a = getattr(project_data, "cp_role_a", "") or ""
        role_b = getattr(project_data, "cp_role_b", "") or ""
        # 若 project_data 中未显式设置，从角色表的 cp_role 字段派生
        if not role_a or not role_b:
            for c in (getattr(project_data, "characters", None) or []):
                cp_role = c.get("cp_role", "") if isinstance(c, dict) else getattr(c, "cp_role", "")
                name = c.get("name", "") if isinstance(c, dict) else getattr(c, "name", "")
                if cp_role == "A" and not role_a:
                    role_a = name
                elif cp_role == "B" and not role_b:
                    role_b = name
        if not role_a or not role_b:
            return None

        # 1. 题库选择（正确处理嵌套结构）
        genre_key = self.GENRE_TO_CP_LIBRARY.get(getattr(project_data, "story_genre", "custom"))
        candidates = []

        core_lib = self.templates.get("core_basic_library", {})
        candidates.extend(self._extract_templates_from_lib(core_lib))

        if genre_key:
            genre_section = self.templates.get("genre_exclusive_library", {}).get(genre_key, {})
            if isinstance(genre_section, dict):
                candidates.extend(genre_section.get("templates", []))
            elif isinstance(genre_section, list):
                candidates.extend(genre_section)

        # 2. 过滤 Hauge 阶段（从 adapt_tags 中解析 hauge_phase）
        hauge_stage_id = episode_node.get("hauge_stage_id", 1)
        valid_candidates = []
        for item in candidates:
            tags = self._parse_adapt_tags(item.get("adapt_tags", []))
            phase = tags.get("hauge_phase")
            if phase is None or phase == hauge_stage_id:
                valid_candidates.append((item, tags))

        if not valid_candidates:
            # 降级：忽略阶段过滤，从全库抽取
            valid_candidates = [(item, self._parse_adapt_tags(item.get("adapt_tags", [])))
                                for item in candidates]
        if not valid_candidates:
            return None

        # 随机抽取一个
        selected, selected_tags = random.choice(valid_candidates)

        # 占位符替换（JSON 字段名为 "content"，非 "template"）
        raw_text = selected.get("content", selected.get("template", ""))
        scene = episode_node.get("main_scene", "当前场景")
        rendered_text = (
            raw_text
            .replace("{role_a}", role_a)
            .replace("{role_b}", role_b)
            .replace("{scene}", scene)
        )

        hook_type = selected_tags.get("hook_type", "互动片段")
        hauge_phase = selected_tags.get("hauge_phase")

        return {
            "id": selected.get("id", "unknown"),
            "raw_template": raw_text,
            "rendered_text": rendered_text,
            "hook_type": hook_type,
            "hauge_stages": [hauge_phase] if hauge_phase is not None else [],
        }
