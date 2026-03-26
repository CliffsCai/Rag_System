# -*- coding: utf-8 -*-
"""类目 API"""
from typing import Optional
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.services import category_service

router = APIRouter(prefix="/categories", tags=["categories"])


class CategoryCreate(BaseModel):
    name: str
    description: Optional[str] = None


class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


@router.get("")
async def list_categories():
    return JSONResponse(content={"success": True, "data": category_service.list_categories()})


@router.post("")
async def create_category(body: CategoryCreate):
    category = category_service.create_category(body.name, body.description)
    return JSONResponse(content={"success": True, "message": "类目创建成功", "data": category})


@router.get("/{category_id}")
async def get_category(category_id: str):
    result = category_service.get_category_with_files(category_id)
    return JSONResponse(content={"success": True, "data": result})


@router.put("/{category_id}")
async def update_category(category_id: str, body: CategoryUpdate):
    result = category_service.update_category(category_id, body.name, body.description)
    return JSONResponse(content={"success": True, "message": "更新成功", "data": result})


@router.delete("/{category_id}")
async def delete_category(category_id: str):
    category_service.delete_category(category_id)
    return JSONResponse(content={"success": True, "message": "类目删除成功"})


class BatchDeleteFilesRequest(BaseModel):
    file_ids: list[str]


@router.delete("/{category_id}/files/{file_id}")
async def delete_category_file(category_id: str, file_id: str):
    file_name = category_service.delete_category_file(category_id, file_id)
    return JSONResponse(content={"success": True, "message": f"文件「{file_name}」已删除"})


@router.post("/{category_id}/files/batch-delete")
async def batch_delete_category_files(category_id: str, body: BatchDeleteFilesRequest):
    result = category_service.batch_delete_category_files(category_id, body.file_ids)
    return JSONResponse(content={
        "success": True,
        "message": f"已删除 {len(result['deleted'])} 个文件",
        "data": result,
    })
