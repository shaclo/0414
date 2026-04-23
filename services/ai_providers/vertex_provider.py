# ============================================================
# services/ai_providers/vertex_provider.py
# Vertex AI (Google Gemini) 供应商实现
# 鉴权方式：JSON 服务账号密钥文件
# ============================================================

import os
import logging
import math

from services.ai_providers.base_provider import BaseProvider

logger = logging.getLogger(__name__)


class VertexProvider(BaseProvider):
    """
    Google Vertex AI 供应商。

    使用 google-genai SDK（REST 模式）通过 VertexAI 端点调用 Gemini。
    鉴权方式：JSON 服务账号密钥文件。

    配置字段:
        project_id:      GCP 项目 ID
        location:        区域（如 us-central1）
        key_path:        JSON 密钥文件路径
        model:           模型名（如 gemini-2.5-flash）
        proxy:           代理地址（可选）
        embedding_model: Embedding 模型名（如 text-embedding-004，为空则不支持）
        embedding_dim:   Embedding 向量维度（默认 768）
    """

    def __init__(self):
        super().__init__()
        self._client = None

    @property
    def provider_type(self) -> str:
        return "vertex"

    def initialize(self, config: dict):
        if self._initialized and self._config == config:
            return
        self._config = dict(config)

        # 设置代理
        proxy = config.get("proxy", "")
        if proxy:
            os.environ["HTTP_PROXY"] = proxy
            os.environ["HTTPS_PROXY"] = proxy

        from google import genai
        from google.oauth2 import service_account

        # 加载服务账号凭证
        key_path = config.get("key_path", "")
        if not key_path or not os.path.exists(key_path):
            raise FileNotFoundError(f"Vertex AI 密钥文件不存在: {key_path}")

        credentials = service_account.Credentials.from_service_account_file(
            key_path,
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )

        # 创建 genai 客户端
        self._client = genai.Client(
            vertexai=True,
            project=config.get("project_id", ""),
            location=config.get("location", "us-central1"),
            credentials=credentials,
        )

        self._initialized = True
        logger.info(
            "VertexProvider 初始化完成: project=%s, model=%s",
            config.get("project_id"), config.get("model"),
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
            raise RuntimeError("VertexProvider 未初始化")

        from google.genai import types

        config_kwargs = dict(
            system_instruction=system_prompt,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            max_output_tokens=max_tokens,
        )
        if response_mime_type:
            config_kwargs["response_mime_type"] = response_mime_type

        config = types.GenerateContentConfig(**config_kwargs)

        response = self._client.models.generate_content(
            model=self._config.get("model", "gemini-2.5-flash"),
            contents=user_prompt,
            config=config,
        )

        result_text = response.text
        if result_text is None:
            logger.error("Vertex API returned None. Full response: %s", response)
            result_text = ""
        return result_text

    def generate_embeddings(self, texts: list[str]) -> list[list[float]]:
        if not self._initialized:
            raise RuntimeError("VertexProvider 未初始化")

        embedding_model = self._config.get("embedding_model", "")
        if not embedding_model or not texts:
            return []

        result = self._client.models.embed_content(
            model=embedding_model,
            contents=texts,
        )

        vectors = []
        for emb in result.embeddings:
            vec = emb.values
            # L2 归一化（FAISS IndexFlatIP 内积 = 余弦相似度）
            norm = math.sqrt(sum(v * v for v in vec))
            if norm > 0:
                vec = [v / norm for v in vec]
            vectors.append(vec)

        logger.info(
            "Embedding 生成完成: %d 条文本 → %d 维向量",
            len(texts), len(vectors[0]) if vectors else 0,
        )
        return vectors

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
