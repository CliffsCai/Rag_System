# -*- coding: utf-8 -*-
"""
Select / Rerank Node（single_doc 和 multi_doc 路径共用）

无 rerank（rerank_enabled=False）：
  按 RRF score 降序取 llm_context_top_k，与原逻辑完全一致。

有 rerank（rerank_enabled=True，非多模态知识库）：
  调用 qwen3-rerank 对候选 chunks 重排，
  single_doc 取 single_doc_rerank_top_k，multi_doc 取 multi_doc_rerank_top_k。
  rerank 失败时自动降级为原始 score 排序。

数据来源：
  multi_doc 路径：filtered_chunks（经过 filter_chunks 节点）
  single_doc 路径：merged_chunks（直接来自检索节点，未经 filter）
  优先读 filtered_chunks，为空则 fallback 到 merged_chunks。
"""

from typing import Dict, Any
from datetime import datetime

from ..state import KnowledgeAgentState


def _score(chunk) -> float:
    if isinstance(chunk, dict):
        return chunk.get("rerank_score") or chunk.get("score", 0.0) or 0.0
    return getattr(chunk, "rerank_score", None) or getattr(chunk, "score", 0.0) or 0.0


def select_top_k_chunks(state: KnowledgeAgentState) -> Dict[str, Any]:
    """
    统一的截断 / rerank 节点，single_doc 和 multi_doc 路径共用。
    """
    # 数据来源：filtered_chunks 优先，为空则用 merged_chunks
    candidates = state.get("filtered_chunks") or state.get("merged_chunks") or []
    config = state["config"]

    is_multi_doc = bool(state.get("filtered_chunks"))  # multi_doc 路径有 filtered_chunks
    is_multimodal = getattr(config, "kb_type", "standard") == "multimodal"
    rerank_enabled = getattr(config, "rerank_enabled", False) and not is_multimodal

    print(f"\n[SelectTopK] candidates={len(candidates)}, rerank={rerank_enabled}, multi_doc={is_multi_doc}")

    try:
        if rerank_enabled and candidates:
            # ── Rerank 路径 ──────────────────────────────────────────────────
            top_k = (
                getattr(config, "multi_doc_rerank_top_k", 10)
                if is_multi_doc
                else getattr(config, "single_doc_rerank_top_k", 5)
            )
            query = state.get("rewritten_query") or state.get("query", "")
            model = getattr(config, "rerank_model_name", "qwen3-rerank")

            from app.services.rerank_service import get_rerank_service
            top_chunks = get_rerank_service().rerank(
                query=query,
                chunks=candidates,
                model=model,
                top_n=top_k,
            )
            method = f"rerank({model})"
        else:
            # ── 原始 score 排序路径 ──────────────────────────────────────────
            top_k = getattr(config, "llm_context_top_k", 10)
            top_chunks = sorted(candidates, key=_score, reverse=True)[:top_k]
            method = "score_sort"

        print(f"[SelectTopK] method={method}, selected={len(top_chunks)}")

        metrics = state["metrics"]
        metrics.chunks_after_rerank = len(top_chunks)

        return {
            "reranked_chunks": top_chunks,
            "merged_chunks": top_chunks,
            "metrics": metrics,
            "processing_log": [{
                "stage": "select_top_k",
                "timestamp": datetime.now().isoformat(),
                "method": method,
                "chunks_in": len(candidates),
                "chunks_out": len(top_chunks),
            }],
        }

    except Exception as e:
        print(f"[SelectTopK] Error: {e}")
        return {"all_errors": [f"select_top_k failed: {e}"]}
