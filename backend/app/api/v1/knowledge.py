# -*- coding: utf-8 -*-
"""Knowledge API Routes"""
from fastapi import APIRouter
from app.core.config import settings
from app.models.requests import KnowledgeRequest
from app.models.responses import KnowledgeResponse
from app.services.knowledge_service import invoke_knowledge_qa

router = APIRouter(prefix="/knowledge")


@router.post("/", response_model=KnowledgeResponse, summary="Knowledge Base Q&A")
async def knowledge_qa(request: KnowledgeRequest):
    """RAG 问答，完整流水线：改写→分类→检索→过滤→重排→生成→质量检查"""
    model_name = request.model or settings.default_model
    result = await invoke_knowledge_qa(
        query=request.query,
        model_name=model_name,
        session_id=request.session_id,
        collection=request.collection or None,
        force_multi_doc=request.force_multi_doc,
        keyword_filter=request.keyword_filter or None,
    )
    return KnowledgeResponse(
        status_code=200,
        request_id=result["request_id"],
        session_id=result["session_id"],
        answer=result["answer"],
        confidence=result["confidence"],
        sources=result["sources"],
        model=result["model"],
        finish_reason="stop",
        thoughts=result["thoughts"],
        image_map=result["image_map"],
    )
