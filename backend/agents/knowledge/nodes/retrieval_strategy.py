# -*- coding: utf-8 -*-
"""
Retrieval Strategy Node - 判断检索策略
"""

import logging
import re
from datetime import datetime

from ..state import KnowledgeAgentState, RetrievalStrategy

logger = logging.getLogger(__name__)


def determine_retrieval_strategy(state: KnowledgeAgentState) -> dict:
    start_time = datetime.now()

    try:
        query = state["query"]
        logger.info(f"[RetrievalStrategy] 开始判断检索策略: {query}")

        error_patterns = [
            r'error\s*:\s*\w+', r'exception\s*:\s*\w+', r'\d{3,4}\s*error',
            r'错误代码[:：]\s*\w+', r'报错[:：]', r'traceback', r'stack\s*trace',
        ]
        code_patterns = [
            r'`[^`]+`', r'```[\s\S]+```',
            r'^\s*[\w\-]+\s+[\w\-]+', r'[a-zA-Z_]\w*\([^\)]*\)',
        ]
        exact_keywords = ['精确', '完全匹配', '一模一样', '原文', '原话', 'exact', 'exactly', 'verbatim']

        has_error_code = any(re.search(p, query, re.IGNORECASE) for p in error_patterns)
        has_code = any(re.search(p, query) for p in code_patterns)
        has_exact = any(k in query.lower() for k in exact_keywords)

        if has_error_code or has_code or has_exact:
            strategy = RetrievalStrategy.KEYWORD_ONLY
            reasons = []
            if has_error_code: reasons.append("包含错误代码")
            if has_code:       reasons.append("包含代码片段")
            if has_exact:      reasons.append("要求精确匹配")
            reason_str = ", ".join(reasons)
        else:
            strategy = RetrievalStrategy.HYBRID
            reason_str = "常规查询，使用混合检索"

        duration = (datetime.now() - start_time).total_seconds() * 1000
        logger.info(f"[RetrievalStrategy] 策略: {strategy.value} ({duration:.0f}ms) 原因: {reason_str}")

        return {
            "retrieval_strategy": strategy,
            "retrieval_strategy_reason": reason_str,
            "processing_log": [{
                "stage": "retrieval_strategy",
                "duration_ms": duration,
                "strategy": strategy.value,
                "reason": reason_str,
            }],
        }

    except Exception as e:
        logger.error(f"[RetrievalStrategy] 策略判断失败: {e}", exc_info=True)
        return {
            "retrieval_strategy": RetrievalStrategy.HYBRID,
            "retrieval_strategy_reason": "策略判断失败，默认混合检索",
            "all_warnings": [f"检索策略判断失败: {e}"],
        }
