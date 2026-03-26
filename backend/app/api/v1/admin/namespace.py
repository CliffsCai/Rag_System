# -*- coding: utf-8 -*-
"""命名空间管理：创建、查询列表、查询详情、删除"""
import logging
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional

from app.services.adb_vector_service import get_adb_vector_service
from app.db.namespace_repository import get_namespace_repository
from ._deps import manager_credentials

logger = logging.getLogger(__name__)
router = APIRouter()


class CreateNamespaceRequest(BaseModel):
    namespace: str = Field(..., description="命名空间名称")
    namespace_password: str = Field(..., description="命名空间密码")
    display_name: Optional[str] = Field(None, description="显示名称")
    description: Optional[str] = Field(None, description="描述")


class DeleteNamespaceRequest(BaseModel):
    namespace: str = Field(..., description="命名空间名称")


@router.post("/namespace/create")
async def create_namespace(req: CreateNamespaceRequest):
    """创建命名空间，密码加密存入注册表"""
    try:
        account, pwd = manager_credentials()
        vs = get_adb_vector_service()
        result = vs.create_namespace(
            manager_account=account,
            manager_account_password=pwd,
            namespace=req.namespace,
            namespace_password=req.namespace_password,
        )
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("message", "创建失败"))

        get_namespace_repository().register(
            namespace=req.namespace,
            password=req.namespace_password,
            display_name=req.display_name,
            description=req.description,
        )
        return JSONResponse(status_code=200, content={
            "success": True,
            "message": f"命名空间 '{req.namespace}' 创建成功，密码已加密存储",
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建命名空间失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/namespace/list")
async def list_namespaces():
    """查询 ADB 命名空间列表，与注册表合并展示"""
    try:
        account, pwd = manager_credentials()
        vs = get_adb_vector_service()

        adb_result = vs.list_namespaces(manager_account=account, manager_account_password=pwd)
        adb_names = set(adb_result.get("namespaces", []))

        registered = {r["namespace"]: r for r in get_namespace_repository().list_all()}

        merged = []
        for name in adb_names:
            info = registered.get(name, {})
            merged.append({
                "namespace": name,
                "display_name": info.get("display_name") or name,
                "description": info.get("description") or "",
                "created_by": info.get("created_by") or "",
                "created_at": str(info.get("created_at") or ""),
            })
        merged.sort(key=lambda x: x["namespace"])

        return JSONResponse(status_code=200, content={
            "success": True,
            "data": {"namespaces": merged, "count": len(merged)},
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"查询命名空间列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/namespace/describe")
async def describe_namespace(namespace: str = Query(...)):
    """查询命名空间详情"""
    try:
        account, pwd = manager_credentials()
        result = get_adb_vector_service().describe_namespace(
            manager_account=account, manager_account_password=pwd, namespace=namespace
        )
        if not result.get("success"):
            raise HTTPException(status_code=404, detail=result.get("error", "查询失败"))
        return JSONResponse(status_code=200, content={"success": True, "data": result})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/namespace/delete")
async def delete_namespace(req: DeleteNamespaceRequest):
    """删除命名空间，同时清除注册表记录"""
    try:
        account, pwd = manager_credentials()
        result = get_adb_vector_service().delete_namespace(
            manager_account=account, manager_account_password=pwd, namespace=req.namespace
        )
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("message", "删除失败"))

        get_namespace_repository().delete(req.namespace)
        return JSONResponse(status_code=200, content={
            "success": True, "message": f"命名空间 '{req.namespace}' 已删除"
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除命名空间失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
