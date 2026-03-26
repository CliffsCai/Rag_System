# -*- coding: utf-8 -*-
"""
Response Models
Pydantic models for API response formatting
"""

from pydantic import BaseModel
from typing import List, Dict, Any, Optional


class ChatResponse(BaseModel):
    """Chat endpoint response model (compatible with Bailian Agent)"""
    # 基础响应
    status_code: int = 200
    request_id: str
    session_id: str
    
    # 对话内容
    messages: List[Dict[str, Any]]
    model: str
    
    # 完成信息
    finish_reason: Optional[str] = "stop"  # stop, length, null
    
    # 使用统计
    usage: Optional[Dict[str, Any]] = None
    
    # 思考过程（调试用）
    thoughts: Optional[Dict[str, Any]] = None
    
    # 错误信息
    code: Optional[str] = None
    message: Optional[str] = None


class KnowledgeResponse(BaseModel):
    """Knowledge endpoint response model (compatible with Bailian Agent)"""
    # 基础响应
    status_code: int = 200
    request_id: str
    session_id: str
    
    # 回答内容
    answer: str
    confidence: float
    sources: List[Dict[str, Any]]
    model: str
    
    # 完成信息
    finish_reason: Optional[str] = "stop"
    
    # 思考过程
    thoughts: Optional[Dict[str, Any]] = None

    # 图文模式：占位符 → OSS URL 映射
    image_map: Optional[Dict[str, str]] = None

    # 错误信息
    code: Optional[str] = None
    message: Optional[str] = None
    error: Optional[str] = None  # 保留兼容性


class ModelInfo(BaseModel):
    """Model information model"""
    name: str
    description: str
    provider: str
    max_tokens: int


class ModelsResponse(BaseModel):
    """Models list response model"""
    models: List[ModelInfo]
    default_model: str


class HealthResponse(BaseModel):
    """Health check response model"""
    status: str
    api_key_configured: bool
    default_model: str
    ssl_verify: bool