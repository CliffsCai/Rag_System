# -*- coding: utf-8 -*-
"""Knowledge API Routes"""
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from app.core.config import settings
from app.models.requests import KnowledgeRequest
from app.models.responses import KnowledgeResponse
from app.services.knowledge_service import invoke_knowledge_qa, stream_knowledge_qa_sse

router = APIRouter(prefix="/knowledge")


@router.post("/", response_model=KnowledgeResponse, summary="Knowledge Base Q&A")
async def knowledge_qa(request: KnowledgeRequest):
    """RAG 问答，完整流水线：改写→分类→检索→过滤→重排→生成→质量检查"""
    model_name = request.model or settings.default_model

    # 多模态：用户图片 base64 → 上传 OSS → 生成预签名 URL
    query_image_url = None
    query_image_oss_key = None
    if request.query_image:
        try:
            import base64, uuid
            from app.services.oss_service import get_oss_service
            img_bytes = base64.b64decode(request.query_image)
            img_uuid = uuid.uuid4().hex[:12]
            # 路径：query_images/{user_id}/{kb_name}/{session_id}/{uuid}.jpg
            kb_name = request.collection or "default"
            oss_path = f"query_images/default/{kb_name}/{request.session_id}"
            query_image_oss_key = get_oss_service().upload_file(
                oss_path, f"{img_uuid}.jpg", img_bytes
            )
            query_image_url = get_oss_service().get_presigned_url(query_image_oss_key, expires=600)
        except Exception as e:
            import logging as _log
            _log.getLogger(__name__).warning(f"用户查询图片上传失败，降级为纯文字检索: {e}")

    result = await invoke_knowledge_qa(
        query=request.query,
        model_name=model_name,
        session_id=request.session_id,
        collection=request.collection or None,
        force_multi_doc=request.force_multi_doc,
        keyword_filter=request.keyword_filter or None,
        query_image_url=query_image_url,
        query_image_oss_key=query_image_oss_key,
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


@router.post("/stream", summary="Knowledge Base Q&A (SSE stream)")
async def knowledge_qa_stream(request: KnowledgeRequest):
    """RAG 问答流式输出：event meta / delta / done / error，生成阶段为 OpenAI 兼容 Chat Completions stream。"""
    model_name = request.model or settings.default_model

    query_image_url = None
    query_image_oss_key = None
    if request.query_image:
        try:
            import base64
            import uuid as _uuid
            from app.services.oss_service import get_oss_service
            img_bytes = base64.b64decode(request.query_image)
            img_uuid = _uuid.uuid4().hex[:12]
            kb_name = request.collection or "default"
            oss_path = f"query_images/default/{kb_name}/{request.session_id}"
            query_image_oss_key = get_oss_service().upload_file(
                oss_path, f"{img_uuid}.jpg", img_bytes
            )
            query_image_url = get_oss_service().get_presigned_url(query_image_oss_key, expires=600)
        except Exception as e:
            import logging as _log
            _log.getLogger(__name__).warning(f"用户查询图片上传失败，降级为纯文字检索: {e}")

    async def event_gen():
        async for chunk in stream_knowledge_qa_sse(
            query=request.query,
            model_name=model_name,
            session_id=request.session_id,
            collection=request.collection or None,
            force_multi_doc=request.force_multi_doc,
            keyword_filter=request.keyword_filter or None,
            query_image_url=query_image_url,
            query_image_oss_key=query_image_oss_key,
        ):
            yield chunk

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
