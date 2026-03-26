# -*- coding: utf-8 -*-
"""
Knowledge RAG 业务逻辑（Knowledge Agent 调用封装）
"""
import uuid
import logging
from typing import Optional

from langchain_core.messages import HumanMessage, AIMessage

from app.core.config import settings, SUPPORTED_MODELS
from app.core.exceptions import ValidationError, ExternalServiceError

logger = logging.getLogger(__name__)


def invoke_knowledge_qa(
    query: str,
    model_name: str,
    session_id: str,
    collection: Optional[str] = None,
    messages: Optional[list] = None,
) -> dict:
    """
    调用 Knowledge Agent 执行 RAG 问答。
    messages: [{"role": "user"|"assistant", "content": str}]（历史对话，可选）
    """
    if model_name not in SUPPORTED_MODELS:
        raise ValidationError(f"Model '{model_name}' not supported. Available: {list(SUPPORTED_MODELS.keys())}")

    from agents.knowledge import get_knowledge_agent, create_initial_state, RAGConfig
    agent = get_knowledge_agent()

    request_id = str(uuid.uuid4())

    lc_messages = None
    if messages:
        lc_messages = []
        for msg in messages:
            if msg["role"] == "user":
                lc_messages.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                lc_messages.append(AIMessage(content=msg["content"]))
        lc_messages.append(HumanMessage(content=query))

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
        ),
        messages=lc_messages,
    )

    config = {
        "configurable": {
            "model": model_name,
            "session_id": session_id,
            "thread_id": f"knowledge_{session_id}_{request_id}",
        }
    }

    logger.info("处理 knowledge 请求", extra={"session_id": session_id, "request_id": request_id})

    try:
        result = agent.invoke(initial_state, config=config)
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
        "conversation_turns": len(lc_messages) if lc_messages else 1,
    }

    return {
        "request_id": request_id,
        "session_id": session_id,
        "answer": result["answer"],
        "confidence": result["confidence"],
        "sources": result["sources"],
        "model": model_name,
        "thoughts": thoughts,
        "image_map": result.get("image_map") or None,
    }
