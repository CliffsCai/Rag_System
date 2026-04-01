# -*- coding: utf-8 -*-
"""切片操作 API"""
from typing import Optional
from fastapi import APIRouter, Form, UploadFile, File
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.services import chunk_service

router = APIRouter(prefix="/chunks", tags=["chunks"])


# ── 查询 ──────────────────────────────────────────────────────────────────────

@router.get("/job/{job_id}")
async def get_chunks_by_job(job_id: str):
    return JSONResponse(content={"success": True, "data": chunk_service.get_chunks_by_job(job_id)})


# ── 单切片操作 ────────────────────────────────────────────────────────────────

class EditChunkBody(BaseModel):
    content: str


@router.put("/job/{job_id}/chunk/{chunk_index}")
async def edit_chunk(job_id: str, chunk_index: int, body: EditChunkBody):
    chunk_service.edit_chunk(job_id, chunk_index, body.content)
    return JSONResponse(content={"success": True, "message": "切片已更新"})


@router.post("/job/{job_id}/chunk/{chunk_index}/clean")
async def clean_single_chunk(job_id: str, chunk_index: int, instruction: Optional[str] = Form(None)):
    cleaned = chunk_service.clean_single_chunk(job_id, chunk_index, instruction)
    return JSONResponse(content={"success": True, "message": "清洗完成", "data": {"content": cleaned}})


@router.post("/job/{job_id}/chunk/{chunk_index}/revert")
async def revert_single_chunk(job_id: str, chunk_index: int):
    chunk_service.revert_single_chunk(job_id, chunk_index)
    return JSONResponse(content={"success": True, "message": "已恢复原始内容"})


# ── 批量操作（按 job）────────────────────────────────────────────────────────

class BatchCleanBody(BaseModel):
    instruction: Optional[str] = None


@router.post("/job/{job_id}/clean")
async def clean_job_chunks(job_id: str, body: BatchCleanBody = BatchCleanBody()):
    result = await chunk_service.clean_job_chunks(job_id, body.instruction)
    return JSONResponse(content={
        "success": True,
        "message": f"清洗完成，成功 {result['success']}/{result['total']} 个",
        "data": result,
    })


@router.post("/job/{job_id}/revert")
async def revert_job_chunks(job_id: str):
    chunk_service.revert_job_chunks(job_id)
    return JSONResponse(content={"success": True, "message": "已恢复该 job 所有切片到原始内容"})


# ── 全局批量操作 ──────────────────────────────────────────────────────────────

@router.post("/clean-all")
async def clean_all_chunks(body: BatchCleanBody = BatchCleanBody()):
    result = await chunk_service.clean_all_chunks(body.instruction)
    return JSONResponse(content={
        "success": True,
        "message": f"全量清洗完成，成功 {result['success']}，失败 {result['failed']}",
        "data": result,
    })


@router.post("/revert-all")
async def revert_all_chunks():
    chunk_service.revert_all_chunks()
    return JSONResponse(content={"success": True, "message": "已恢复所有切片到原始内容"})


# ── 向量库上传 ────────────────────────────────────────────────────────────────

@router.post("/job/{job_id}/upsert")
async def upsert_job_chunks(job_id: str):
    result = await chunk_service.upsert_job_chunks(job_id)
    return JSONResponse(content={"success": True, "message": "上传成功", "data": result})


class BatchUpsertRequest(BaseModel):
    job_ids: list[str]


@router.post("/batch-upsert")
async def batch_upsert_jobs(body: BatchUpsertRequest):
    result = await chunk_service.batch_upsert_jobs(body.job_ids)
    ok = len(result["succeeded"])
    fail = len(result["failed"])
    return JSONResponse(content={
        "success": True,
        "message": f"上传完成：成功 {ok} 个，失败 {fail} 个",
        "data": result,
    })


# ── 图片管理 ──────────────────────────────────────────────────────────────────

@router.get("/job/{job_id}/chunk/{chunk_index}/images")
async def get_chunk_images(job_id: str, chunk_index: int):
    images = chunk_service.get_chunk_images(job_id, chunk_index)
    return JSONResponse(content={"success": True, "data": {"images": images}})


@router.post("/job/{job_id}/chunk/{chunk_index}/images")
async def add_chunk_image(
    job_id: str,
    chunk_index: int,
    file: UploadFile = File(...),
    page: Optional[int] = Form(None),
    insert_position: int = Form(0),
):
    record = chunk_service.add_chunk_image(
        job_id=job_id,
        chunk_index=chunk_index,
        file_content=await file.read(),
        filename=file.filename,
        insert_position=insert_position,
        page=page,
    )
    return JSONResponse(content={"success": True, "data": record})


@router.delete("/job/{job_id}/chunk/{chunk_index}/images/{image_id}")
async def delete_chunk_image(job_id: str, chunk_index: int, image_id: str):
    chunk_service.delete_chunk_image(job_id, chunk_index, image_id)
    return JSONResponse(content={"success": True, "message": "图片已删除"})


# ── 占位符解析 ────────────────────────────────────────────────────────────────

class ResolveImagesRequest(BaseModel):
    placeholders: list[str]


@router.post("/resolve-images")
async def resolve_images(body: ResolveImagesRequest):
    """批量将占位符解析为预签名 URL，用于历史对话图片展示"""
    result = chunk_service.resolve_image_placeholders(body.placeholders)
    return JSONResponse(content={"success": True, "data": result})
