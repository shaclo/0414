# ============================================================
# services/rag_controller.py
# RAG (检索增强生成) 一致性监控器
# 
# V2: 使用 FAISS 做本地向量检索 + Gemini Embedding API 生成向量
#      → 余弦相似度在本地用 FAISS IndexFlatIP 计算
#      → 只将检索到的相关片段（Top-K）发送给 AI 审查
#      → 不再把全量 Beat 塞进 prompt
# ============================================================

import json
import logging
import numpy as np
from typing import List, Optional, Dict

import faiss

from env import (
    SYSTEM_PROMPT_RAG_CHECK,
    USER_PROMPT_RAG_CHECK,
    SUGGESTED_TEMPERATURES,
)
from services.ai_service import ai_service, AIService

logger = logging.getLogger(__name__)

# FAISS 索引维度（与 Gemini text-embedding-004 一致）
EMBEDDING_DIM = AIService.EMBEDDING_DIM    # 768


class RAGController:
    """
    RAG 一致性监控器（NarrativeLoom 论文中的 Plot Controller）。

    架构（V2 - FAISS）：
    ┌───────────────┐     ┌──────────────────┐     ┌───────────────┐
    │ 世界观变量/Beat │ ──→ │ Gemini Embedding │ ──→ │ FAISS Index   │
    │   (文本)       │     │  text-embedding  │     │ (余弦相似度)   │
    └───────────────┘     │   -004 (768维)   │     │ 本地计算       │
                          └──────────────────┘     └──────┬────────┘
                                                          │ Top-K
                                                          ▼
                                                   ┌──────────────┐
                                                   │ AI-Call-6    │
                                                   │ 矛盾检测     │
                                                   │ (只传相关片段)│
                                                   └──────────────┘
    职责：
    1. 将世界观变量/已确认 Beat 文本 → Gemini Embedding → FAISS 索引
    2. 新 Beat → Embedding → FAISS 检索 Top-K 相关文档
    3. 只用 Top-K 相关文档（而非全量）调用 AI-Call-6 做矛盾检测
    4. 返回矛盾报告
    """

    # 检索返回前 K 个最相关文档
    TOP_K = 8

    def __init__(self):
        self._index: Optional[faiss.IndexFlatIP] = None
        self._doc_store: List[Dict] = []   # [{id, text, type, metadata}]
        self._initialized = False

    def _ensure_initialized(self):
        """懒初始化 FAISS 索引"""
        if self._initialized:
            return
        # IndexFlatIP = 内积（配合归一化向量 = 余弦相似度）
        self._index = faiss.IndexFlatIP(EMBEDDING_DIM)
        self._doc_store = []
        self._initialized = True
        logger.info("FAISS 索引初始化完成: dim=%d, metric=余弦相似度(内积)", EMBEDDING_DIM)

    # ================================================================== #
    # 索引 — 写入向量数据库
    # ================================================================== #

    def index_world_variables(self, variables: List[dict]):
        """
        将世界观变量存入向量索引。
        每个变量 → 一个文本文档 → 一个 embedding → FAISS 索引。
        """
        self._ensure_initialized()
        if not variables:
            return

        documents = []
        ids = []
        for var in variables:
            doc_text = (
                f"[世界观: {var.get('category', '')}] "
                f"{var.get('name', '')}: {var.get('definition', '')}。"
                f"限制: {var.get('constraints', '')}"
            )
            doc_id = var.get("id", f"wv_{len(self._doc_store)}")
            documents.append(doc_text)
            ids.append(doc_id)

        try:
            embeddings = ai_service.generate_embeddings(documents)
            self._add_to_index(documents, ids, embeddings, doc_type="world_variable")
            logger.info("已索引 %d 条世界观变量到 FAISS", len(documents))
        except Exception as e:
            logger.error("世界观变量索引失败: %s", e)

    def index_beat(self, node_id: str, beat: dict):
        """
        将已确认的 Beat 存入向量索引。
        """
        self._ensure_initialized()
        if not beat:
            return

        events_text = " → ".join(
            f"{e.get('action', '')}({e.get('causal_impact', '')})"
            for e in beat.get("causal_events", [])
        )
        doc_text = (
            f"[Beat {node_id}] "
            f"环境: {beat.get('setting', '')}。"
            f"角色: {', '.join(beat.get('entities', []))}。"
            f"事件链: {events_text}。"
            f"悬念: {beat.get('hook', '')}"
        )

        try:
            embeddings = ai_service.generate_embeddings([doc_text])
            self._add_to_index([doc_text], [f"beat_{node_id}"], embeddings, doc_type="confirmed_beat")
            logger.info("已索引 Beat %s 到 FAISS", node_id)
        except Exception as e:
            logger.error("Beat %s 索引失败: %s", node_id, e)

    def _add_to_index(self, documents: List[str], ids: List[str],
                      embeddings: List[List[float]], doc_type: str):
        """将文档和向量写入 FAISS 索引 + 文档存储"""
        if not embeddings:
            return

        # 去重：如果 id 已存在，先标记旧的为 deleted（FAISS 不支持原地更新）
        existing_ids = {d["id"] for d in self._doc_store}
        for doc_id in ids:
            if doc_id in existing_ids:
                # 标记旧记录为已删除（FAISS 无法删除，但检索时过滤）
                for d in self._doc_store:
                    if d["id"] == doc_id:
                        d["deleted"] = True
                        break

        # 写入 FAISS
        vectors = np.array(embeddings, dtype=np.float32)
        self._index.add(vectors)

        # 写入文档存储
        for i, (doc_text, doc_id) in enumerate(zip(documents, ids)):
            self._doc_store.append({
                "id": doc_id,
                "text": doc_text,
                "type": doc_type,
                "index_pos": self._index.ntotal - len(embeddings) + i,
                "deleted": False,
            })

    # ================================================================== #
    # 检索 — 本地余弦相似度计算
    # ================================================================== #

    def retrieve(self, query_text: str, top_k: int = None) -> List[Dict]:
        """
        用 FAISS 做本地余弦相似度检索。

        Args:
            query_text: 查询文本（新 Beat 的摘要）
            top_k: 返回前 K 个最相关文档

        Returns:
            [{id, text, type, score}, ...]  按相似度降序
        """
        self._ensure_initialized()
        if top_k is None:
            top_k = self.TOP_K

        if self._index.ntotal == 0:
            logger.warning("FAISS 索引为空，无法检索")
            return []

        try:
            query_emb = ai_service.generate_embeddings([query_text])
            if not query_emb:
                return []

            query_vec = np.array(query_emb, dtype=np.float32)

            # 搜索比实际需要多一些（考虑删除标记）
            search_k = min(top_k * 2, self._index.ntotal)
            scores, indices = self._index.search(query_vec, search_k)

            results = []
            for score, idx in zip(scores[0], indices[0]):
                if idx < 0:
                    continue
                # 在文档存储中查找
                doc = next((d for d in self._doc_store
                           if d["index_pos"] == idx and not d.get("deleted")), None)
                if doc:
                    results.append({
                        "id": doc["id"],
                        "text": doc["text"],
                        "type": doc["type"],
                        "score": float(score),
                    })
                if len(results) >= top_k:
                    break

            logger.info(
                "FAISS 检索完成: query_len=%d, 返回 %d 条 (最高相似度=%.4f)",
                len(query_text), len(results),
                results[0]["score"] if results else 0.0,
            )
            return results

        except Exception as e:
            logger.error("FAISS 检索失败: %s", e)
            return []

    # ================================================================== #
    # 一致性审查 — 检索后只传相关片段给 AI
    # ================================================================== #

    def check_consistency(
        self,
        new_beat_json: str,
        world_variables_json: str,
        confirmed_beats_json: str,
        temperature: float = None,
        top_p: float = 0.9,
        top_k: int = 40,
        max_tokens: int = 8192,
    ) -> dict:
        """
        RAG 一致性审查 (AI-Call-6)。

        V2 流程：
        1. 将新 Beat 文本化 → Gemini Embedding
        2. FAISS 本地余弦相似度检索 → Top-K 相关文档
        3. 只将 Top-K 相关文档（而非全量 Beat）发给 AI 做矛盾检测
        4. AI 返回矛盾报告
        """
        if temperature is None:
            temperature = SUGGESTED_TEMPERATURES["rag_check"]

        # 解析新 Beat 用于检索查询
        try:
            new_beat = json.loads(new_beat_json)
        except json.JSONDecodeError:
            new_beat = {}

        # 构建检索查询文本
        events_text = " → ".join(
            e.get("action", "") for e in new_beat.get("causal_events", [])
        )
        query = (
            f"环境:{new_beat.get('setting', '')} "
            f"角色:{','.join(new_beat.get('entities', []))} "
            f"事件:{events_text} "
            f"悬念:{new_beat.get('hook', '')}"
        )

        # FAISS 本地检索 Top-K 相关文档
        retrieved = self.retrieve(query, top_k=self.TOP_K)

        if retrieved:
            # V2: 用检索结果替代全量 context
            retrieved_context = "\n\n".join(
                f"[相似度 {r['score']:.3f}] {r['text']}"
                for r in retrieved
            )
            logger.info(
                "RAG 使用检索模式: %d 条相关文档 (全量 %d 条)",
                len(retrieved), self._index.ntotal,
            )
        else:
            # 降级：索引为空时用全量（兼容首次使用）
            retrieved_context = (
                f"世界观变量:\n{world_variables_json}\n\n"
                f"已确认 Beat:\n{confirmed_beats_json}"
            )
            logger.info("RAG 降级为全量模式（索引为空或检索失败）")

        # 组装 Prompt — 用检索片段替代全量
        user_prompt = (
            USER_PROMPT_RAG_CHECK
            .replace("{new_beat_json}", new_beat_json)
            .replace("{world_variables_json}", retrieved_context)
            .replace("{confirmed_beats_json}", "（已通过向量检索筛选，见上方相关片段）")
        )

        result = ai_service.generate_json(
            user_prompt=user_prompt,
            system_prompt=SYSTEM_PROMPT_RAG_CHECK,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            max_tokens=max_tokens,
        )

        logger.info(
            "RAG 审查完成: 通过 %d/%d, 冲突 %d",
            result.get("pass_count", 0),
            result.get("total_checks", 0),
            result.get("fail_count", 0),
        )
        return result

    # ================================================================== #
    # 管理
    # ================================================================== #

    def clear_database(self):
        """清空向量索引（项目重置时调用）"""
        self._index = faiss.IndexFlatIP(EMBEDDING_DIM)
        self._doc_store = []
        logger.info("FAISS 向量索引已清空")

    def get_stats(self) -> dict:
        """返回索引统计信息"""
        self._ensure_initialized()
        total = self._index.ntotal
        active = sum(1 for d in self._doc_store if not d.get("deleted"))
        wv_count = sum(1 for d in self._doc_store
                       if d["type"] == "world_variable" and not d.get("deleted"))
        beat_count = sum(1 for d in self._doc_store
                        if d["type"] == "confirmed_beat" and not d.get("deleted"))
        return {
            "total_vectors": total,
            "active_documents": active,
            "world_variables": wv_count,
            "confirmed_beats": beat_count,
            "embedding_dim": EMBEDDING_DIM,
            "metric": "cosine_similarity (via IndexFlatIP)",
        }


# 全局单例
rag_controller = RAGController()
