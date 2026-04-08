# -*- coding: utf-8 -*-
"""
Knowledge RAG 业务逻辑（Knowledge Agent 调用封装）
"""
import uuid
import logging
from typing import Optional

from app.core.config import settings, SUPPORTED_MODELS
from app.core.exceptions import ValidationError, ExternalServiceError

logger = logging.getLogger(__name__)


async def invoke_knowledge_qa(
    query: str,
    model_name: str,
    session_id: str,
    collection: Optional[str] = None,
    force_multi_doc: Optional[bool] = None,
    keyword_filter: Optional[str] = None,
    query_image_url: Optional[str] = None,
    query_image_oss_key: Optional[str] = None,
) -> dict:
    """调用 Knowledge Agent 执行 RAG 问答。"""
    if model_name not in SUPPORTED_MODELS:
        raise ValidationError(f"Model '{model_name}' not supported. Available: {list(SUPPORTED_MODELS.keys())}")

    from agents.knowledge import get_knowledge_agent, create_initial_state, RAGConfig
    agent = get_knowledge_agent()

    request_id = str(uuid.uuid4())

    # 读取 kb 的 retrieval_config 注入到 RAGConfig
    rc = {}
    if collection:
        try:
            from app.db import get_kb_repository
            kb = get_kb_repository().get_by_name(collection)
            if kb:
                rc = kb.get("retrieval_config") or {}
        except Exception as e:
            logger.warning(f"读取 kb retrieval_config 失败，使用默认值: {e}")

    # LangGraph 通过 checkpointer（thread_id=session_id）自动恢复历史对话，
    # 无需手动传入历史消息，否则 add_messages reducer 会导致消息重复累加。
    initial_state = create_initial_state(
        query=query,
        user_id="api_user",
        session_id=session_id,
        config=RAGConfig(
            model=model_name,
            retrieval_strategy="hybrid",
            enable_llm_filter=True,
            enable_rerank=True,
            enable_citations=True,
            enable_fallback=True,
            collection=collection or None,
            # 从 kb retrieval_config 注入，缺省用 RAGConfig 默认值
            ranker=rc.get("ranker", "RRF"),
            rrf_k=rc.get("rrf_k", 60),
            hybrid_alpha=rc.get("hybrid_alpha", 0.5),
            multi_doc_top_k=rc.get("multi_doc_top_k", 20),
            multi_doc_group_size=rc.get("multi_doc_group_size", 3),
            strict_group_size=rc.get("strict_group_size", False),
            single_doc_top_k=rc.get("single_doc_top_k", 20),
            llm_context_top_k=rc.get("llm_context_top_k", 10),
            memory_turns=rc.get("memory_turns", 2),
            # 多模态
            kb_type=kb.get("kb_type", "standard") if kb else "standard",
            query_image_url=query_image_url,
            image_vector_dim=rc.get("image_vector_dim", 1024),
            # 用户请求级覆盖（优先级高于 kb 配置）
            force_multi_doc=force_multi_doc,
            keyword_filter=keyword_filter,
        ),
    )

    config = {
        "configurable": {
            "model": model_name,
            "session_id": session_id,
            "thread_id": session_id,  # LangGraph 用 session_id 作为 thread_id 实现对话记忆
        }
    }

    logger.info("处理 knowledge 请求", extra={"session_id": session_id, "request_id": request_id})

    try:
        result = await agent.ainvoke(initial_state, config=config)
    except Exception as e:
        raise ExternalServiceError(f"Knowledge Agent 调用失败: {e}") from e

    metrics = result.get("metrics", {})
    thoughts = {
        "query_analysis": {
            "intent": result.get("query_intent", ""),
            "complexity": result.get("query_complexity", ""),
            "keywords": result.get("query_keywords", []),
        },
        "retrieval": {
            "chunks_retrieved": metrics.total_chunks_retrieved if hasattr(metrics, "total_chunks_retrieved") else 0,
            "chunks_used": metrics.chunks_after_rerank if hasattr(metrics, "chunks_after_rerank") else 0,
        },
        "conversation_turns": 1,
    }

    return_data = {
        "request_id": request_id,
        "session_id": session_id,
        "answer": result["answer"],
        "confidence": result["confidence"],
        "sources": result["sources"],
        "model": model_name,
        "thoughts": thoughts,
        "image_map": result.get("image_map") or None,
    }

    # 持久化消息到 conversation_message 表（仅当 session_id 对应真实会话时）
    try:
        from app.db import get_conversation_repository
        import re as _re
        conv_repo = get_conversation_repository()
        if conv_repo.get_session(session_id):
            # 提取 answer 里的占位符
            answer_text = result["answer"] or ""
            phs = list(set(_re.findall(r'<<IMAGE:[0-9a-f]+>>', answer_text)))

            # 存用户消息（含查询图片 oss_key，用于历史显示和清理）
            conv_repo.add_message(
                session_id=session_id,
                role="user",
                content=query,
                query_image_oss_key=query_image_oss_key,
            )
            # 存 assistant 消息（content 存占位符原文，不存 URL）
            conv_repo.add_message(
                session_id=session_id,
                role="assistant",
                content=answer_text,
                sources=result.get("sources") or [],
                confidence=result.get("confidence"),
                image_placeholders=phs,
            )
            conv_repo.touch_session(session_id)
    except Exception as _e:
        logger.warning(f"消息持久化失败（不影响回答）: {_e}")

    return return_data
