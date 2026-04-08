# -*- coding: utf-8 -*-
"""
Multimodal Retrieve Node - 多模态知识库检索
三路 AnnSearchRequest：text dense + BM25 + image dense
用户可同时传文字和图片查询，图片向量加入 image_dense 路。
"""
import logging
from datetime import datetime
from typing import List, Optional

from ..state import KnowledgeAgentState, RetrievalStrategy
from app.services.milvus_service import get_milvus_service

logger = logging.getLogger(__name__)


def multimodal_retrieve(
    state: KnowledgeAgentState,
    group_by_field: Optional[str] = None,
    group_size: int = 1,
    strict_group_size: bool = False,
) -> dict:
    """
    多模态检索：text dense + BM25 + image dense 三路 hybrid_search。
    - query_image_url 有值时，生成图片查询向量加入 image_dense 路
    - query_image_url 为空时，用文字向量同时查 image_dense（跨模态）
    """
    start_time = datetime.now()

    try:
        query = state["query"]
        _cfg = state.get("config")
        collection = _cfg.collection if _cfg else None
        retrieval_strategy = state.get("retrieval_strategy", RetrievalStrategy.HYBRID)

        ranker         = _cfg.ranker              if _cfg else "RRF"
        rrf_k          = _cfg.rrf_k               if _cfg else 60
        hybrid_alpha   = _cfg.hybrid_alpha         if _cfg else 0.5
        top_k          = _cfg.multi_doc_top_k      if _cfg else 20
        keyword_filter = _cfg.keyword_filter       if _cfg else None
        query_image_url = getattr(_cfg, "query_image_url", None)
        # image_vector_dim 与 kb.vector_dim 在创建时已强制对齐
        image_vector_dim = getattr(_cfg, "image_vector_dim", 1024)

        logger.info(f"[MultimodalRetrieve] query={query}, image={'yes' if query_image_url else 'no'}")

        # 生成图片查询向量
        query_image_vector = None
        if query_image_url:
            try:
                from app.services.multimodal_embedding_service import get_multimodal_embedding_service
                query_image_vector = get_multimodal_embedding_service().embed_image(
                    query_image_url, dimension=image_vector_dim
                )
                logger.info("[MultimodalRetrieve] 用户图片向量化完成")
            except Exception as e:
                logger.warning(f"[MultimodalRetrieve] 用户图片向量化失败，降级为纯文字检索: {e}")
        else:
            # 无用户图片时，用文字向量查 image_dense（跨模态检索）
            try:
                from app.services.multimodal_embedding_service import get_multimodal_embedding_service
                query_image_vector = get_multimodal_embedding_service().embed_text(
                    query, dimension=image_vector_dim
                )
                logger.info("[MultimodalRetrieve] 文字跨模态查询 image_dense")
            except Exception as e:
                logger.warning(f"[MultimodalRetrieve] 跨模态文字向量化失败: {e}")

        milvus_svc = get_milvus_service()

        # 多模态 kb 的 dense 字段用 qwen3-vl-embedding 生成
        from app.services.multimodal_embedding_service import get_multimodal_embedding_service
        mm_svc = get_multimodal_embedding_service()
        query_text_vector = mm_svc.embed_text(query, dimension=image_vector_dim)

        if retrieval_strategy == RetrievalStrategy.KEYWORD_ONLY:
            chunks = milvus_svc.hybrid_search(
                collection_name=collection,
                query=query,
                top_k=top_k,
                keyword_filter=keyword_filter or query,
                ranker=ranker,
                rrf_k=rrf_k,
                hybrid_alpha=hybrid_alpha,
                query_image_vector=query_image_vector,
                query_text_vector=query_text_vector,
            )
        else:
            chunks = milvus_svc.hybrid_search(
                collection_name=collection,
                query=query,
                top_k=top_k,
                ranker=ranker,
                rrf_k=rrf_k,
                hybrid_alpha=hybrid_alpha,
                group_by_field=group_by_field,
                group_size=group_size,
                strict_group_size=strict_group_size,
                query_image_vector=query_image_vector,
                query_text_vector=query_text_vector,
            )

        duration = (datetime.now() - start_time).total_seconds() * 1000
        logger.info(f"[MultimodalRetrieve] 完成 ({duration:.0f}ms): {len(chunks)} 条")

        metrics = state["metrics"]
        metrics.retrieval_duration_ms = duration
        metrics.total_chunks_retrieved = len(chunks)

        return {
            "merged_chunks": chunks,
            "total_candidates": len(chunks),
            "retrieval_strategy_used": retrieval_strategy,
            "metrics": metrics,
            "processing_log": [{
                "stage": "multimodal_retrieve",
                "duration_ms": duration,
                "chunks_count": len(chunks),
                "has_image_query": bool(query_image_url),
            }],
        }

    except Exception as e:
        logger.error(f"[MultimodalRetrieve] 检索失败: {e}", exc_info=True)
        return {
            "merged_chunks": [],
            "total_candidates": 0,
            "all_errors": [f"多模态检索失败: {e}"],
        }
