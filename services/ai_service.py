# ============================================================
# services/ai_service.py
# AI 调用统一入口 — Provider 策略模式
#
# 支持多供应商切换（Vertex AI / OpenAI 兼容 API）
# 上层调用者（worker.py 等）通过本模块的统一接口调用，
# 无需关心底层使用的是哪个供应商。
# ============================================================

import os
import json
import time
import random
import asyncio
import logging
from typing import Optional

from proxyserverconfig import (
    DEFAULT_TEMPERATURE, DEFAULT_TOP_P, DEFAULT_TOP_K, DEFAULT_MAX_TOKENS,
    MAX_CONCURRENT_CALLS, MIN_CALL_INTERVAL, MAX_CALL_INTERVAL,
)

logger = logging.getLogger(__name__)

# 配置文件路径
_CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config")
PROVIDER_CONFIG_PATH = os.path.join(_CONFIG_DIR, "provider_config.json")


class AIService:
    """
    AI 调用的统一入口（Provider 策略模式）。

    功能：
    - 多供应商管理（添加/删除/切换）
    - 同步调用 (generate / generate_json)
    - 异步并行调用 (parallel_generate) — 支持多供应商随机分配
    - QPS 速率限制 (信号量 + 随机间隔)
    - Embedding 生成（委托给当前 Provider，不支持则返回空）
    """

    def __init__(self):
        self._providers: dict = {}       # provider_id → BaseProvider 实例
        self._active_id: str = ""        # 当前活跃的供应商 ID
        self._config_data: dict = {}     # 完整配置数据
        self._initialized = False
        self._last_call_time = 0.0
        self._semaphore = None

    # ------------------------------------------------------------------ #
    # 初始化 & 配置
    # ------------------------------------------------------------------ #
    def initialize(self):
        """加载供应商配置（不初始化 Provider，Provider 在首次 AI 调用时懒加载）"""
        if self._initialized:
            return
        self._load_config()
        self._initialized = True

    def _load_config(self):
        """从 config/provider_config.json 加载配置"""
        os.makedirs(_CONFIG_DIR, exist_ok=True)

        if os.path.exists(PROVIDER_CONFIG_PATH):
            with open(PROVIDER_CONFIG_PATH, "r", encoding="utf-8") as f:
                self._config_data = json.load(f)
        else:
            # 首次启动：从 proxyserverconfig.py 迁移
            self._config_data = self._migrate_from_legacy()
            self._save_config()

        self._active_id = self._config_data.get("active_provider", "")
        providers_cfg = self._config_data.get("providers", {})

        if not self._active_id and providers_cfg:
            self._active_id = next(iter(providers_cfg))

        logger.info("加载供应商配置: %d 个供应商, 活跃: %s",
                     len(providers_cfg), self._active_id)

    def _migrate_from_legacy(self) -> dict:
        """从旧版 proxyserverconfig.py 迁移为新配置格式"""
        from proxyserverconfig import (
            PROXY_URL, VERTEX_PROJECT_ID, VERTEX_LOCATION,
            VERTEX_KEY_PATH, VERTEX_MODEL,
        )
        return {
            "active_provider": "vertex_default",
            "providers": {
                "vertex_default": {
                    "type": "vertex",
                    "name": "Vertex AI (默认)",
                    "project_id": VERTEX_PROJECT_ID,
                    "location": VERTEX_LOCATION,
                    "key_path": VERTEX_KEY_PATH,
                    "model": VERTEX_MODEL,
                    "proxy": PROXY_URL,
                    "models": ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"],
                    "embedding_model": "text-embedding-004",
                    "embedding_dim": 768,
                }
            }
        }

    def _save_config(self):
        """保存配置到 JSON 文件"""
        os.makedirs(_CONFIG_DIR, exist_ok=True)
        # 同步供应商实例的配置回 config_data
        for pid, provider in self._providers.items():
            if pid in self._config_data.get("providers", {}):
                self._config_data["providers"][pid] = provider.get_config()
        self._config_data["active_provider"] = self._active_id
        with open(PROVIDER_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(self._config_data, f, ensure_ascii=False, indent=2)

    def _init_provider(self, provider_id: str):
        """初始化指定的供应商实例"""
        if provider_id in self._providers:
            return self._providers[provider_id]

        providers_cfg = self._config_data.get("providers", {})
        cfg = providers_cfg.get(provider_id)
        if not cfg:
            raise ValueError(f"供应商 '{provider_id}' 不存在")

        provider_type = cfg.get("type", "")
        if provider_type == "vertex":
            from services.ai_providers.vertex_provider import VertexProvider
            provider = VertexProvider()
        elif provider_type == "openai_compatible":
            from services.ai_providers.openai_provider import OpenAICompatibleProvider
            provider = OpenAICompatibleProvider()
        else:
            raise ValueError(f"不支持的供应商类型: {provider_type}")

        provider.initialize(cfg)
        self._providers[provider_id] = provider
        return provider

    def _get_active_provider(self):
        """获取当前活跃的 Provider 实例"""
        if self._active_id not in self._providers:
            self._init_provider(self._active_id)
        return self._providers[self._active_id]

    def _get_provider(self, provider_id: str):
        """获取指定 Provider 实例（用于并行调用多供应商）"""
        if provider_id not in self._providers:
            self._init_provider(provider_id)
        return self._providers[provider_id]

    # ------------------------------------------------------------------ #
    # 供应商管理（供 UI 调用）
    # ------------------------------------------------------------------ #
    def get_all_providers(self) -> dict:
        """获取所有供应商配置: {id: config_dict}"""
        return dict(self._config_data.get("providers", {}))

    def get_active_provider_id(self) -> str:
        return self._active_id

    def get_active_provider_name(self) -> str:
        cfg = self._config_data.get("providers", {}).get(self._active_id, {})
        return cfg.get("name", self._active_id)

    def get_current_model(self) -> str:
        cfg = self._config_data.get("providers", {}).get(self._active_id, {})
        return cfg.get("model", "")

    def switch_provider(self, provider_id: str):
        """切换活跃供应商"""
        if provider_id not in self._config_data.get("providers", {}):
            raise ValueError(f"供应商 '{provider_id}' 不存在")
        self._active_id = provider_id
        self._init_provider(provider_id)
        self._save_config()
        logger.info("切换供应商: %s", provider_id)

    def switch_model(self, model_name: str):
        """切换当前供应商的模型"""
        provider = self._get_active_provider()
        provider.current_model = model_name
        self._config_data["providers"][self._active_id]["model"] = model_name
        self._save_config()
        logger.info("切换模型: %s → %s", self._active_id, model_name)

    def add_provider(self, provider_id: str, config: dict):
        """添加新供应商"""
        if "providers" not in self._config_data:
            self._config_data["providers"] = {}
        self._config_data["providers"][provider_id] = config
        # 清除已缓存的旧实例
        self._providers.pop(provider_id, None)
        self._save_config()
        logger.info("添加供应商: %s (%s)", provider_id, config.get("name"))

    def update_provider(self, provider_id: str, config: dict):
        """更新供应商配置"""
        if provider_id not in self._config_data.get("providers", {}):
            raise ValueError(f"供应商 '{provider_id}' 不存在")
        self._config_data["providers"][provider_id] = config
        # 清除已缓存的旧实例，下次调用时重新初始化
        self._providers.pop(provider_id, None)
        self._save_config()

    def remove_provider(self, provider_id: str):
        """删除供应商"""
        self._config_data.get("providers", {}).pop(provider_id, None)
        self._providers.pop(provider_id, None)
        if self._active_id == provider_id:
            remaining = list(self._config_data.get("providers", {}).keys())
            self._active_id = remaining[0] if remaining else ""
        self._save_config()

    def test_provider(self, provider_id: str, config: dict = None) -> tuple:
        """
        测试指定供应商的连接。

        Args:
            provider_id: 供应商 ID
            config: 可选的配置字典。如果传入则用此配置测试（不影响已保存的配置）；
                    如果不传则从已保存的配置中读取。
        """
        cfg = config or self._config_data.get("providers", {}).get(provider_id)
        if not cfg:
            return False, f"供应商 '{provider_id}' 不存在"
        provider_type = cfg.get("type", "")
        if provider_type == "vertex":
            from services.ai_providers.vertex_provider import VertexProvider
            p = VertexProvider()
        elif provider_type == "openai_compatible":
            from services.ai_providers.openai_provider import OpenAICompatibleProvider
            p = OpenAICompatibleProvider()
        else:
            return False, f"不支持的供应商类型: {provider_type}"
        try:
            p.initialize(cfg)
        except Exception as e:
            return False, f"初始化失败: {str(e)}"
        return p.test_connection()

    # ------------------------------------------------------------------ #
    # Embedding 支持查询
    # ------------------------------------------------------------------ #
    def supports_embedding(self) -> bool:
        """当前活跃供应商是否支持 Embedding"""
        self.initialize()
        return self._get_active_provider().supports_embedding()

    def get_embedding_dim(self) -> int:
        """当前活跃供应商的 Embedding 维度"""
        self.initialize()
        return self._get_active_provider().get_embedding_dim()

    # ------------------------------------------------------------------ #
    # 生成调用（对外接口不变）
    # ------------------------------------------------------------------ #
    def generate(
        self,
        user_prompt: str,
        system_prompt: str,
        temperature: float = DEFAULT_TEMPERATURE,
        top_p: float = DEFAULT_TOP_P,
        top_k: int = DEFAULT_TOP_K,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        response_mime_type: str = None,
    ) -> str:
        """同步调用 AI 生成文本（委托给当前活跃 Provider）"""
        self.initialize()
        provider = self._get_active_provider()

        logger.info("AI 调用开始: provider=%s, model=%s, temp=%.2f, prompt_len=%d",
                     self._active_id, provider.current_model, temperature, len(user_prompt))

        result = provider.generate(
            user_prompt, system_prompt, temperature, top_p, top_k, max_tokens,
            response_mime_type=response_mime_type,
        )

        logger.info("AI 调用完成: response_len=%d", len(result))
        return result

    def generate_json(
        self,
        user_prompt: str,
        system_prompt: str,
        temperature: float = DEFAULT_TEMPERATURE,
        top_p: float = DEFAULT_TOP_P,
        top_k: int = DEFAULT_TOP_K,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> dict:
        """调用 AI 并解析 JSON 响应"""
        raw = self.generate(
            user_prompt, system_prompt, temperature, top_p, top_k, max_tokens,
            response_mime_type="application/json",
        )

        # 清理可能的 markdown 包裹
        cleaned = raw.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        if cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.warning("JSON 解析失败，尝试修复截断的 JSON: %s", str(e))
            repaired = self._repair_truncated_json(cleaned)
            try:
                return json.loads(repaired)
            except json.JSONDecodeError:
                logger.error("JSON 修复失败，原始内容末尾: ...%s", cleaned[-200:])
                raise

    @staticmethod
    def _repair_truncated_json(text: str) -> str:
        """
        尝试修复被截断的 JSON。
        当 AI 生成的内容超过 max_tokens 时，JSON 可能在中间被切断。
        策略：关闭所有未闭合的字符串、数组和对象。
        """
        # 1. 如果在字符串中间被截断，先闭合字符串
        in_string = False
        escape = False
        for ch in text:
            if escape:
                escape = False
                continue
            if ch == '\\':
                escape = True
                continue
            if ch == '"':
                in_string = not in_string

        if in_string:
            text += '"'

        # 2. 统计未闭合的括号
        stack = []
        in_str = False
        esc = False
        for ch in text:
            if esc:
                esc = False
                continue
            if ch == '\\':
                esc = True
                continue
            if ch == '"':
                in_str = not in_str
                continue
            if in_str:
                continue
            if ch in ('{', '['):
                stack.append(ch)
            elif ch == '}' and stack and stack[-1] == '{':
                stack.pop()
            elif ch == ']' and stack and stack[-1] == '[':
                stack.pop()

        # 3. 检查末尾是否需要补逗号后的值
        stripped = text.rstrip()
        if stripped.endswith(','):
            text = stripped[:-1]
        elif stripped.endswith(':'):
            text = stripped + ' null'

        # 4. 按相反顺序闭合括号
        for bracket in reversed(stack):
            if bracket == '{':
                t = text.rstrip()
                if t.endswith(','):
                    text = t[:-1]
                text += '}'
            elif bracket == '[':
                t = text.rstrip()
                if t.endswith(','):
                    text = t[:-1]
                text += ']'

        logger.info("JSON 修复完成，修复了 %d 个未闭合括号", len(stack))
        return text

    # ------------------------------------------------------------------ #
    # 异步并行调用（支持多供应商随机分配）
    # ------------------------------------------------------------------ #
    async def _rate_limited_generate(
        self,
        user_prompt: str,
        system_prompt: str,
        temperature: float,
        top_p: float,
        top_k: int,
        max_tokens: int,
        response_mime_type: str = None,
        provider_id: str = None,
    ) -> str:
        """带速率限制的异步单次调用"""
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(MAX_CONCURRENT_CALLS)

        async with self._semaphore:
            wait_time = random.uniform(MIN_CALL_INTERVAL, MAX_CALL_INTERVAL)
            elapsed = time.time() - self._last_call_time
            if elapsed < wait_time:
                await asyncio.sleep(wait_time - elapsed)

            self._last_call_time = time.time()

            # 使用指定的 Provider 或当前活跃的
            provider = self._get_provider(provider_id) if provider_id else self._get_active_provider()

            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: provider.generate(
                    user_prompt, system_prompt, temperature, top_p, top_k, max_tokens,
                    response_mime_type=response_mime_type,
                ),
            )
            return result

    async def parallel_generate(
        self,
        calls: list,
        provider_pool: list = None,
    ) -> list:
        """
        并行调用多个 AI 请求（受 QPS 限制）。

        Args:
            calls: 调用参数列表
            provider_pool: 可选的供应商 ID 列表。
                           如果传入多个，每次调用随机选一个。
                           如果不传，使用当前全局活跃供应商。

        Returns:
            结果列表: [{"persona_key": str, "result": str|None, "error": str|None}]
        """
        self.initialize()

        # 预初始化所有 pool 中的供应商
        if provider_pool:
            for pid in provider_pool:
                self._init_provider(pid)

        async def _single_call(call_params):
            persona_key = call_params.get("persona_key", "unknown")

            # 多供应商随机分配
            if provider_pool and len(provider_pool) > 0:
                pid = random.choice(provider_pool)
            else:
                pid = self._active_id

            try:
                result_text = await self._rate_limited_generate(
                    user_prompt=call_params["user_prompt"],
                    system_prompt=call_params["system_prompt"],
                    temperature=call_params.get("temperature", DEFAULT_TEMPERATURE),
                    top_p=call_params.get("top_p", DEFAULT_TOP_P),
                    top_k=call_params.get("top_k", DEFAULT_TOP_K),
                    max_tokens=call_params.get("max_tokens", DEFAULT_MAX_TOKENS),
                    response_mime_type=call_params.get("response_mime_type", "application/json"),
                    provider_id=pid,
                )
                return {"persona_key": persona_key, "result": result_text, "error": None,
                        "provider_id": pid}
            except Exception as e:
                logger.error("人格 %s (供应商 %s) 调用失败: %s", persona_key, pid, str(e))
                return {"persona_key": persona_key, "result": None, "error": str(e),
                        "provider_id": pid}

        tasks = [_single_call(c) for c in calls]
        results = await asyncio.gather(*tasks)
        return list(results)

    # ------------------------------------------------------------------ #
    # Embedding 生成（委托给当前 Provider）
    # ------------------------------------------------------------------ #
    def generate_embeddings(self, texts: list[str]) -> list[list[float]]:
        """批量生成文本向量。不支持时返回空列表。"""
        self.initialize()
        provider = self._get_active_provider()
        if not provider.supports_embedding():
            logger.warning("当前供应商 %s 不支持 Embedding，跳过", self._active_id)
            return []
        return provider.generate_embeddings(texts)

    # ------------------------------------------------------------------ #
    # 向后兼容：EMBEDDING_DIM 类属性
    # ------------------------------------------------------------------ #
    @property
    def EMBEDDING_DIM(self):
        """向后兼容：rag_controller.py 引用了 AIService.EMBEDDING_DIM"""
        try:
            return self.get_embedding_dim()
        except Exception:
            return 768


# 全局单例
ai_service = AIService()
