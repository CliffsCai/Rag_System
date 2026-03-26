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
        query = state["query"]
        retrieval_strategy = state.get("retrieval_strategy", RetrievalStrategy.HYBRID)
        collection = (state.get("config") or {}) and getattr(state.get("config"), "collection", None)

        logger.info(f"[MultiDocRetrieve] 开始多文档检索: {query}")
        logger.info(f"[MultiDocRetrieve] 检索策略: {retrieval_strategy.value}")
        print(f"\n[MultiDocRetrieve] query={query}, strategy={retrieval_strategy}")
        
        # 获取检索服务
        retrieval_service = get_retrieval_service()
        
        # 根据策略选择检索方式
        if retrieval_strategy == RetrievalStrategy.KEYWORD_ONLY:
            logger.info("[MultiDocRetrieve] 使用关键词检索")
            chunks = retrieval_service.keyword_search(
                query=query,
                top_k=50,
                collection=collection,
            )
        elif retrieval_strategy == RetrievalStrategy.HYBRID:
            logger.info("[MultiDocRetrieve] 使用混合检索（广撒网，后续 filter/rerank node 处理）")
            chunks = retrieval_service.hybrid_search(
                query=query,
                top_k=50,
                collection=collection,
            )
        else:
            logger.warning(f"[MultiDocRetrieve] 未知策略 {retrieval_strategy}, 使用混合检索")
            chunks = retrieval_service.hybrid_search(
                query=query,
                top_k=50,
                collection=collection,
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
