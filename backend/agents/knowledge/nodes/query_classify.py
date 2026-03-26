# -*- coding: utf-8 -*-
"""
Query Classify Node - 问题分类
判断问题是单文档查询还是多文档查询
"""

import logging
from datetime import datetime

from dashscope import Generation

from ..state import KnowledgeAgentState
from app.core.config import settings
from app.core.prompts import KNOWLEDGE_QUERY_CLASSIFY_SYSTEM

logger = logging.getLogger(__name__)


def query_classify(state: KnowledgeAgentState) -> dict:
    start_time = datetime.now()

    try:
        query = state["query"]
        logger.info(f"[QueryClassify] 开始分类问题: {query}")

        messages = [
            {
                "role": "system",
                "content": KNOWLEDGE_QUERY_CLASSIFY_SYSTEM,
            },
            {"role": "user", "content": f"问题: {query}\n\n分类结果:"},
        ]

        response = Generation.call(
            api_key=settings.dashscope_api_key,
            model=state["config"].model,
            messages=messages,
            result_format="message",
        )

        if response.status_code == 200:
            classification = response.output.choices[0].message.get("content", "").strip().lower()
        else:
            logger.warning(f"[QueryClassify] DashScope error {response.status_code}, 默认 multi_doc")
            classification = ""

        if "single" in classification:
            query_type = "single_doc"
        elif "multi" in classification:
            query_type = "multi_doc"
        else:
            logger.warning(f"[QueryClassify] 无法识别分类结果: '{classification}', 默认 multi_doc")
            query_type = "multi_doc"

        duration = (datetime.now() - start_time).total_seconds() * 1000
        logger.info(f"[QueryClassify] 分类完成 ({duration:.0f}ms): {query_type}")

        return {
            "query_type": query_type,
            "processing_log": [{
                "stage": "query_classify",
                "duration_ms": duration,
                "query_type": query_type,
            }],
        }

    except Exception as e:
        logger.error(f"[QueryClassify] 分类失败: {e}", exc_info=True)
        return {
            "query_type": "multi_doc",
            "all_warnings": [f"问题分类失败，默认多文档查询: {e}"],
        }
