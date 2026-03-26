# -*- coding: utf-8 -*-
"""
Node 5: Generate
Generates answer based on retrieved context using DashScope Generation.call()
with tool calling support
"""

from typing import Dict, Any
from datetime import datetime

from dashscope import Generation
from langchain_core.messages import AIMessage

from ..state import KnowledgeAgentState
from app.core.config import settings
from app.core.prompts import KNOWLEDGE_GENERATE_SYSTEM_GREETING, KNOWLEDGE_GENERATE_SYSTEM, KNOWLEDGE_GENERATE_SYSTEM_IMAGE


def _convert_messages_to_dicts(messages) -> list:
    """Convert LangChain BaseMessage list to plain dicts for DashScope"""
    result = []
    for msg in messages:
        if hasattr(msg, "type"):
            if msg.type == "human":
                result.append({"role": "user", "content": msg.content})
            elif msg.type == "ai":
                entry = {"role": "assistant", "content": msg.content or ""}
                # preserve tool_calls if present
                if hasattr(msg, "additional_kwargs") and msg.additional_kwargs.get("tool_calls"):
                    entry["tool_calls"] = msg.additional_kwargs["tool_calls"]
                result.append(entry)
            elif msg.type == "tool":
                result.append({
                    "role": "tool",
                    "content": msg.content,
                    "tool_call_id": getattr(msg, "tool_call_id", "")
                })
            elif msg.type == "system":
                result.append({"role": "system", "content": msg.content})
        elif isinstance(msg, dict):
            result.append(msg)
    return result


def generate_answer(state: KnowledgeAgentState, config=None) -> Dict[str, Any]:
    """
    Generate answer based on retrieved context using DashScope Generation.call()

    Features:
        - Uses DashScope Generation.call() directly (no LangChain LLM wrapper)
        - Supports tool calling (send_email, web_search, query_database)
        - Calculates confidence score
        - Extracts source citations
    """
    query = state["query"]
    reranked_chunks = state.get("merged_chunks") or []
    rag_config = state["config"]
    conversation_messages = state.get("messages", [])

    print(f"\n[Node 5: Generate] Generating answer with {len(reranked_chunks)} chunks "
          f"and {len(conversation_messages)} messages")

    # Model name: prefer runtime config, fall back to state config, then settings
    if config:
        model_name = config.get("configurable", {}).get("model") or rag_config.model
    else:
        model_name = rag_config.model or settings.default_model

    api_key = settings.dashscope_api_key

    try:
        # ── Build context from retrieved chunks ──────────────────────────────
        context_parts = []
        image_map: dict = {}  # placeholder → oss_url，用于图文模式

        # 判断是否图文模式
        collection = rag_config.collection or settings.adb_collection
        is_image_mode = False
        try:
            from app.db import get_collection_config_repository
            cfg = get_collection_config_repository().get_by_collection(settings.adb_namespace, collection)
            is_image_mode = bool(cfg and cfg.get("image_mode"))
        except Exception:
            pass

        # 图文模式：批量查询 chunk 关联图片
        chunk_image_map: dict = {}  # chunk_id → [image_record]
        if is_image_mode:
            try:
                from app.db import get_chunk_image_repository
                chunk_ids = []
                for chunk in reranked_chunks:
                    cid = (chunk.get("id") if isinstance(chunk, dict) else getattr(chunk, "chunk_id", None))
                    if cid:
                        chunk_ids.append(cid)
                if chunk_ids:
                    img_records = get_chunk_image_repository().get_by_chunk_ids(chunk_ids)
                    for r in img_records:
                        ph = r.get("placeholder", "")
                        ok = r.get("oss_key", "")
                        chunk_image_map.setdefault(r["chunk_id"], []).append(r)
                        if ok:
                            image_map[ph] = f"/api/v1/documents/image-proxy?oss_key={ok}"
                    print(f"[Generate] 图文模式: {len(img_records)} 条图片记录, image_map {len(image_map)} 条")
            except Exception as e:
                import traceback
                print(f"[Generate] 查询图片记录失败: {e}\n{traceback.format_exc()}")

        for i, chunk in enumerate(reranked_chunks, 1):
            if isinstance(chunk, dict):
                title = chunk.get("title") or chunk.get("metadata", {}).get("title", "未知标题")
                content = chunk.get("content", "")
                chunk_id = chunk.get("id", "")
            else:
                title = getattr(chunk, "title", None) or "未知标题"
                content = getattr(chunk, "content", "")
                chunk_id = getattr(chunk, "chunk_id", "")
            context_parts.append(f"[文档 {i}] {title}")
            context_parts.append(content)
            context_parts.append("")

        context_text = "\n".join(context_parts)

        # ── Detect greeting ──────────────────────────────────────────────────
        query_intent = state.get("query_intent", "general")
        is_greeting = query_intent == "general" and any(
            g in query.lower() for g in ["你好", "您好", "hello", "hi", "嗨"]
        )

        # ── System prompt ────────────────────────────────────────────────────
        if is_greeting:
            system_prompt = KNOWLEDGE_GENERATE_SYSTEM_GREETING
        elif is_image_mode:
            system_prompt = KNOWLEDGE_GENERATE_SYSTEM_IMAGE.format(context=context_text)
        else:
            system_prompt = KNOWLEDGE_GENERATE_SYSTEM.format(context=context_text)

        # ── Build messages list (plain dicts) ────────────────────────────────
        messages = [{"role": "system", "content": system_prompt}]

        # Conversation history (exclude last message = current query)
        history_dicts = _convert_messages_to_dicts(conversation_messages[:-1])
        messages.extend(history_dicts)

        # Current user query
        messages.append({"role": "user", "content": f"用户问题：{query}"})

        # ── MCP tools in DashScope format ────────────────────────────────────
        # tools disabled for now
        tools = None

        print(f"[Generate] model={model_name}")

        # ── First LLM call ───────────────────────────────────────────────────
        call_kwargs = dict(
            api_key=api_key,
            model=model_name,
            messages=messages,
            result_format="message",
        )

        response = Generation.call(**call_kwargs)

        if response.status_code != 200:
            raise RuntimeError(
                f"DashScope error {response.status_code}: {response.message}"
            )

        assistant_output = response.output.choices[0].message

        # ── Extract final answer (no tool loop) ──────────────────────────────
        answer = (
            assistant_output.get("content", "")
            if isinstance(assistant_output, dict)
            else getattr(assistant_output, "content", "")
        ) or ""

        tools_used = []

        # ── Sources：返回全部切片，前端负责文件名去重展示 ────────────────────
        sources = []
        for chunk in reranked_chunks:
            if isinstance(chunk, dict):
                file_name = chunk.get("file_name") or chunk.get("metadata", {}).get("file_name", "")
                title = chunk.get("title") or chunk.get("metadata", {}).get("title") or file_name or "未知来源"
                sources.append({
                    "id": chunk.get("id", ""),
                    "title": title,
                    "file_name": file_name,
                    "content": chunk.get("content", "")[:200],
                    "score": chunk.get("score", 0.0),
                    "metadata": chunk.get("metadata", {}),
                })
            else:
                file_name = getattr(chunk, "file_name", "") or ""
                title = getattr(chunk, "title", None) or getattr(chunk, "source", None) or file_name or "未知来源"
                sources.append({
                    "id": getattr(chunk, "chunk_id", ""),
                    "title": title,
                    "file_name": file_name,
                    "content": (getattr(chunk, "content", "") or "")[:200],
                    "score": getattr(chunk, "score", 0.0),
                    "metadata": getattr(chunk, "metadata", {}) or {},
                })

        # ── Confidence ───────────────────────────────────────────────────────
        if reranked_chunks:
            def _s(c):
                return (c.get("score", 0) if isinstance(c, dict) else getattr(c, "score", 0)) or 0
            avg_score = sum(_s(c) for c in reranked_chunks[:3]) / min(3, len(reranked_chunks))
            confidence = min(avg_score, 1.0)
        else:
            confidence = 0.5

        print(f"[Generate] Done. confidence={confidence:.2f}, tools_used={tools_used}")

        # ── Metrics ──────────────────────────────────────────────────────────
        metrics = state["metrics"]
        metrics.llm_calls += 1 + (1 if tools_used else 0)

        return {
            "answer": answer,
            "confidence": confidence,
            "sources": sources,
            "context": context_text,
            "tools_used": tools_used,
            "metrics": metrics,
            "image_map": image_map,
            "messages": [AIMessage(content=answer)],
            "processing_log": [{
                "stage": "generate",
                "timestamp": datetime.now().isoformat(),
                "model": model_name,
                "tools_used": tools_used,
                "confidence": confidence,
            }],
        }

    except Exception as e:
        import traceback
        print(f"[Generate] Error: {e}\n{traceback.format_exc()}")
        return {
            "answer": f"抱歉，生成答案时出现错误: {e}",
            "confidence": 0.0,
            "sources": [],
            "context": "",
            "tools_used": [],
            "all_errors": [f"Generation failed: {e}"],
        }
