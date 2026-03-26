# -*- coding: utf-8 -*-
"""
Relevance Filter Node - 检索切片二次过滤
使用 LLM 判断 query 与切片是否相关，过滤不相关的切片
"""

import logging
from datetime import datetime

from dashscope import Generation

from ..state import KnowledgeAgentState
from app.core.config import settings
from app.core.prompts import KNOWLEDGE_RELEVANCE_FILTER_SYSTEM

logger = logging.getLogger(__name__)


def relevance_filter(state: KnowledgeAgentState) -> dict:
    start_time = datetime.now()

    try:
        query = state["query"]
        # single_doc 路径：merged_chunks 直接来自 single_doc_retrieve
        # multi_doc 路径：rerank_chunks 已把 top-K 写回 merged_chunks
        chunks = state.get("merged_chunks") or []

        print(f"[RelevanceFilter] 开始相关性过滤: {len(chunks)} 个切片")

        if not chunks:
            print("[RelevanceFilter] 没有切片需要过滤")
            return {
                "reranked_chunks": [],
                "filtered_chunks": [],
                "chunks_removed": 0,
            }

        # 批量处理（每批 5 个）
        batch_size = 5
        filtered_chunks = []
        filter_decisions = []

        def _content(c):
            return (c.get("content", "") if isinstance(c, dict) else getattr(c, "content", "")) or ""

        def _chunk_id(c):
            return (c.get("id", "") if isinstance(c, dict) else getattr(c, "chunk_id", "")) or ""

        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]

            chunks_text = "\n\n".join(
                f"切片{idx + 1}:\n{_content(c)[:500]}"
                for idx, c in enumerate(batch)
            )

            messages = [
                {
                    "role": "system",
                    "content": KNOWLEDGE_RELEVANCE_FILTER_SYSTEM,
                },
                {
                    "role": "user",
                    "content": f"用户问题: {query}\n\n文档切片:\n{chunks_text}\n\n请判断每个切片的相关性:",
                },
            ]

            try:
                response = Generation.call(
                    api_key=settings.dashscope_api_key,
                    model=state["config"].model,
                    messages=messages,
                    result_format="message",
                )

                if response.status_code == 200:
                    result = response.output.choices[0].message.get("content", "").strip()
                    for line in result.split("\n"):
                        line = line.strip()
                        if "|" in line:
                            parts = line.split("|")
                            if len(parts) == 2:
                                try:
                                    chunk_idx = int(parts[0].strip()) - 1
                                    relevance = parts[1].strip().lower()
                                    if 0 <= chunk_idx < len(batch):
                                        chunk = batch[chunk_idx]
                                        is_relevant = "relevant" in relevance
                                        filter_decisions.append({
                                            "chunk_id": _chunk_id(chunk),
                                            "is_relevant": is_relevant,
                                        })
                                        if is_relevant:
                                            filtered_chunks.append(chunk)
                                except (ValueError, IndexError):
                                    pass
                else:
                    logger.warning(f"[RelevanceFilter] DashScope error {response.status_code}, 保留该批次")
                    filtered_chunks.extend(batch)

            except Exception as e:
                logger.error(f"[RelevanceFilter] 批次处理失败: {e}")
                filtered_chunks.extend(batch)

        chunks_removed = len(chunks) - len(filtered_chunks)
        duration = (datetime.now() - start_time).total_seconds() * 1000

        print(f"[RelevanceFilter] 完成 ({duration:.0f}ms) 原始:{len(chunks)} 保留:{len(filtered_chunks)} 移除:{chunks_removed}")

        metrics = state["metrics"]
        metrics.filter_duration_ms = duration
        metrics.chunks_after_filter = len(filtered_chunks)

        return {
            "reranked_chunks": filtered_chunks,
            "filtered_chunks": filtered_chunks,
            "filter_decisions": filter_decisions,
            "chunks_removed": chunks_removed,
            "metrics": metrics,
            "processing_log": [{
                "stage": "relevance_filter",
                "duration_ms": duration,
                "original_count": len(chunks),
                "filtered_count": len(filtered_chunks),
                "removed_count": chunks_removed,
            }],
        }

    except Exception as e:
        print(f"[RelevanceFilter] 过滤失败: {e}", )
        import traceback; traceback.print_exc()
        fallback = state.get("merged_chunks") or []
        return {
            "reranked_chunks": fallback,
            "filtered_chunks": fallback,
            "chunks_removed": 0,
            "all_warnings": [f"相关性过滤失败，返回原始结果: {e}"],
        }
