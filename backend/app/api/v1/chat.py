# -*- coding: utf-8 -*-
"""Chat API Routes"""
from fastapi import APIRouter
from app.core.config import settings
from app.models.requests import ChatRequest
from app.models.responses import ChatResponse
from app.services.chat_service import invoke_chat

router = APIRouter()


@router.post("/", response_model=ChatResponse, summary="Chat with Supervisor Agent")
async def chat(request: ChatRequest):
    """与 Supervisor Agent 对话（多 Agent 系统，含会话级对话记忆）"""
    model_name = request.model or settings.default_model
    result = invoke_chat(
        messages=[{"role": m.role, "content": m.content} for m in request.messages],
        model_name=model_name,
        session_id=request.session_id or "default_session",
        temperature=request.temperature if request.temperature is not None else 0.7,
    )
    return ChatResponse(
        status_code=200,
        request_id=result["request_id"],
        session_id=result["session_id"],
        messages=result["messages"],
        model=result["model"],
        finish_reason="stop",
        usage=result["usage"],
        thoughts=result["thoughts"],
    )
