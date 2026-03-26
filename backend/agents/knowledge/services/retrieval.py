# -*- coding: utf-8 -*-
"""
Retrieval Service - ADB Document Collection Integration
"""

from typing import List, Optional
import logging
from app.services.adb_document_service import get_adb_document_service
from app.core.config import settings

logger = logging.getLogger(__name__)


class RetrievalService:
    """Retrieval service using ADB QueryContent API"""

    def _get_doc_service(self, collection: Optional[str] = None):
        """根据 collection 获取 doc service，不传则用默认"""
        from app.services.adb_document_service import ADBDocumentService
        if collection:
            return ADBDocumentService(namespace=settings.adb_namespace, collection=collection)
        return get_adb_document_service()

    def vector_search(
        self,
        query: str,
        top_k: int = 10,
        filter_str: Optional[str] = None,
        rerank_factor: Optional[float] = None,
        collection: Optional[str] = None,
    ) -> List[dict]:
        """向量+全文混合检索（alpha=0.5），直接返回 ADB 原始 dict 列表"""
        if rerank_factor is not None and rerank_factor <= 1:
            logger.warning(f"rerank_factor={rerank_factor} 非法，已忽略")
            rerank_factor = None

        doc_service = self._get_doc_service(collection)
        results = doc_service.query_content(
            query=query,
            top_k=top_k,
            filter_str=filter_str,
            rerank_factor=rerank_factor,
            hybrid_search="Weight",
            hybrid_search_args={"Weight": {"alpha": 0.5}},
            include_file_url=True,
        )

        print(f"[Retrieval] vector_search 返回 {len(results)} 个结果")
        return results

    def keyword_search(
        self,
        query: str,
        top_k: int = 10,
        filter_str: Optional[str] = None,
        collection: Optional[str] = None,
    ) -> List[dict]:
        """纯关键词检索（alpha=0.0），直接返回 ADB 原始 dict 列表"""
        doc_service = self._get_doc_service(collection)
        results = doc_service.query_content(
            query=query,
            top_k=top_k,
            filter_str=filter_str,
            rerank_factor=None,
            hybrid_search="Weight",
            hybrid_search_args={"Weight": {"alpha": 0.0}},
            include_file_url=True,
        )

        print(f"[Retrieval] keyword_search 返回 {len(results)} 个结果")
        return results

    def hybrid_search(
        self,
        query: str,
        top_k: int = 10,
        filter_str: Optional[str] = None,
        rerank_factor: Optional[float] = None,
        collection: Optional[str] = None,
    ) -> List[dict]:
        """混合检索（向量+全文，alpha=0.5）"""
        return self.vector_search(query=query, top_k=top_k, filter_str=filter_str, rerank_factor=rerank_factor, collection=collection)


# 全局单例
_retrieval_service = None


def get_retrieval_service() -> RetrievalService:
    global _retrieval_service
    if _retrieval_service is None:
        _retrieval_service = RetrievalService()
    return _retrieval_service
