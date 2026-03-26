# -*- coding: utf-8 -*-
"""
Chat 业务逻辑（Supervisor Agent 调用封装）
"""
import uuid
import logging
from typing import Optional

from langchain_core.messages import HumanMessage

from app.core.config import settings, SUPPORTED_MODELS
from app.core.exceptions import ValidationError, ExternalServiceError

logger = logging.getLogger(__name__)


def invoke_chat(
    messages: list,
    model_name: str,
    session_id: str,
    temperature: float = 0.7,
) -> dict:
    """
    调用 Supervisor Agent，返回结构化结果。
    messages: [{"role": "user"|"assistant", "content": str}]
    thread_id 基于 session_id 隔离，每个会话独立记忆。
    """
    if model_name not in SUPPORTED_MODELS:
        raise ValidationError(f"Model '{model_name}' not supported. Available: {list(SUPPORTED_MODELS.keys())}")

    if not messages:
        raise ValidationError("No messages provided")

    latest = messages[-1]
    if latest["role"] != "user":
        raise ValidationError("Latest message must be from user")

    from agents.supervisor import get_supervisor_agent
    agent = get_supervisor_agent()

    request_id = str(uuid.uuid4())
    # thread_id 基于 session_id，保证每个会话独立的对话记忆
    thread_id = f"chat_{session_id}"

    config = {
        "configurable": {
            "model": model_name,
            "session_id": session_id,
            "thread_id": thread_id,
            "temperature": temperature,
        }
    }

    logger.info("处理 chat 请求", extra={"session_id": session_id, "request_id": request_id})

    try:
        result = agent.invoke({"messages": [HumanMessage(content=latest["content"])]}, config=config)
    except Exception as e:
        raise ExternalServiceError(f"Supervisor Agent 调用失败: {e}") from e

    result_messages = result.get("messages", [])

    last_ai = next(
        (m for m in reversed(result_messages) if hasattr(m, "type") and m.type == "ai"),
        None,
    )
    response_content = last_ai.content if last_ai else "抱歉，我没有理解您的问题。"

    tools_used = []
    for msg in result_messages:
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            for tc in msg.tool_calls:
                name = tc.get("name", "unknown")
                if name not in tools_used:
                    tools_used.append(name)

    conversation_turns = len(
        [m for m in result_messages if hasattr(m, "type") and m.type in ("human", "ai")]
    )

    return {
        "request_id": request_id,
        "session_id": session_id,
        "messages": [{"role": "assistant", "content": response_content}],
        "model": model_name,
        "tools_used": tools_used,
        "thoughts": {
            "mode": "supervisor_chat",
            "agent_type": "supervisor_with_sub_agents",
            "conversation_turns": conversation_turns,
            "specialized_agents_available": ["email_agent", "search_agent"],
            "tools_called": tools_used,
        },
        "usage": {
            "tools_used": tools_used,
            "models": [{"model_id": model_name, "input_tokens": 0, "output_tokens": 0}],
        },
    }
