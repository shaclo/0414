# ============================================================
# services/ai_providers/base_provider.py
# AI 供应商抽象基类 — 定义统一的调用接口
# ============================================================

from abc import ABC, abstractmethod
from typing import Optional


class BaseProvider(ABC):
    """
    AI 供应商抽象基类。

    所有供应商（Vertex AI、豆包、DeepSeek、OpenAI 等）必须实现此接口。
    上层调用者（ai_service.py）通过此接口统一调用，无需关心底层差异。
    """

    def __init__(self):
        self._initialized = False
        self._config: dict = {}

    @property
    @abstractmethod
    def provider_type(self) -> str:
        """供应商类型标识: 'vertex' | 'openai_compatible'"""
        ...

    @property
    def name(self) -> str:
        return self._config.get("name", "未命名")

    @property
    def current_model(self) -> str:
        return self._config.get("model", "")

    @current_model.setter
    def current_model(self, model: str):
        self._config["model"] = model

    @property
    def available_models(self) -> list:
        return self._config.get("models", [])

    @abstractmethod
    def initialize(self, config: dict):
        """
        使用配置初始化供应商客户端。

        Args:
            config: 供应商配置字典，包含鉴权信息、模型、代理等
        """
        ...

    @abstractmethod
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
        """
        调用 AI 生成文本。

        Args:
            user_prompt:       用户消息
            system_prompt:     系统指令
            temperature:       温度
            top_p:             Top-P
            top_k:             Top-K（部分供应商不支持，忽略即可）
            max_tokens:        最大生成 token 数
            response_mime_type: None=纯文本, "application/json"=JSON 模式

        Returns:
            AI 生成的文本
        """
        ...

    def supports_embedding(self) -> bool:
        """当前供应商是否支持 Embedding（有配置 embedding_model 则支持）"""
        return bool(self._config.get("embedding_model"))

    def get_embedding_dim(self) -> int:
        """Embedding 向量维度"""
        return self._config.get("embedding_dim", 768)

    def generate_embeddings(self, texts: list[str]) -> list[list[float]]:
        """
        批量生成文本向量。不支持的供应商返回空列表。

        Args:
            texts: 文本列表

        Returns:
            向量列表
        """
        return []

    @abstractmethod
    def test_connection(self) -> tuple:
        """
        测试连接是否正常。

        Returns:
            (success: bool, message: str)
        """
        ...

    def get_config(self) -> dict:
        """获取当前配置（用于持久化）"""
        return dict(self._config)
