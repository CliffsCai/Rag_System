# -*- coding: utf-8 -*-
"""
Embedding 服务
封装 DashScope text-embedding API，支持批量调用和限流重试
"""
import logging
import time
from typing import List, Optional

import dashscope
from dashscope import TextEmbedding

from app.core.config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:

    def __init__(self):
        dashscope.api_key = settings.dashscope_api_key
        self.model = settings.embedding_model
        self.batch_size = settings.embedding_batch_size
        self.dimension = settings.embedding_dimension

    def embed_texts(self, texts: List[str], dimension: Optional[int] = None) -> List[List[float]]:
        """
        批量生成向量。
        DashScope 单次最多 25 条，超出自动分批。
        返回与 texts 等长的向量列表。
        dimension: 指定输出维度，None 则使用配置默认值
        """
        if not texts:
            return []

        dim = dimension or self.dimension
        all_vectors: List[List[float]] = []
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i: i + self.batch_size]
            vectors = self._embed_batch(batch, dimension=dim)
            all_vectors.extend(vectors)

        return all_vectors

    def embed_query(self, text: str, dimension: Optional[int] = None) -> List[float]:
        """单条查询向量"""
        dim = dimension or self.dimension
        vectors = self._embed_batch([text], dimension=dim)
        return vectors[0] if vectors else []

    def _embed_batch(self, texts: List[str], retry: int = 5, dimension: Optional[int] = None) -> List[List[float]]:
        for attempt in range(retry):
            try:
                resp = TextEmbedding.call(
                    model=self.model,
                    input=texts,
                    dimension=dimension,
                )
                if resp.status_code != 200:
                    raise RuntimeError(f"DashScope embedding 失败: {resp.message}")
                embeddings = resp.output["embeddings"]
                # 按 text_index 排序确保顺序一致
                embeddings.sort(key=lambda x: x["text_index"])
                return [e["embedding"] for e in embeddings]
            except Exception as e:
                if attempt < retry - 1:
                    wait = min(2 ** attempt * 2, 60)  # 2s, 4s, 8s, 16s，最多 60s
                    logger.warning(f"Embedding 调用失败，{wait}s 后重试 ({attempt+1}/{retry}): {e}")
                    time.sleep(wait)
                else:
                    logger.error(f"Embedding 调用最终失败: {e}")
                    raise
        return []


_instance = None


def get_embedding_service() -> EmbeddingService:
    global _instance
    if _instance is None:
        _instance = EmbeddingService()
    return _instance
