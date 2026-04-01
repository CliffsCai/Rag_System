# -*- coding: utf-8 -*-
"""对话会话 API"""
from typing import Optional
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.services import conversation_service

router = APIRouter(prefix="/conversations", tags=["conversations"])


class CreateSessionRequest(BaseModel):
    kb_name: str
    title: str = "新会话"
    user_id: str = "default"


@router.get("")
async def list_sessions(
    kb_name: str = Query(...),
    user_id: str = Query(default="default"),
):
    result = conversation_service.list_sessions(kb_name=kb_name, user_id=user_id)
    return JSONResponse(content={"success": True, "data": result})


@router.post("")
async def create_session(body: CreateSessionRequest):
    session = conversation_service.create_session(
        kb_name=body.kb_name, user_id=body.user_id, title=body.title
    )
    return JSONResponse(content={"success": True, "data": session})


@router.get("/{session_id}/messages")
async def get_messages(session_id: str, limit: int = Query(default=100, ge=1, le=500)):
    result = conversation_service.get_session_messages(session_id, limit=limit)
    return JSONResponse(content={"success": True, "data": result})


@router.delete("/{session_id}")
async def delete_session(session_id: str):
    conversation_service.delete_session(session_id)
    return JSONResponse(content={"success": True, "message": "会话已删除"})
