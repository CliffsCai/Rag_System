# -*- coding: utf-8 -*-
"""
Request Models
Pydantic models for API request validation
"""

from pydantic import BaseModel
from typing import List, Dict, Any, Optional


class Message(BaseModel):
    """Chat message model"""
    role: str
    content: str


class ChatRequest(BaseModel):
    """Chat endpoint request model"""
    messages: List[Message]
    session_id: Optional[str] = None  # 会话标识符
    model: Optional[str] = None
    temperature: Optional[float] = None


class KnowledgeRequest(BaseModel):
    """Knowledge base request model"""
    query: str
    session_id: str = "default"
    model: Optional[str] = None
    collection: Optional[str] = None          # 指定知识库，不传则用默认
    force_multi_doc: Optional[bool] = None    # True=强制多文档，None=LLM 判断
    keyword_filter: Optional[str] = None      # 有值=强制 KEYWORD_ONLY + TEXT_MATCH 预过滤