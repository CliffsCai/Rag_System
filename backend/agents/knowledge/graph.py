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
    ↓  ───────────────────────────────────  （single vs multi 条件分支）
  ┌────────────────────────────────────┐
  │ kg_query_route    ← 并行/串行均可，  │
  │ kg_graph_retrieve    设置深度标志、  │
  │                       查图谱写入     │
  │                       kg_graph_chunks│
  └────────────────────────────────────┘
  ┌─────────────────────────────────────────┐
  │ single_doc_retrieve                     │  Milvus RRF hybrid   │
  └─────────────────────────────────────────┘
  ┌─────────────────────────────────────────┐
  │ multi_doc_retrieve                      │  Milvus RRF hybrid
  │   → filter_chunks                       │
  │   → select_top_k_chunks                 │
  └─────────────────────────────────────────┘
    ↓
  generate_answer  ← 读取 merged_chunks + kg_graph_chunks
    ↓               → 分节 prompt（向量 / 图谱）
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
    kg_query_route,
    graph_retrieve,
    single_doc_retrieve,
    multi_doc_retrieve,
    filter_chunks,
    select_top_k_chunks,
    generate_answer,
    check_quality,
    finalize_metrics,
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
    builder.add_node("kg_query_route", kg_query_route)
    builder.add_node("graph_retrieve", graph_retrieve)
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
    # 知识图谱检索：每次都走（kg_query_route 设置深度，graph_retrieve 执行查询）
    builder.add_edge("determine_retrieval_strategy", "kg_query_route")
    builder.add_edge("kg_query_route", "graph_retrieve")

    # 条件路由：single vs multi（检索后与图谱结果汇聚）
    builder.add_conditional_edges(
        "graph_retrieve",
        route_by_query_type,
        {
            "single_doc_retrieve": "single_doc_retrieve",
            "multi_doc_retrieve": "multi_doc_retrieve",
        }
    )

    # single_doc 路径：Milvus RRF hybrid → select_top_k / rerank → generate
    builder.add_edge("single_doc_retrieve", "select_top_k_chunks")

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
    print("[Graph] path: rewrite→classify→strategy→kg_query_route→graph_retrieve→{single|multi}_retrieve→generate")

    return graph
