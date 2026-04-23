# ============================================================
# services/ai_providers/openai_provider.py
# OpenAI 兼容 API 供应商实现（适用于豆包、DeepSeek、OpenAI、Moonshot 等）
# 鉴权方式：API Key + Base URL
# ============================================================

import os
import json
import logging
import math
from typing import Optional

from services.ai_providers.base_provider import BaseProvider

logger = logging.getLogger(__name__)


class OpenAICompatibleProvider(BaseProvider):
    """
    OpenAI 兼容 API 供应商。

    适用于所有兼容 OpenAI Chat Completions API 的服务：
    - 豆包 (Doubao)
    - DeepSeek
    - OpenAI
    - Moonshot (Kimi)
    - 智谱 (GLM)
    - 其他兼容服务

    鉴权方式：API Key + 自定义 Base URL。

    配置字段:
        api_key:         API 密钥
        base_url:        API 端点 URL（如 https://ark.cn-beijing.volces.com/api/v3）
        model:           模型名（如 doubao-pro-32k）
        proxy:           代理地址（可选）
        embedding_model: Embedding 模型名（为空则不支持）
        embedding_dim:   Embedding 向量维度
    """

    def __init__(self):
        super().__init__()
        self._client = None

    @property
    def provider_type(self) -> str:
        return "openai_compatible"

    def initialize(self, config: dict):
        if self._initialized and self._config == config:
            return
        self._config = dict(config)

        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError(
                "需要安装 openai 库。请运行: pip install openai"
            )

        # 代理设置
        proxy = config.get("proxy", "")
        http_client = None
        if proxy:
            try:
                import httpx
                http_client = httpx.Client(proxy=proxy)
            except ImportError:
                # 回退到环境变量
                os.environ["HTTP_PROXY"] = proxy
                os.environ["HTTPS_PROXY"] = proxy

        client_kwargs = {
            "api_key": config.get("api_key", ""),
            "base_url": config.get("base_url", ""),
        }
        if http_client:
            client_kwargs["http_client"] = http_client

        self._client = OpenAI(**client_kwargs)
        self._initialized = True
        logger.info(
            "OpenAICompatibleProvider 初始化完成: base_url=%s, model=%s",
            config.get("base_url"), config.get("model"),
        )

    def generate(
        self,
        user_prompt: str,
        system_prompt: str,
        temperature: float = 0.7,
        top_p: float = 0.9,
        top_k: int = 40,
        max_tokens: int = 16384,
        response_mime_type: str = None,
    ) -> str:
        if not self._initialized:
            raise RuntimeError("OpenAICompatibleProvider 未初始化")

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        kwargs = {
            "model": self._config.get("model", ""),
            "messages": messages,
            "temperature": temperature,
            "top_p": top_p,
            "max_tokens": max_tokens,
        }

        # JSON 模式（如果供应商支持）
        if response_mime_type == "application/json":
            kwargs["response_format"] = {"type": "json_object"}

        try:
            response = self._client.chat.completions.create(**kwargs)
            result_text = response.choices[0].message.content
            if result_text is None:
                logger.error("OpenAI API returned None content.")
                result_text = ""
            return result_text
        except Exception as e:
            # 如果 JSON 模式不支持，回退到普通模式并在 prompt 中要求 JSON
            if response_mime_type == "application/json" and "response_format" in str(e):
                logger.warning("供应商不支持 response_format，回退到 prompt 要求 JSON")
                del kwargs["response_format"]
                kwargs["messages"][0]["content"] += "\n\n请严格以 JSON 格式返回结果，不要包含任何非 JSON 内容。"
                response = self._client.chat.completions.create(**kwargs)
                return response.choices[0].message.content or ""
            raise

    def generate_embeddings(self, texts: list[str]) -> list[list[float]]:
        if not self._initialized:
            raise RuntimeError("OpenAICompatibleProvider 未初始化")

        embedding_model = self._config.get("embedding_model", "")
        if not embedding_model or not texts:
            return []

        try:
            response = self._client.embeddings.create(
                model=embedding_model,
                input=texts,
            )

            vectors = []
            for item in response.data:
                vec = item.embedding
                # L2 归一化
                norm = math.sqrt(sum(v * v for v in vec))
                if norm > 0:
                    vec = [v / norm for v in vec]
                vectors.append(vec)

            logger.info(
                "Embedding 生成完成: %d 条文本 → %d 维向量",
                len(texts), len(vectors[0]) if vectors else 0,
            )
            return vectors
        except Exception as e:
            logger.error("Embedding 生成失败: %s", str(e))
            return []

    def test_connection(self) -> tuple:
        try:
            self.initialize(self._config)
            result = self.generate(
                user_prompt="Reply with exactly: CONNECTION_OK",
                system_prompt="You are a test assistant. Reply exactly as instructed.",
                temperature=0.0,
                max_tokens=20,
            )
            if result and len(result.strip()) > 0:
                return True, f"连接成功 ✅ 模型: {self._config.get('model')}，返回: {result.strip()[:50]}"
            return False, "连接成功但返回为空"
        except Exception as e:
            return False, f"连接失败: {str(e)}"
