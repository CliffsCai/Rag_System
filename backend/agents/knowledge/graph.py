# -*- coding: utf-8 -*-
"""
Knowledge Agent Graph Definition
Defines the complete RAG workflow using LangGraph

Workflow:
  START
    ↓
  query_rewrite          - 改写用户提问，更新rewrite字段
    ↓
  query_classify         - 判断 single_doc / multi_doc，更新query_type字段
    ↓
  determine_retrieval_strategy  - 判断 keyword / hybrid，更新retrieval_strategy
    ↓根据retrieval_strategy、走不同的分支，在graph.py 中add_conditional_edges方法定义条件分支，再通过query_type字段，在检索时选不同的检索方式，具体检索逻辑先不讲
  ┌─────────────────────────────────────────┐
  │ single_doc_retrieve                     │  top_k=20, Milvus RRF hybrid   │
  │   → generate_answer                     │
  └─────────────────────────────────────────┘
  ┌─────────────────────────────────────────┐
  │ multi_doc_retrieve                      │  top_k=20, Milvus RRF hybrid
  │   → filter_chunks (score 阈值过滤)      │  │
  │   → select_top_k_chunks (排序截断)      │
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
from typing import Literal, Optional, List

from .state import KnowledgeAgentState
from .nodes import (
    query_rewrite,
    query_classify,
    determine_retrieval_strategy,
    single_doc_retrieve,
    multi_doc_retrieve,
    filter_chunks,
    select_top_k_chunks,
    generate_answer,
    check_quality,
    finalize_metrics
)


def route_by_query_type(state: KnowledgeAgentState) -> Literal["single_doc_retrieve", "multi_doc_retrieve"]:
    """根据 query_type 路由到不同检索节点"""
    return "single_doc_retrieve" if state.get("query_type") == "single_doc" else "multi_doc_retrieve"


# def route_after_single_retrieve(state: KnowledgeAgentState) -> Literal["relevance_filter"]:
#     """single_doc 路径：跳过 filter/rerank，直接进 LLM 二次过滤"""
#     return "relevance_filter"


def route_after_multi_retrieve(state: KnowledgeAgentState) -> Literal["filter_chunks"]:
    """multi_doc 路径：先 score 过滤，再 rerank"""
    return "filter_chunks"


def should_check_quality(state: KnowledgeAgentState) -> Literal["check_quality", "finalize_metrics"]:
    config = state["config"]
    return "check_quality" if config.enable_fallback else "finalize_metrics"


def create_knowledge_agent(checkpointer=None, interrupt_before: Optional[List[str]] = None):
    """
    创建 Knowledge Agent

    Args:
        checkpointer: LangGraph checkpointer（AsyncPostgresSaver 或 MemorySaver）
        interrupt_before: 若包含 'generate_answer'，则 ainvoke 在生成前暂停，供 OpenAI 兼容流式补全后 aupdate_state + 二次 ainvoke 恢复
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
    builder.add_node("select_top_k_chunks", select_top_k_chunks)
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
    builder.add_edge("filter_chunks", "select_top_k_chunks")
    builder.add_edge("select_top_k_chunks", "generate_answer")

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

    compile_kw = {"checkpointer": checkpointer}
    if interrupt_before:
        compile_kw["interrupt_before"] = interrupt_before
    graph = builder.compile(**compile_kw)

    print("[Graph] Knowledge Agent created")
    print("[Graph] single_doc: rewrite→classify→strategy→single_retrieve(Milvus hybrid)→generate")
    print("[Graph] multi_doc:  rewrite→classify→strategy→multi_retrieve→filter→rerank→generate")

    return graph
