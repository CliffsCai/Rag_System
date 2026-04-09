# -*- coding: utf-8 -*-
"""
Multi Document Retrieve Node - 多文档查询
跨多个文档进行检索,返回top 20结果
"""

import logging
from datetime import datetime
from typing import List

from ..state import KnowledgeAgentState, RetrievedChunk, RetrievalStrategy
from ..services.retrieval import get_retrieval_service

logger = logging.getLogger(__name__)


def multi_doc_retrieve(state: KnowledgeAgentState) -> KnowledgeAgentState:
    """
    多文档查询节点
    
    功能:
    - 跨多个文档进行检索
    - 返回top k结果
    - 根据retrieval_strategy使用相应的检索方式
    
    Args:
        state: 当前agent状态
        
    Returns:
        更新后的状态,包含检索到的chunks
    """
    start_time = datetime.now()
    
    try:
        query = state["rewritten_query"]
        retrieval_strategy = state.get("retrieval_strategy", RetrievalStrategy.HYBRID)
        _cfg = state.get("config")
        collection = _cfg.collection if _cfg else None

        # 从 RAGConfig 读检索参数（已由 knowledge_service 从 kb retrieval_config 注入）
        ranker         = _cfg.ranker              if _cfg else "RRF"
        rrf_k          = _cfg.rrf_k               if _cfg else 60
        hybrid_alpha   = _cfg.hybrid_alpha         if _cfg else 0.5
        top_k          = _cfg.multi_doc_top_k      if _cfg else 20
        group_size     = _cfg.multi_doc_group_size if _cfg else 3
        strict_group   = _cfg.strict_group_size    if _cfg else False
        keyword_filter = _cfg.keyword_filter       if _cfg else None

        # 多模态知识库走专用检索节点（分组搜索参数透传）
        if getattr(_cfg, "kb_type", "standard") == "multimodal":
            from .multimodal_retrieve import multimodal_retrieve
            return multimodal_retrieve(
                state,
                group_by_field="file_name",
                group_size=group_size,
                strict_group_size=strict_group,
            )

        logger.info(f"[MultiDocRetrieve] 开始多文档检索: {query}")
        logger.info(f"[MultiDocRetrieve] 检索策略: {retrieval_strategy.value}, ranker={ranker}, top_k={top_k}, group_size={group_size}")
        print(f"\n[MultiDocRetrieve] query={query}, strategy={retrieval_strategy}")
        
        # 获取检索服务
        retrieval_service = get_retrieval_service()
        
        # 根据策略选择检索方式
        if retrieval_strategy == RetrievalStrategy.KEYWORD_ONLY:
            logger.info("[MultiDocRetrieve] 使用关键词检索")
            chunks = retrieval_service.keyword_search(
                query=query,
                top_k=top_k,
                collection=collection,
                keyword_filter=keyword_filter,
                ranker=ranker,
                rrf_k=rrf_k,
                hybrid_alpha=hybrid_alpha,
            )
        elif retrieval_strategy == RetrievalStrategy.HYBRID:
            logger.info("[MultiDocRetrieve] 使用混合检索（分组搜索，按 file_name 保证多文档多样性）")
            chunks = retrieval_service.hybrid_search(
                query=query,
                top_k=top_k,
                collection=collection,
                group_by_field="file_name",
                group_size=group_size,
                strict_group_size=strict_group,
                ranker=ranker,
                rrf_k=rrf_k,
                hybrid_alpha=hybrid_alpha,
            )
        else:
            logger.warning(f"[MultiDocRetrieve] 未知策略 {retrieval_strategy}, 使用混合检索")
            chunks = retrieval_service.hybrid_search(
                query=query,
                top_k=top_k,
                collection=collection,
                group_by_field="file_name",
                group_size=group_size,
                strict_group_size=strict_group,
                ranker=ranker,
                rrf_k=rrf_k,
                hybrid_alpha=hybrid_alpha,
            )
        
        duration = (datetime.now() - start_time).total_seconds() * 1000
        
        logger.info(f"[MultiDocRetrieve] 检索完成 ({duration:.0f}ms): 找到 {len(chunks)} 个结果")
        
        # 更新metrics
        metrics = state["metrics"]
        metrics.retrieval_duration_ms = duration
        metrics.total_chunks_retrieved = len(chunks)
        
        return {
            "merged_chunks": chunks,
            "total_candidates": len(chunks),
            "retrieval_strategy_used": retrieval_strategy,
            "metrics": metrics,
            "processing_log": [{
                "stage": "multi_doc_retrieve",
                "duration_ms": duration,
                "chunks_count": len(chunks),
                "strategy": retrieval_strategy.value,
            }],
        }

    except Exception as e:
        logger.error(f"[MultiDocRetrieve] 检索失败: {e}", exc_info=True)
        return {
            "merged_chunks": [],
            "total_candidates": 0,
            "all_errors": [f"多文档检索失败: {e}"],
            "error": str(e),
            "error_stage": "multi_doc_retrieve",
        }
