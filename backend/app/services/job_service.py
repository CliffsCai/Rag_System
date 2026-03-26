# -*- coding: utf-8 -*-
"""
上传任务业务逻辑
"""
import asyncio
import json
import logging
import httpx
from typing import Optional

from app.core.exceptions import ForbiddenError, ValidationError, ExternalServiceError
from app.db import get_job_repository, get_chunk_repository, get_document_job_repository
from app.services.adb_document_service import ADBDocumentService
from app.core.config import settings

logger = logging.getLogger(__name__)


def list_jobs(limit: int = 200) -> dict:
    jobs = get_job_repository().list_jobs(limit=limit)
    return {"jobs": jobs, "total": len(jobs)}


def get_job_debug_context() -> dict:
    repo = get_job_repository()
    return {
        "context": repo.get_debug_context(),
        "total": repo.count_jobs(),
        "sample": repo.list_jobs(limit=3),
    }


def get_job_detail(job_id: str) -> dict:
    job_meta = get_job_repository().get_job(job_id)
    detail = ADBDocumentService().get_upload_job_detail(job_id)

    adb_status = (detail.get("status") or "").lower()
    if detail.get("completed") or adb_status == "success":
        display_status = "Success"
    elif detail.get("error") or adb_status == "failed":
        display_status = "Failed"
    else:
        display_status = detail.get("status") or (job_meta or {}).get("status", "queued")

    return {"job": {**(job_meta or {}), "status": display_status}, "detail": detail}


async def fetch_and_store_chunks(job_id: str) -> dict:
    """
    从 ADB 获取 ChunkFileUrl，下载 JSONL 并存入 knowledge_chunk_store。
    返回 {"total": int, "source": str}
    """
    doc_job_repo = get_document_job_repository()
    doc_job_record = doc_job_repo.get_by_job_id(job_id)

    if doc_job_record and doc_job_record.get("vectorized"):
        raise ForbiddenError("该文件已上传向量库，不允许重新获取切片")

    file_name = (doc_job_record or {}).get("file_name") or job_id
    collection = (doc_job_record or {}).get("collection") or settings.adb_collection

    doc_service = ADBDocumentService(namespace=settings.adb_namespace, collection=collection)

    try:
        chunk_file_url = await asyncio.to_thread(doc_service.get_chunk_file_url, job_id)
    except Exception as e:
        raise ExternalServiceError(f"获取 ChunkFileUrl 失败: {e}") from e

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.get(chunk_file_url)
            resp.raise_for_status()
            content = resp.text
    except Exception as e:
        raise ExternalServiceError(f"下载切片文件失败: {e}") from e

    chunks = []
    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            chunks.append(json.loads(line))
        except json.JSONDecodeError:
            logger.warning("跳过无效 JSONL 行", extra={"job_id": job_id, "line": line[:80]})

    if not chunks:
        raise ValidationError("切片文件解析结果为空")

    await asyncio.to_thread(get_chunk_repository().bulk_insert, job_id, file_name, chunks)
    return {"total": len(chunks), "source": "jsonl"}


def cancel_job(job_id: str) -> dict:
    job_meta = get_job_repository().get_job(job_id)
    result = ADBDocumentService().cancel_upload_job(job_id)
    return {"message": result.get("message", "任务取消成功"), "job": job_meta}
