# -*- coding: utf-8 -*-
"""
图文模式切分服务
负责从 OSS 下载 PDF、本地解析、图片上传 OSS、写库等完整流程
"""

import asyncio
import logging
import uuid
from typing import Any, Dict, List

from app.core.config import settings
from app.db import (
    get_category_repository,
    get_chunk_repository,
    get_chunk_image_repository,
    get_document_job_repository,
    get_job_repository,
)
from app.services.doc_image_parser import parse_pdf, parse_word
from app.services.oss_service import get_oss_service

logger = logging.getLogger(__name__)


async def process_image_mode_files(
    all_files: List[Dict[str, Any]],
    category_id: str,
    category_name: str,
    collection: str,
    chunk_size: int,
    chunk_overlap: int,
    image_dpi: int,
) -> Dict[str, Any]:
    """
    图文模式批量切分：下载 OSS PDF → PyMuPDF 解析 → 图片上传 OSS → 写 chunk_store + chunk_image。

    Returns:
        {"submitted": [...], "errors": [...]}
    """
    doc_job_repo = get_document_job_repository()
    chunk_repo = get_chunk_repository()
    img_repo = get_chunk_image_repository()
    oss_service = get_oss_service()

    submitted = []
    errors = []

    for f in all_files:
        file_name = f["file_name"]
        ext = file_name.lower().rsplit(".", 1)[-1]
        if ext not in ("pdf", "docx"):
            errors.append({"file_name": file_name, "error": "图文模式仅支持 PDF / DOCX"})
            continue

        try:
            # 清理旧 job 的 OSS 图片和数据库记录，避免重复切分时残留
            old_job = doc_job_repo.get_by_filename_category_collection(file_name, category_id, collection)
            if old_job and old_job.get("job_id"):
                old_job_id = old_job["job_id"]
                try:
                    old_oss_keys = img_repo.get_oss_keys_by_job(old_job_id)
                    if old_oss_keys:
                        oss_service.delete_objects(old_oss_keys)
                        logger.info(f"[图文切分] 清理旧图片 OSS: {len(old_oss_keys)} 个 job_id={old_job_id}")
                    img_repo.delete_by_job(old_job_id)
                    chunk_repo.delete_by_job(old_job_id)
                except Exception as e:
                    logger.warning(f"[图文切分] 清理旧 job 失败（继续）: {e}")

            file_content = oss_service.get_object_bytes(f"{category_name}/{file_name}")
            job_id = str(uuid.uuid4())

            if ext == "pdf":
                chunks, image_records = await asyncio.to_thread(
                    parse_pdf,
                    file_content=file_content,
                    job_id=job_id,
                    chunk_size=chunk_size,
                    chunk_overlap=chunk_overlap,
                    image_dpi=image_dpi,
                )
            else:  # docx
                chunks, image_records = await asyncio.to_thread(
                    parse_word,
                    file_content=file_content,
                    job_id=job_id,
                    chunk_size=chunk_size,
                    chunk_overlap=chunk_overlap,
                )

            chunk_repo.bulk_insert(
                job_id=job_id,
                file_name=file_name,
                chunks=[{"page_content": c["content"], "metadata": c["metadata"]} for c in chunks],
            )
            if image_records:
                img_repo.bulk_insert(image_records)

            doc_job_repo.upsert(
                file_name=file_name,
                job_id=job_id,
                category_id=category_id,
                collection=collection,
            )
            get_job_repository().upsert_job(
                job_id=job_id,
                file_name=file_name,
                namespace=settings.adb_namespace,
                collection=collection,
                splitting_method="image_mode",
                dry_run=False,
                status="Success",
                message="图文模式本地切分完成",
            )
            submitted.append({"file_name": file_name, "job_id": job_id})
            logger.info(f"[图文切分] {file_name} 完成: {len(chunks)} 切片, {len(image_records)} 图片")

        except Exception as e:
            logger.error(f"[图文切分] {file_name} 失败: {e}")
            errors.append({"file_name": file_name, "error": str(e)})

    return {"submitted": submitted, "errors": errors}
