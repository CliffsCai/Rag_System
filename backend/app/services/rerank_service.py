# -*- coding: utf-8 -*-
"""
Rerank 服务
封装 DashScope TextReRank API（qwen3-rerank）
输入 query + chunks（无占位符的纯文本），输出按 relevance_score 降序排列的 chunks
"""
import logging
import time
from typing import List

import dashscope

from app.core.config import settings

logger = logging.getLogger(__name__)

# 单次请求最多 500 个文档
_MAX_DOCS_PER_REQUEST = 500


class RerankService:

    def __init__(self):
        dashscope.api_key = settings.dashscope_api_key

    def rerank(
        self,
        query: str,
        chunks: list,
        model: str = "qwen3-rerank",
        top_n: int = 10,
        retry: int = 3,
    ) -> list:
        """
        对 chunks 按与 query 的语义相关性重排，返回 top_n 个。

        chunks 格式：dict（含 content 字段）或 RetrievedChunk dataclass。
        content 应为 Milvus 中存储的无占位符纯文本。

        返回：原 chunk 对象列表（附加 rerank_score 字段），按 relevance_score 降序。
        """
        if not chunks or not query:
            return chunks[:top_n]

        # 截断到 API 上限
        candidates = chunks[:_MAX_DOCS_PER_REQUEST]

        documents = [
            c.get("content", "") if isinstance(c, dict) else getattr(c, "content", "")
            for c in candidates
        ]

        for attempt in range(retry):
            try:
                resp = dashscope.TextReRank.call(
                    model=model,
                    query=query,
                    documents=documents,
                    top_n=top_n,
                    return_documents=False,
                )
                if resp.status_code != 200:
                    raise RuntimeError(f"TextReRank 失败: {resp.message}")

                # results 已按 relevance_score 降序排列
                results = resp.output["results"]
                reranked = []
                for r in results:
                    idx = r["index"]
                    score = r["relevance_score"]
                    chunk = candidates[idx]
                    # 写回 rerank_score
                    if isinstance(chunk, dict):
                        chunk = {**chunk, "rerank_score": score}
                    else:
                        chunk.rerank_score = score
                    reranked.append(chunk)

                logger.info(f"[Rerank] {model} 完成，输入 {len(candidates)} 条，输出 {len(reranked)} 条")
                return reranked

            except Exception as e:
                if attempt < retry - 1:
                    wait = 2 ** attempt
                    logger.warning(f"[Rerank] 第 {attempt+1} 次失败，{wait}s 后重试: {e}")
                    time.sleep(wait)
                else:
                    logger.error(f"[Rerank] 最终失败，降级为原始排序: {e}")
                    # 降级：按原始 score 排序取 top_n
                    return sorted(
                        candidates,
                        key=lambda c: c.get("score", 0.0) if isinstance(c, dict) else getattr(c, "score", 0.0),
                        reverse=True,
                    )[:top_n]

        return chunks[:top_n]


_instance = None


def get_rerank_service() -> RerankService:
    global _instance
    if _instance is None:
        _instance = RerankService()
    return _instance
