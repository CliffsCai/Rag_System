# -*- coding: utf-8 -*-
"""
Rerank Node - 按分数排序并取 top-K（multi_doc 路径专用）

single_doc 路径已在 ADB 层完成 rerank，不经过此节点。
注意：此处是基于已有分数的排序，不是 cross-encoder rerank。
     ADB 层的 rerank_factor 才是真正的 cross-encoder rerank。
"""

from typing import Dict, Any
from datetime import datetime

from ..state import KnowledgeAgentState


def _score(chunk) -> float:
    """兼容 RetrievedChunk dataclass 和 dict 两种格式取分数"""
    if isinstance(chunk, dict):
        return chunk.get("rerank_score") or chunk.get("score", 0.0) or 0.0
    return getattr(chunk, "rerank_score", None) or getattr(chunk, "score", 0.0) or 0.0


def rerank_chunks(state: KnowledgeAgentState) -> Dict[str, Any]:
    """
    对 filtered_chunks 按分数降序排列，取 top rerank_top_k（multi_doc 路径）
    结果写入 reranked_chunks 和 merged_chunks（供 relevance_filter 读取）
    """
    filtered_chunks = state["filtered_chunks"]
    config = state["config"]

    print(f"\n[Rerank] Sorting {len(filtered_chunks)} chunks, top_k={config.rerank_top_k}")

    try:
        sorted_chunks = sorted(filtered_chunks, key=_score, reverse=True)
        top_chunks = sorted_chunks[:config.rerank_top_k]

        print(f"[Rerank] Selected top {len(top_chunks)} chunks")

        metrics = state["metrics"]
        metrics.chunks_after_rerank = len(top_chunks)

        return {
            "reranked_chunks": top_chunks,
            "merged_chunks": top_chunks,   # generate_answer 读 merged_chunks
            "metrics": metrics,
            "processing_log": [{
                "stage": "rerank",
                "timestamp": datetime.now().isoformat(),
                "chunks_in": len(filtered_chunks),
                "chunks_out": len(top_chunks),
            }]
        }

    except Exception as e:
        print(f"[Rerank] Error: {e}")
        return {"all_errors": [f"Reranking failed: {e}"]}
