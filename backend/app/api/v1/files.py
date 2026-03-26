# -*- coding: utf-8 -*-
"""文件列表 API"""
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.services import file_service

router = APIRouter(prefix="/files", tags=["files"])


class DeleteFileRequest(BaseModel):
    job_id: str
    collection: str


class BatchDeleteFilesRequest(BaseModel):
    job_ids: list[str]
    collection: str


@router.get("")
async def list_files(
    limit: int = Query(default=200, ge=1, le=2000),
    collection: str = Query(default="", description="按知识库过滤，不传则返回全部"),
):
    result = file_service.list_files(limit=limit, collection=collection or None)
    return JSONResponse(content={"success": True, "data": result})


@router.delete("")
async def delete_file(req: DeleteFileRequest):
    file_name = file_service.delete_file(req.job_id, req.collection)
    return JSONResponse(content={"success": True, "message": f"文件「{file_name}」已删除"})


@router.post("/batch-delete")
async def batch_delete_files(req: BatchDeleteFilesRequest):
    result = file_service.batch_delete_files(req.job_ids, req.collection)
    ok = len(result["deleted"])
    fail = len(result["failed"])
    return JSONResponse(content={
        "success": True,
        "message": f"已删除 {ok} 个，失败 {fail} 个",
        "data": result,
    })
