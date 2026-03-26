# -*- coding: utf-8 -*-
"""上传任务 API"""
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from app.services import job_service

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("")
async def list_jobs(limit: int = Query(200, ge=1, le=1000)):
    return JSONResponse(content={"success": True, "data": job_service.list_jobs(limit=limit)})


@router.get("/debug")
async def debug_jobs():
    return JSONResponse(content={"success": True, "data": job_service.get_job_debug_context()})


@router.get("/{job_id}")
async def get_job(job_id: str):
    return JSONResponse(content={"success": True, "data": job_service.get_job_detail(job_id)})


@router.post("/{job_id}/fetch-chunks")
async def fetch_chunks(job_id: str):
    result = await job_service.fetch_and_store_chunks(job_id)
    return JSONResponse(content={
        "success": True,
        "message": f"切片已保存，共 {result['total']} 个",
        "data": result,
    })


@router.post("/{job_id}/cancel")
async def cancel_job(job_id: str):
    result = job_service.cancel_job(job_id)
    return JSONResponse(content={"success": True, "message": result["message"], "data": {"job": result["job"]}})
