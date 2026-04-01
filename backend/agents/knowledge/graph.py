# -*- coding: utf-8 -*-
"""
Knowledge Agent Graph Definition
Defines the complete RAG workflow using LangGraph

Workflow:
  START
    ↓
  query_rewrite          - 改写用户提问
    ↓
  query_classify         - 判断 single_doc / multi_doc
    ↓
  determine_retrieval_strategy  - 判断 keyword / hybrid
    ↓
  ┌─────────────────────────────────────────┐
  │ single_doc_retrieve                     │  top_k=20, Milvus RRF hybrid
  │   → relevance_filter (LLM 二次过滤)     │
  │   → generate_answer                     │
  └─────────────────────────────────────────┘
  ┌─────────────────────────────────────────┐
  │ multi_doc_retrieve                      │  top_k=50, Milvus RRF hybrid
  │   → filter_chunks (score 阈值过滤)      │
  │   → rerank_chunks  (按分数排序取 top-K) │
  │   → relevance_filter (LLM 二次过滤)     │
  │   → generate_answer                     │
  └─────────────────────────────────────────┘
    ↓
  check_quality (conditional)
    ↓
  finalize_metrics
    ↓
  END
"""

from langgraph.graph import StateGraph, START, END
from typing import Literal

from .state import KnowledgeAgentState
from .nodes import (
    query_rewrite,
    query_classify,
    determine_retrieval_strategy,
    single_doc_retrieve,
    multi_doc_retrieve,
    filter_chunks,
    rerank_chunks,
    generate_answer,
    check_quality,
    finalize_metrics
)


def route_by_query_type(state: KnowledgeAgentState) -> Literal["single_doc_retrieve", "multi_doc_retrieve"]:
    """根据 query_type 路由到不同检索节点"""
    return "single_doc_retrieve" if state.get("query_type") == "single_doc" else "multi_doc_retrieve"


def route_after_single_retrieve(state: KnowledgeAgentState) -> Literal["relevance_filter"]:
    """single_doc 路径：跳过 filter/rerank，直接进 LLM 二次过滤"""
    return "relevance_filter"


def route_after_multi_retrieve(state: KnowledgeAgentState) -> Literal["filter_chunks"]:
    """multi_doc 路径：先 score 过滤，再 rerank"""
    return "filter_chunks"


def should_check_quality(state: KnowledgeAgentState) -> Literal["check_quality", "finalize_metrics"]:
    config = state["config"]
    return "check_quality" if config.enable_fallback else "finalize_metrics"


def create_knowledge_agent(checkpointer=None):
    """
    创建 Knowledge Agent

    Args:
        checkpointer: LangGraph checkpointer（AsyncPostgresSaver 或 MemorySaver）
    Returns:
        Compiled LangGraph agent
    """
    print("\n[Graph] Building Knowledge Agent")

    builder = StateGraph(KnowledgeAgentState)

    # ── 节点 ──────────────────────────────────────────────────────────────────
    builder.add_node("query_rewrite", query_rewrite)
    builder.add_node("query_classify", query_classify)
    builder.add_node("determine_retrieval_strategy", determine_retrieval_strategy)
    builder.add_node("single_doc_retrieve", single_doc_retrieve)
    builder.add_node("multi_doc_retrieve", multi_doc_retrieve)
    builder.add_node("filter_chunks", filter_chunks)
    builder.add_node("rerank_chunks", rerank_chunks)
    builder.add_node("generate_answer", generate_answer)
    builder.add_node("check_quality", check_quality)
    builder.add_node("finalize_metrics", finalize_metrics)

    # ── 边 ───────────────────────────────────────────────────────────────────
    builder.add_edge(START, "query_rewrite")
    builder.add_edge("query_rewrite", "query_classify")
    builder.add_edge("query_classify", "determine_retrieval_strategy")

    # 条件路由：single vs multi
    builder.add_conditional_edges(
        "determine_retrieval_strategy",
        route_by_query_type,
        {
            "single_doc_retrieve": "single_doc_retrieve",
            "multi_doc_retrieve": "multi_doc_retrieve",
        }
    )

    # single_doc 路径：Milvus RRF hybrid → 直接 generate
    builder.add_edge("single_doc_retrieve", "generate_answer")

    # multi_doc 路径：score 过滤 → rerank → generate
    builder.add_edge("multi_doc_retrieve", "filter_chunks")
    builder.add_edge("filter_chunks", "rerank_chunks")
    builder.add_edge("rerank_chunks", "generate_answer")

    builder.add_conditional_edges(
        "generate_answer",
        should_check_quality,
        {
            "check_quality": "check_quality",
            "finalize_metrics": "finalize_metrics",
        }
    )

    builder.add_edge("check_quality", "finalize_metrics")
    builder.add_edge("finalize_metrics", END)

    graph = builder.compile(checkpointer=checkpointer)

    print("[Graph] Knowledge Agent created")
    print("[Graph] single_doc: rewrite→classify→strategy→single_retrieve(Milvus hybrid)→relevance_filter→generate")
    print("[Graph] multi_doc:  rewrite→classify→strategy→multi_retrieve→filter→rerank→relevance_filter→generate")

    return graph
