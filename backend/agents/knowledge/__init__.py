# -*- coding: utf-8 -*-
from .graph import create_knowledge_agent
from .state import KnowledgeAgentState, RetrievedChunk, create_initial_state, RAGConfig

_agent = None


def get_knowledge_agent():
    """获取 Knowledge Agent 实例（延迟初始化，注入 PostgresSaver checkpointer）"""
    global _agent
    if _agent is None:
        from app.core.checkpointer import get_checkpointer
        checkpointer = get_checkpointer()
        _agent = create_knowledge_agent(checkpointer=checkpointer)
    return _agent


__all__ = [
    "get_knowledge_agent",
    "create_knowledge_agent",
    "KnowledgeAgentState",
    "RetrievedChunk",
    "create_initial_state",
    "RAGConfig",
]
