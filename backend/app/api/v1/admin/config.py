# -*- coding: utf-8 -*-
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from app.services.adb_vector_service import get_adb_vector_service
from app.core.config import settings

router = APIRouter()


@router.get("/config")
async def get_config():
    """获取当前 ADB 配置信息"""
    try:
        vs = get_adb_vector_service()
        return JSONResponse(status_code=200, content={
            "success": True,
            "data": {
                "instance_id": vs.instance_id,
                "region_id": vs.region_id,
                "namespace": settings.adb_namespace,
                "collection": settings.adb_collection,
                "embedding_model": settings.adb_embedding_model,
            }
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
