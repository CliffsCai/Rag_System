# -*- coding: utf-8 -*-
"""
千问 OpenAI 兼容 Chat Completions 流式（北京 regional compatible-mode/v1）
与 DashScope messages 结构互转；供 knowledge SSE 使用。
"""
from typing import Any, AsyncIterator, Dict, List

import httpx
from openai import AsyncOpenAI

from app.core.config import settings


def dashscope_style_messages_to_openai(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """将 generate 节点中的 messages（含 DashScope 多模态 list）转为 OpenAI Chat 格式。"""
    out: List[Dict[str, Any]] = []
    for m in messages:
        role = m["role"]
        content = m.get("content")
        if role == "user" and isinstance(content, list):
            parts = []
            for part in content:
                if not isinstance(part, dict):
                    continue
                if "image" in part:
                    parts.append({"type": "image_url", "image_url": {"url": part["image"]}})
                if "text" in part:
                    parts.append({"type": "text", "text": part["text"]})
            out.append({"role": "user", "content": parts})
        else:
            out.append({"role": role, "content": content if isinstance(content, str) else str(content)})
    return out


async def iter_openai_text_deltas(
    messages: List[Dict[str, Any]],
    model: str,
) -> AsyncIterator[str]:
    """
    异步迭代模型输出的文本 delta（content 片段）。
    忽略仅含 usage 的空 choices chunk。
    """
    client = AsyncOpenAI(
        api_key=settings.dashscope_api_key,
        base_url=settings.dashscope_base_url,
        http_client=httpx.AsyncClient(verify=settings.ssl_verify),
    )
    oa_messages = dashscope_style_messages_to_openai(messages)
    stream = await client.chat.completions.create(
        model=model,
        messages=oa_messages,
        stream=True,
        stream_options={"include_usage": True},
    )
    async for chunk in stream:
        ch0 = chunk.choices[0] if chunk.choices else None
        if not ch0 or not ch0.delta:
            continue
        piece = ch0.delta.content
        if piece:
            yield piece
