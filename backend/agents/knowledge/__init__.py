# -*- coding: utf-8 -*-
from .graph import create_knowledge_agent
from .state import KnowledgeAgentState, RetrievedChunk, create_initial_state, RAGConfig

_agent = None


def get_knowledge_agent():
    """获取 Knowledge Agent 实例（延迟初始化，模块级缓存）"""
    global _agent
    if _agent is None:
        _agent = create_knowledge_agent()
    return _agent


__all__ = [
    "get_knowledge_agent",
    "create_knowledge_agent",
    "KnowledgeAgentState",
    "RetrievedChunk",
    "create_initial_state",
    "RAGConfig",
]
