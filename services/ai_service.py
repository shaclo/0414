# ============================================================
# services/ai_service.py
# Gemini AI 调用封装 (使用 google-genai SDK，REST 模式)
# 职责：凭证初始化、代理设置、QPS 控制、生成调用
#
# 注意：由于 ARM64 Windows 不支持 grpcio 预编译轮子，
# 本模块使用 google-genai SDK (REST) 替代 vertexai SDK (gRPC)。
# 调用效果完全一致，仅底层传输协议不同。
# ============================================================

import os
import json
import time
import random
import asyncio
import logging
from typing import Optional

from google import genai
from google.genai import types
from google.oauth2 import service_account

from proxyserverconfig import (
    PROXY_URL, VERTEX_PROJECT_ID, VERTEX_LOCATION,
    VERTEX_KEY_PATH, VERTEX_MODEL,
    DEFAULT_TEMPERATURE, DEFAULT_TOP_P, DEFAULT_TOP_K, DEFAULT_MAX_TOKENS,
    MAX_CONCURRENT_CALLS, MIN_CALL_INTERVAL, MAX_CALL_INTERVAL,
)

logger = logging.getLogger(__name__)


class AIService:
    """
    Gemini AI 调用的统一入口。

    功能：
    - 凭证初始化与代理设置
    - 同步调用 (generate)
    - 异步并行调用 (parallel_generate) — 用于盲视变异阶段
    - QPS 速率限制 (信号量 + 随机 3-15 秒间隔)

    使用 google-genai SDK 通过 VertexAI 端点调用 Gemini，
    底层使用 REST（而非 gRPC），兼容 ARM64 Windows。
    """

    def __init__(self):
        self._client = None
        self._initialized = False
        self._last_call_time = 0.0
        self._semaphore = None

    def initialize(self):
        """
        初始化 Gemini 客户端。
        设置代理 → 加载服务账号凭证 → 创建 genai Client。
        """
        if self._initialized:
            return

        # 设置代理
        os.environ["HTTP_PROXY"] = PROXY_URL
        os.environ["HTTPS_PROXY"] = PROXY_URL

        # 加载服务账号凭证
        credentials = service_account.Credentials.from_service_account_file(
            VERTEX_KEY_PATH,
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )

        # 创建 genai 客户端（通过 VertexAI 端点）
        self._client = genai.Client(
            vertexai=True,
            project=VERTEX_PROJECT_ID,
            location=VERTEX_LOCATION,
            credentials=credentials,
        )

        self._initialized = True
        logger.info("AIService 初始化完成 (google-genai REST): project=%s, model=%s",
                    VERTEX_PROJECT_ID, VERTEX_MODEL)

    def generate(
        self,
        user_prompt: str,
        system_prompt: str,
        temperature: float = DEFAULT_TEMPERATURE,
        top_p: float = DEFAULT_TOP_P,
        top_k: int = DEFAULT_TOP_K,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> str:
        """
        同步调用 Gemini API。

        Args:
            user_prompt: 用户消息内容
            system_prompt: 系统指令
            temperature: 温度值
            top_p: Top-P 值
            top_k: Top-K 值
            max_tokens: 最大生成 token 数

        Returns:
            AI 生成的文本内容
        """
        self.initialize()

        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            max_output_tokens=max_tokens,
            response_mime_type="application/json",
        )

        logger.info("AI 调用开始: temperature=%.2f, prompt_len=%d", temperature, len(user_prompt))

        response = self._client.models.generate_content(
            model=VERTEX_MODEL,
            contents=user_prompt,
            config=config,
        )

        result_text = response.text
        if result_text is None:
            logger.error("API returned None text. Full response: %s", response)
            result_text = ""
        logger.info("AI 调用完成: response_len=%d", len(result_text))
        return result_text

    def generate_json(
        self,
        user_prompt: str,
        system_prompt: str,
        temperature: float = DEFAULT_TEMPERATURE,
        top_p: float = DEFAULT_TOP_P,
        top_k: int = DEFAULT_TOP_K,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> dict:
        """
        调用 Gemini 并解析 JSON 响应。

        Returns:
            解析后的 dict

        Raises:
            json.JSONDecodeError: JSON 解析失败
        """
        raw = self.generate(user_prompt, system_prompt, temperature, top_p, top_k, max_tokens)

        # 清理可能的 markdown 包裹
        cleaned = raw.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        if cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        return json.loads(cleaned)

    async def _rate_limited_generate(
        self,
        user_prompt: str,
        system_prompt: str,
        temperature: float,
        top_p: float,
        top_k: int,
        max_tokens: int,
    ) -> str:
        """
        带速率限制的异步单次调用。
        用于盲视变异阶段的并行调用。

        速率控制：
        - 信号量限制最大并发数 (MAX_CONCURRENT_CALLS = 3)
        - 每次调用前随机等待 3~15 秒
        """
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(MAX_CONCURRENT_CALLS)

        async with self._semaphore:
            # 随机间隔等待
            wait_time = random.uniform(MIN_CALL_INTERVAL, MAX_CALL_INTERVAL)
            elapsed = time.time() - self._last_call_time
            if elapsed < wait_time:
                await asyncio.sleep(wait_time - elapsed)

            self._last_call_time = time.time()

            # 在线程池中执行同步调用（google-genai 的同步 API）
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                self.generate,
                user_prompt, system_prompt, temperature, top_p, top_k, max_tokens,
            )
            return result

    async def parallel_generate(
        self,
        calls: list,
    ) -> list:
        """
        并行调用多个 AI 请求（受 QPS 限制：最大并发3，随机间隔3-15秒）。

        Args:
            calls: 调用参数列表，每个元素是 dict:
                {
                    "user_prompt": str,
                    "system_prompt": str,
                    "temperature": float,
                    "top_p": float,
                    "top_k": int,
                    "max_tokens": int,
                    "persona_key": str,  # 用于标识结果
                }

        Returns:
            结果列表: [{"persona_key": str, "result": str|None, "error": str|None}]
        """
        self.initialize()

        async def _single_call(call_params):
            persona_key = call_params.get("persona_key", "unknown")
            try:
                result_text = await self._rate_limited_generate(
                    user_prompt=call_params["user_prompt"],
                    system_prompt=call_params["system_prompt"],
                    temperature=call_params.get("temperature", DEFAULT_TEMPERATURE),
                    top_p=call_params.get("top_p", DEFAULT_TOP_P),
                    top_k=call_params.get("top_k", DEFAULT_TOP_K),
                    max_tokens=call_params.get("max_tokens", DEFAULT_MAX_TOKENS),
                )
                return {"persona_key": persona_key, "result": result_text, "error": None}
            except Exception as e:
                logger.error("人格 %s 调用失败: %s", persona_key, str(e))
                return {"persona_key": persona_key, "result": None, "error": str(e)}

        tasks = [_single_call(c) for c in calls]
        results = await asyncio.gather(*tasks)
        return list(results)

    # ------------------------------------------------------------------ #
    # Embedding 生成（用于 RAG 向量检索）
    # ------------------------------------------------------------------ #
    EMBEDDING_MODEL = "text-embedding-004"   # 768 维，支持中文
    EMBEDDING_DIM = 768

    def generate_embeddings(self, texts: list[str]) -> list[list[float]]:
        """
        批量生成文本向量。

        使用 Gemini text-embedding-004 模型。
        返回归一化后的 float 列表（可直接用于 FAISS IndexFlatIP 做余弦相似度）。

        Args:
            texts: 文本列表（单次最多 100 条）

        Returns:
            向量列表，每个向量 768 维
        """
        self.initialize()

        if not texts:
            return []

        # google-genai SDK 的 embed_content API
        result = self._client.models.embed_content(
            model=self.EMBEDDING_MODEL,
            contents=texts,
        )

        vectors = []
        for emb in result.embeddings:
            vec = emb.values
            # L2 归一化（FAISS IndexFlatIP 内积 = 余弦相似度）
            import math
            norm = math.sqrt(sum(v * v for v in vec))
            if norm > 0:
                vec = [v / norm for v in vec]
            vectors.append(vec)

        logger.info("Embedding 生成完成: %d 条文本 → %d 维向量", len(texts), len(vectors[0]) if vectors else 0)
        return vectors


# 全局单例
ai_service = AIService()
