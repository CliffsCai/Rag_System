# -*- coding: utf-8 -*-
"""文档管理 API"""
import logging
from typing import Optional
from fastapi import APIRouter, BackgroundTasks, UploadFile, File, Form, Query
from fastapi.responses import JSONResponse, Response

from app.services import document_service
from app.services.oss_service import get_oss_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/upload")
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    kb_name: str = Form(...),
    chunk_size: int = Form(500),
    chunk_overlap: int = Form(50),
    image_dpi: int = Form(150),
    sync_graph: bool = Form(False, description="是否同步到知识图谱"),
):
    """单文件上传到知识库，后台异步切分+向量化，可选同步到知识图谱"""
    result = await document_service.upload_document(
        file_name=file.filename,
        file_content=await file.read(),
        kb_name=kb_name,
        background_tasks=background_tasks,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        image_dpi=image_dpi,
        sync_graph=sync_graph,
    )
    return JSONResponse(content={
        "success": True,
        "message": "上传任务已提交，后台正在处理，请通过 job_id 查询进度",
        "data": result,
    })


@router.post("/upload-to-category")
async def upload_document_to_category(
    file: UploadFile = File(...),
    category_id: str = Form(...),
):
    """上传文件到类目（OSS），不触发切分"""
    record = document_service.upload_to_category(
        file_name=file.filename,
        file_content=await file.read(),
        category_id=category_id,
    )
    return JSONResponse(content={
        "success": True,
        "message": "文件已上传到 OSS，可在类目页面点击「开始切分」",
        "data": record,
    })


@router.post("/batch-upload-to-category")
async def batch_upload_to_category(
    files: list[UploadFile] = File(...),
    category_id: str = Form(...),
):
    """批量上传文件到类目"""
    file_pairs = [(f.filename, await f.read()) for f in files]
    result = await document_service.batch_upload_to_category(file_pairs, category_id)
    ok = len(result["succeeded"])
    fail = len(result["failed"])
    return JSONResponse(content={
        "success": True,
        "message": f"上传完成：成功 {ok} 个，失败 {fail} 个，共 {result['total']} 个",
        "data": result,
    })


@router.post("/start-chunking/{category_id}")
async def start_chunking(
    category_id: str,
    background_tasks: BackgroundTasks,
    kb_name: str = Query(..., description="目标知识库名称"),
    chunk_size: int = Query(500),
    chunk_overlap: int = Query(50),
    image_dpi: int = Query(150),
    sync_graph: bool = Query(False, description="是否同步到知识图谱"),
    excel_rows_per_chunk: int = Query(50, description="Excel 每个切片的数据行数"),
):
    """将类目下所有文件提交到知识库切分流水线"""
    result = await document_service.start_chunking(
        category_id=category_id,
        kb_name=kb_name,
        background_tasks=background_tasks,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        image_dpi=image_dpi,
        sync_graph=sync_graph,
        excel_rows_per_chunk=excel_rows_per_chunk,
    )
    return JSONResponse(content={
        "success": True,
        "message": f"已提交 {result['submitted']} 个文件，后台处理中",
        "data": result,
    })


@router.post("/search")
async def search_documents(
    query: str = Form(...),
    kb_name: str = Form(None),
    collection: str = Form(None),
    top_k: int = Form(10),
    filter_expr: Optional[str] = Form(None),
    hybrid_search: Optional[str] = Form(None),
    hybrid_alpha: float = Form(0.5),
    keyword_filter: Optional[str] = Form(None),
):
    kb = kb_name or collection
    if not kb:
        return JSONResponse(status_code=422, content={"detail": "kb_name 或 collection 必须提供"})
    results = document_service.search_documents(
        query=query,
        kb_name=kb,
        top_k=top_k,
        filter_expr=filter_expr or None,
        ranker=hybrid_search or "RRF",
        hybrid_alpha=hybrid_alpha,
        keyword_filter=keyword_filter or None,
    )
    return JSONResponse(content={
        "success": True,
        "data": {"query": query, "results": results, "total": len(results)},
    })


@router.get("/image-proxy")
async def image_proxy(oss_key: str):
    """代理返回 OSS 私有图片"""
    data = get_oss_service().get_object_bytes(oss_key)
    ext = oss_key.rsplit(".", 1)[-1].lower() if "." in oss_key else "png"
    content_type = {
        "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
        "gif": "image/gif", "webp": "image/webp",
    }.get(ext, "image/png")
    return Response(content=data, media_type=content_type)
