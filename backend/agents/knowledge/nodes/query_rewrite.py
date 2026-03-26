# -*- coding: utf-8 -*-
"""
Query Rewrite Node - 增强改写用户提问
"""

import logging
from datetime import datetime

from dashscope import Generation

from ..state import KnowledgeAgentState
from app.core.config import settings
from app.core.prompts import KNOWLEDGE_QUERY_REWRITE_SYSTEM

logger = logging.getLogger(__name__)


def query_rewrite(state: KnowledgeAgentState) -> dict:
    start_time = datetime.now()

    try:
        original_query = state["original_query"]
        logger.info(f"[QueryRewrite] 开始改写问题: {original_query}")

        messages = [
            {
                "role": "system",
                "content": KNOWLEDGE_QUERY_REWRITE_SYSTEM,
            },
            {"role": "user", "content": f"原始问题: {original_query}\n\n改写后的问题:"},
        ]

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
        logger.info(f"[QueryRewrite] 完成 ({duration:.0f}ms) 原始: {original_query} → 改写: {rewritten_query}")

        return {
            "query": rewritten_query,
            "rewritten_query": rewritten_query,
            "processing_log": [{
                "stage": "query_rewrite",
                "duration_ms": duration,
                "original": original_query,
                "rewritten": rewritten_query,
            }],
        }

    except Exception as e:
        logger.error(f"[QueryRewrite] 改写失败: {e}", exc_info=True)
        return {
            "query": state["original_query"],
            "rewritten_query": state["original_query"],
            "all_warnings": [f"问题改写失败，使用原始问题: {e}"],
        }
