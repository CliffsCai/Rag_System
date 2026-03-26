# -*- coding: utf-8 -*-
"""
文件列表业务逻辑（knowledge_document_job 视图）
"""
import logging
from typing import Optional

from app.core.exceptions import NotFoundError, ExternalServiceError
from app.db import get_document_job_repository
from app.db.chunk_repository import get_chunk_repository
from app.db import chunk_image_repository
from app.services.oss_service import get_oss_service
from app.services.adb_document_service import ADBDocumentService
from app.core.config import settings

logger = logging.getLogger(__name__)


def list_files(limit: int = 200, collection: Optional[str] = None) -> dict:
    files = get_document_job_repository().list_all_with_status(
        limit=limit, collection=collection or None
    )
    return {"files": files, "total": len(files)}


def delete_file(job_id: str, collection: str) -> str:
    """
    联动删除文件：ADB 向量库 + OSS 图片 + 切片表 + job 记录。
    返回被删除的 file_name。
    """
    doc_job_repo = get_document_job_repository()
    chunk_repo = get_chunk_repository()

    record = doc_job_repo.get_by_job_id(job_id)
    if not record:
        raise NotFoundError("文件记录不存在")

    file_name = record["file_name"]

    # 1. ADB 向量库删除（失败不阻断）
    try:
        ADBDocumentService(namespace=settings.adb_namespace, collection=collection).delete_document(file_name)
    except Exception as e:
        logger.warning("ADB 删除失败（继续）", extra={"file_name": file_name, "error": str(e)})

    # 2. 图文模式：OSS 图片 + chunk_image 记录
    try:
        img_repo = chunk_image_repository.get_chunk_image_repository()
        oss_keys = img_repo.get_oss_keys_by_file(file_name)
        if oss_keys:
            get_oss_service().delete_objects(oss_keys)
            logger.info("删除 OSS 图片", extra={"file_name": file_name, "count": len(oss_keys)})
        img_repo.delete_by_file(file_name)
    except Exception as e:
        logger.warning("图片清理失败（继续）", extra={"file_name": file_name, "error": str(e)})

    # 3. 切片
    chunk_repo.delete_by_job(job_id)

    # 4. job 记录
    doc_job_repo.delete_by_job_id(job_id)

    return file_name


def batch_delete_files(job_ids: list[str], collection: str) -> dict:
    """批量删除文件，部分失败不中断，返回 {deleted, failed}"""
    deleted, failed = [], []
    for job_id in job_ids:
        try:
            file_name = delete_file(job_id, collection)
            deleted.append(file_name)
        except Exception as e:
            logger.error("批量删除单文件失败", extra={"job_id": job_id, "error": str(e)})
            failed.append({"job_id": job_id, "error": str(e)})
    return {"deleted": deleted, "failed": failed}
