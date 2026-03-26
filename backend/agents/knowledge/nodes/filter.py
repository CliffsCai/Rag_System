# -*- coding: utf-8 -*-
"""
Filter Node - 按相关性分数过滤切片（multi_doc 路径专用）
"""

from typing import Dict, Any
from datetime import datetime

from ..state import KnowledgeAgentState


def _score(chunk) -> float:
    """兼容 RetrievedChunk dataclass 和 dict 两种格式取分数"""
    if isinstance(chunk, dict):
        return chunk.get("score", 0.0) or 0.0
    return getattr(chunk, "score", 0.0) or 0.0


def filter_chunks(state: KnowledgeAgentState) -> Dict[str, Any]:
    """
    按相关性分数过滤切片（multi_doc 路径）

    single_doc 路径已在 ADB 层完成 rerank，不经过此节点。
    """
    merged_chunks = state["merged_chunks"]
    config = state["config"]

    print(f"\n[Filter] Filtering {len(merged_chunks)} chunks, threshold={config.vector_score_threshold}")

    try:
        min_score = config.vector_score_threshold
        filtered = [c for c in merged_chunks if _score(c) >= min_score]

        print(f"[Filter] Kept {len(filtered)}/{len(merged_chunks)} chunks")

        metrics = state["metrics"]
        metrics.chunks_after_filter = len(filtered)

        return {
            "filtered_chunks": filtered,
            "metrics": metrics,
            "processing_log": [{
                "stage": "filter",
                "timestamp": datetime.now().isoformat(),
                "chunks_before": len(merged_chunks),
                "chunks_after": len(filtered),
                "threshold": min_score,
            }]
        }

    except Exception as e:
        print(f"[Filter] Error: {e}")
        return {"all_errors": [f"Filtering failed: {e}"]}
