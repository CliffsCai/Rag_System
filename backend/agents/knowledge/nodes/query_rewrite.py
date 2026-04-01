# -*- coding: utf-8 -*-
"""
Query Rewrite Node - 增强改写用户提问，支持多轮对话指代消解
"""

import logging
from datetime import datetime

from dashscope import Generation

from ..state import KnowledgeAgentState
from app.core.config import settings
from app.core.prompts import KNOWLEDGE_QUERY_REWRITE_SYSTEM, KNOWLEDGE_QUERY_REWRITE_WITH_HISTORY_SYSTEM

logger = logging.getLogger(__name__)

# 带入历史的最大轮数（太长会干扰改写，取最近 3 轮即可）
_MAX_HISTORY_TURNS = 3


def query_rewrite(state: KnowledgeAgentState) -> dict:
    start_time = datetime.now()

    try:
        original_query = state["original_query"]
        conversation_messages = state.get("messages", [])

        # messages[-1] 是当前 query（HumanMessage），历史是 [:-1]
        history = conversation_messages[:-1] if len(conversation_messages) > 1 else []

        # 取最近 N 轮（每轮 = 1 human + 1 ai），截取尾部
        recent_history = history[-(2 * _MAX_HISTORY_TURNS):]

        if recent_history:
            # 有历史：用指代消解版 prompt，把历史拼入 messages
            system_prompt = KNOWLEDGE_QUERY_REWRITE_WITH_HISTORY_SYSTEM
            messages = [{"role": "system", "content": system_prompt}]
            for msg in recent_history:
                if hasattr(msg, "type"):
                    if msg.type == "human":
                        messages.append({"role": "user", "content": msg.content})
                    elif msg.type == "ai":
                        messages.append({"role": "assistant", "content": msg.content or ""})
                elif isinstance(msg, dict):
                    messages.append(msg)
            messages.append({"role": "user", "content": f"当前问题：{original_query}\n\n改写后的问题："})
            logger.info(f"[QueryRewrite] 带 {len(recent_history)} 条历史改写: {original_query}")
        else:
            # 无历史：用简单版 prompt
            system_prompt = KNOWLEDGE_QUERY_REWRITE_SYSTEM
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"原始问题: {original_query}\n\n改写后的问题:"},
            ]
            logger.info(f"[QueryRewrite] 无历史改写: {original_query}")

        response = Generation.call(
            api_key=settings.dashscope_api_key,
            model=state["config"].model,
            messages=messages,
            result_format="message",
        )

        if response.status_code == 200:
            rewritten_query = response.output.choices[0].message.get("content", "").strip()
        else:
            logger.warning(f"[QueryRewrite] DashScope error {response.status_code}, 使用原始query")
            rewritten_query = ""

        if not rewritten_query or len(rewritten_query) < 2:
            rewritten_query = original_query

        duration = (datetime.now() - start_time).total_seconds() * 1000
        logger.info(f"[QueryRewrite] 完成 ({duration:.0f}ms): {original_query} → {rewritten_query}")

        return {
            "query": rewritten_query,
            "rewritten_query": rewritten_query,
            "processing_log": [{
                "stage": "query_rewrite",
                "duration_ms": duration,
                "original": original_query,
                "rewritten": rewritten_query,
                "history_turns": len(recent_history) // 2,
            }],
        }

    except Exception as e:
        logger.error(f"[QueryRewrite] 改写失败: {e}", exc_info=True)
        return {
            "query": state["original_query"],
            "rewritten_query": state["original_query"],
            "all_warnings": [f"问题改写失败，使用原始问题: {e}"],
        }
