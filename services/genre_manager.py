# ============================================================
# services/genre_manager.py
# 题材预设管理器 — 支持增删改 + JSON 文件持久化
# ============================================================

import json
import logging
import os
from typing import Dict

from env import GENRE_PRESETS

logger = logging.getLogger(__name__)

_CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config")
_GENRE_FILE = os.path.join(_CONFIG_DIR, "genre_presets.json")


class GenrePresetManager:
    """
    题材预设管理器。

    - 启动时从 config/genre_presets.json 加载
    - 若文件不存在，使用 env.py 中的 GENRE_PRESETS 默认值
    - 每次增删改自动保存
    """

    def __init__(self):
        self._presets: Dict[str, dict] = {}
        self._load()

    # ------------------------------------------------------------------ #
    # 持久化
    # ------------------------------------------------------------------ #
    def _load(self):
        if os.path.exists(_GENRE_FILE):
            try:
                with open(_GENRE_FILE, 'r', encoding='utf-8') as f:
                    self._presets = json.load(f)
                logger.info("从 %s 加载了 %d 个题材预设", _GENRE_FILE, len(self._presets))
                return
            except Exception as e:
                logger.warning("加载题材预设失败: %s, 使用默认值", e)

        # 使用默认值
        self._presets = {k: dict(v) for k, v in GENRE_PRESETS.items()}

    def _save(self):
        try:
            os.makedirs(_CONFIG_DIR, exist_ok=True)
            with open(_GENRE_FILE, 'w', encoding='utf-8') as f:
                json.dump(self._presets, f, ensure_ascii=False, indent=2)
            logger.info("题材预设已保存到 %s", _GENRE_FILE)
        except Exception as e:
            logger.error("保存题材预设失败: %s", e)

    # ------------------------------------------------------------------ #
    # 公开接口
    # ------------------------------------------------------------------ #
    def get_all(self) -> Dict[str, dict]:
        return dict(self._presets)

    def get(self, key: str) -> dict:
        return self._presets.get(key, {})

    def add(self, key: str, label: str, description: str,
            skeleton_block: str = "", variation_block: str = "", expansion_block: str = ""):
        if key in self._presets:
            raise ValueError(f"题材 key '{key}' 已存在")
        self._presets[key] = {
            "label": label,
            "description": description,
            "skeleton_block": skeleton_block,
            "variation_block": variation_block,
            "expansion_block": expansion_block,
        }
        self._save()

    def update(self, key: str, label: str, description: str,
               skeleton_block: str = "", variation_block: str = "", expansion_block: str = ""):
        if key not in self._presets:
            raise KeyError(f"题材 key '{key}' 不存在")
        self._presets[key] = {
            "label": label,
            "description": description,
            "skeleton_block": skeleton_block,
            "variation_block": variation_block,
            "expansion_block": expansion_block,
        }
        self._save()

    def remove(self, key: str):
        if key not in self._presets:
            return
        del self._presets[key]
        self._save()

    def reset_to_defaults(self):
        """恢复到 env.py 中的默认预设"""
        self._presets = {k: dict(v) for k, v in GENRE_PRESETS.items()}
        self._save()


# 全局单例
genre_manager = GenrePresetManager()
