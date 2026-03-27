# -*- coding: utf-8 -*-
"""文档管理 API"""
import logging
from typing import Optional
from fastapi import APIRouter, UploadFile, File, Form
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from app.services import document_service
from app.services.oss_service import get_oss_service
from app.core.config import settings
from app.core.exceptions import ExternalServiceError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    metadata: Optional[str] = Form(None),
    chunk_size: int = Form(800),
    chunk_overlap: int = Form(100),
    zh_title_enhance: bool = Form(True),
    vl_enhance: bool = Form(False),
    image_dpi: int = Form(150),
):
    """单文件上传切分，自动判断图文/标准模式"""
    result = await document_service.upload_document(
        file_name=file.filename,
        file_content=await file.read(),
        metadata_raw=metadata,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        zh_title_enhance=zh_title_enhance,
        vl_enhance=vl_enhance,
        image_dpi=image_dpi,
    )
    return JSONResponse(content={
        "success": True,
        "message": "上传任务已提交，请在文件列表查看进度，完成后获取切片",
        "data": result,
    })


@router.post("/upload-to-category")
async def upload_document_to_category(
    file: UploadFile = File(...),
    category_id: str = Form(...),
):
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
    """
    批量上传文件到 OSS 类目目录（支持多文件选择或整个文件夹上传）。
    前端使用 multipart/form-data，files 字段传多个文件即可。
    文件夹上传时前端需将 webkitRelativePath 作为文件名前缀传入（可选）。
    """
    file_pairs = [(f.filename, await f.read()) for f in files]
    result = await document_service.batch_upload_to_category(file_pairs, category_id)

    total = result["total"]
    ok = len(result["succeeded"])
    fail = len(result["failed"])
    return JSONResponse(content={
        "success": True,
        "message": f"上传完成：成功 {ok} 个，失败 {fail} 个，共 {total} 个",
        "data": result,
    })


@router.post("/start-chunking/{category_id}")
async def start_chunking(
    category_id: str,
    collection: str = settings.adb_collection,
    chunk_size: int = 800,
    chunk_overlap: int = 100,
    zh_title_enhance: bool = True,
    vl_enhance: bool = False,
    text_splitter_name: Optional[str] = None,
    image_dpi: int = 150,
):
    result = await document_service.start_chunking(
        category_id=category_id,
        collection=collection,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        zh_title_enhance=zh_title_enhance,
        vl_enhance=vl_enhance,
        text_splitter_name=text_splitter_name,
        image_dpi=image_dpi,
    )
    return JSONResponse(content={
        "success": True,
        "message": f"已提交 {result['submitted']} 个，跳过 {len(result['skipped'])} 个",
        "data": result,
    })


@router.post("/start-chunking-direct/{category_id}")
async def start_chunking_direct(
    category_id: str,
    collection: str = settings.adb_collection,
    chunk_size: int = 800,
    chunk_overlap: int = 100,
    zh_title_enhance: bool = True,
    vl_enhance: bool = False,
    text_splitter_name: Optional[str] = None,
):
    """直接切分并入库（dry_run=False），不支持 image_mode collection。"""
    result = await document_service.start_chunking_direct(
        category_id=category_id,
        collection=collection,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        zh_title_enhance=zh_title_enhance,
        vl_enhance=vl_enhance,
        text_splitter_name=text_splitter_name,
    )
    return JSONResponse(content={
        "success": True,
        "message": f"已直接入库 {result['submitted']} 个，跳过 {len(result['skipped'])} 个",
        "data": result,
    })


@router.get("/list")
async def list_documents():
    return JSONResponse(content={"success": True, "data": document_service.list_documents()})


@router.get("/detail/{file_name}")
async def get_document_detail(file_name: str):
    return JSONResponse(content={"success": True, "data": document_service.get_document_detail(file_name)})


@router.delete("/delete/{file_name}")
async def delete_document(file_name: str):
    document_service.delete_document(file_name)
    return JSONResponse(content={"success": True, "message": "文档删除成功"})


class SearchRequest(BaseModel):
    query: str
    top_k: int = 10
    filter: Optional[str] = None
    hybrid_search: Optional[str] = "Weight"
    hybrid_alpha: float = 0.5
    rerank_factor: Optional[float] = None
    include_file_url: bool = False
    collection: Optional[str] = None


@router.post("/search")
async def search_documents(body: SearchRequest):
    results = document_service.search_documents(
        query=body.query,
        top_k=body.top_k,
        filter_str=body.filter or None,
        hybrid_search=body.hybrid_search,
        hybrid_alpha=body.hybrid_alpha,
        rerank_factor=body.rerank_factor,
        include_file_url=body.include_file_url,
        collection=body.collection,
    )
    return JSONResponse(content={
        "success": True,
        "data": {"query": body.query, "results": results, "total": len(results)},
    })


@router.get("/image-proxy")
async def image_proxy(oss_key: str):
    """代理返回 OSS 私有图片，供浏览器直接展示"""
    data = get_oss_service().get_object_bytes(oss_key)
    ext = oss_key.rsplit(".", 1)[-1].lower() if "." in oss_key else "png"
    content_type = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                    "gif": "image/gif", "webp": "image/webp"}.get(ext, "image/png")
    return Response(content=data, media_type=content_type)
