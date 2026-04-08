# -*- coding: utf-8 -*-
"""
文档管理业务逻辑
"""
import asyncio
import logging
import re
from typing import Optional

from fastapi import BackgroundTasks

from app.core.exceptions import NotFoundError, ValidationError, ExternalServiceError, ConflictError
from app.services.oss_service import get_oss_service
from app.db import (
    get_kb_repository,
    get_category_repository,
    get_category_file_repository,
    get_file_repository,
    get_job_repository,
)

logger = logging.getLogger(__name__)

ALLOWED_EXT = {".pdf", ".doc", ".docx", ".txt", ".md", ".ppt", ".pptx"}
# 允许：字母、数字、中文、下划线、连字符、点、空格
_SAFE_FILENAME_RE = re.compile(r'^[\w\u4e00-\u9fff\-\. ]+$')


# ── 工具函数 ──────────────────────────────────────────────────────────────────

def validate_file(filename: str, size: int) -> None:
    ext = "." + filename.rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_EXT:
        raise ValidationError(f"不支持的文件格式: {ext}")
    if size > 200 * 1024 * 1024:
        raise ValidationError("文件超过 200MB 限制")
    if not _SAFE_FILENAME_RE.match(filename):
        raise ValidationError(
            f"文件名「{filename}」含有非法字符（不允许 / \\ ? # * 等特殊符号），请重命名后上传"
        )


def _get_kb_or_raise(kb_name: str) -> dict:
    kb = get_kb_repository().get_by_name(kb_name)
    if not kb:
        raise NotFoundError(f"知识库「{kb_name}」不存在")
    return kb


# ── 单文件上传到知识库 ────────────────────────────────────────────────────────

async def upload_document(
    file_name: str,
    file_content: bytes,
    kb_name: str,
    background_tasks: BackgroundTasks,
    chunk_size: int = 500,
    chunk_overlap: int = 50,
    image_dpi: int = 150,
) -> dict:
    """
    单文件上传入口：
    1. 校验文件
    2. 检查同名文件是否已存在，存在则拒绝（要求用户先删除旧版本）
    3. 上传 OSS（kb/{kb_name}/{file_name}）
    4. 关联到 __default__ 类目，写 knowledge_category_file
    5. 写 knowledge_file + knowledge_job(pending)
    6. 触发后台任务（切分）
    7. 立即返回 job_id
    """
    validate_file(file_name, len(file_content))
    kb = _get_kb_or_raise(kb_name)

    oss_key = f"kb/{kb_name}/{file_name}"
    file_repo = get_file_repository()

    # 同名文件检查：拒绝覆盖，要求用户手动删除旧版本
    existing = file_repo.get_by_kb_and_oss_key(kb["id"], oss_key)
    if existing:
        raise ConflictError(
            f"文件「{file_name}」已存在于知识库「{kb_name}」，请先在文件列表删除旧版本后重新上传"
        )

    # 上传 OSS
    try:
        get_oss_service().upload_bytes(oss_key, file_content)
    except Exception as e:
        raise ExternalServiceError(f"OSS 上传失败: {e}") from e

    # 关联到 __default__ 类目
    from app.services.category_service import get_or_create_default_category
    default_cat = get_or_create_default_category()
    cat_file_repo = get_category_file_repository()
    # __default__ 类目下同名文件幂等处理（理论上不会出现，但防御一下）
    existing_cat_file = cat_file_repo.get_by_category_and_filename(default_cat["id"], file_name)
    if existing_cat_file:
        cat_file_repo.delete(existing_cat_file["id"])
    cat_file_record = cat_file_repo.create(
        category_id=default_cat["id"],
        file_name=file_name,
        oss_key=oss_key,
    )

    file_record = file_repo.create(
        kb_id=kb["id"],
        file_name=file_name,
        oss_key=oss_key,
        category_file_id=cat_file_record["id"],
        file_size=len(file_content),
        mime_type=_guess_mime(file_name),
        status="pending",
    )

    job = get_job_repository().create(file_id=file_record["id"], kb_id=kb["id"])
    job_id = job["id"]

    background_tasks.add_task(
        _run_pipeline,
        job_id=job_id,
        file_id=file_record["id"],
        kb_id=kb["id"],
        kb_name=kb_name,
        file_name=file_name,
        oss_key=oss_key,
        image_mode=kb["image_mode"],
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        image_dpi=image_dpi,
    )

    logger.info(f"[upload] {file_name} → job_id={job_id}")
    return {"job_id": job_id, "file_id": file_record["id"], "file_name": file_name}


# ── 类目文件上传到 OSS ────────────────────────────────────────────────────────

def upload_to_category(file_name: str, file_content: bytes, category_id: str) -> dict:
    validate_file(file_name, len(file_content))
    category = get_category_repository().get(category_id)
    if not category:
        raise NotFoundError("类目不存在")

    oss_key = get_oss_service().upload_file(f"category/{category['name']}", file_name, file_content)

    cat_file_repo = get_category_file_repository()
    existing = cat_file_repo.get_by_category_and_filename(category_id, file_name)
    if existing:
        cat_file_repo.delete(existing["id"])

    return cat_file_repo.create(category_id=category_id, file_name=file_name, oss_key=oss_key)


async def batch_upload_to_category(files: list, category_id: str) -> dict:
    category = get_category_repository().get(category_id)
    if not category:
        raise NotFoundError("类目不存在")

    async def _upload_one(file_name: str, file_content: bytes) -> dict:
        file_name = file_name.replace("\\", "/").split("/")[-1]
        try:
            validate_file(file_name, len(file_content))
        except ValidationError as e:
            return {"file_name": file_name, "success": False, "error": str(e)}
        try:
            oss_key = await asyncio.to_thread(
                get_oss_service().upload_file,
                f"category/{category['name']}", file_name, file_content,
            )
        except Exception as e:
            return {"file_name": file_name, "success": False, "error": f"OSS 上传失败: {e}"}

        cat_file_repo = get_category_file_repository()
        existing = cat_file_repo.get_by_category_and_filename(category_id, file_name)
        if existing:
            cat_file_repo.delete(existing["id"])
        record = cat_file_repo.create(category_id=category_id, file_name=file_name, oss_key=oss_key)
        return {"file_name": file_name, "success": True, "record": record}

    results = await asyncio.gather(*[_upload_one(name, content) for name, content in files])
    succeeded = [r for r in results if r["success"]]
    failed = [{"file_name": r["file_name"], "error": r["error"]} for r in results if not r["success"]]
    return {"succeeded": succeeded, "failed": failed, "total": len(files)}


# ── 类目文件批量切分到知识库 ──────────────────────────────────────────────────

async def start_chunking(
    category_id: str,
    kb_name: str,
    background_tasks: BackgroundTasks,
    chunk_size: int = 500,
    chunk_overlap: int = 50,
    image_dpi: int = 150,
) -> dict:
    """将类目下所有文件提交到知识库切分流水线，每个文件后台异步处理"""
    category = get_category_repository().get(category_id)
    if not category:
        raise NotFoundError("类目不存在")

    kb = _get_kb_or_raise(kb_name)
    all_files = get_category_file_repository().list_by_category(category_id)
    if not all_files:
        return {"submitted": 0, "files": [], "errors": []}

    file_repo = get_file_repository()
    job_repo = get_job_repository()
    submitted, skipped, errors = [], [], []

    for f in all_files:
        file_name = f["file_name"]
        oss_key = f["oss_key"]
        try:
            existing = file_repo.get_by_kb_and_oss_key(kb["id"], oss_key)
            if existing:
                skipped.append({"file_name": file_name, "reason": "已存在，请先删除旧版本"})
                logger.info(f"[start_chunking] 跳过已存在文件: {file_name}")
                continue

            file_record = file_repo.create(
                kb_id=kb["id"],
                file_name=file_name,
                oss_key=oss_key,
                category_file_id=f["id"],
                status="pending",
            )
            job = job_repo.create(file_id=file_record["id"], kb_id=kb["id"])
            job_id = job["id"]

            background_tasks.add_task(
                _run_pipeline,
                job_id=job_id,
                file_id=file_record["id"],
                kb_id=kb["id"],
                kb_name=kb_name,
                file_name=file_name,
                oss_key=oss_key,
                image_mode=kb["image_mode"],
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                image_dpi=image_dpi,
            )
            submitted.append({"file_name": file_name, "job_id": job_id})
        except Exception as e:
            logger.error(f"[start_chunking] {file_name} 提交失败: {e}")
            errors.append({"file_name": file_name, "error": str(e)})

    return {"submitted": len(submitted), "files": submitted, "skipped": skipped, "errors": errors}


# ── 后台流水线（转发给 job_service）──────────────────────────────────────────

async def _run_pipeline(
    job_id: str,
    file_id: str,
    kb_id: str,
    kb_name: str,
    file_name: str,
    oss_key: str,
    image_mode: bool,
    chunk_size: int,
    chunk_overlap: int,
    image_dpi: int,
) -> None:
    from app.services.job_service import run_job_pipeline
    await run_job_pipeline(
        job_id=job_id,
        file_id=file_id,
        kb_id=kb_id,
        kb_name=kb_name,
        file_name=file_name,
        oss_key=oss_key,
        image_mode=image_mode,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        image_dpi=image_dpi,
    )


# ── 文档检索 ──────────────────────────────────────────────────────────────────

def search_documents(
    query: str,
    kb_name: str,
    top_k: int = 10,
    filter_expr: Optional[str] = None,
    ranker: str = "RRF",
    hybrid_alpha: float = 0.5,
    keyword_filter: Optional[str] = None,
) -> list:
    from app.services.milvus_service import get_milvus_service
    hits = get_milvus_service().hybrid_search(
        collection_name=kb_name,
        query=query,
        top_k=top_k,
        filter_expr=filter_expr,
        ranker=ranker,
        hybrid_alpha=hybrid_alpha,
        keyword_filter=keyword_filter or None,
    )

    # 批量查图片记录，给每个 hit 附上 image_map（placeholder → presigned URL）
    if hits:
        try:
            from app.db import get_chunk_image_repository
            from app.services.oss_service import get_oss_service
            chunk_ids = [h["chunk_id"] for h in hits if h.get("chunk_id")]
            img_records = get_chunk_image_repository().get_by_chunk_ids(chunk_ids)
            oss_svc = get_oss_service()
            chunk_img_map: dict = {}
            for r in img_records:
                cid = r["chunk_id"]
                ph = r.get("placeholder", "")
                ok = r.get("oss_key", "")
                if ph and ok:
                    try:
                        url = oss_svc.get_presigned_url(ok, expires=3600)
                    except Exception:
                        from urllib.parse import quote
                        url = f"/api/v1/documents/image-proxy?oss_key={quote(ok, safe='/')}"
                    chunk_img_map.setdefault(cid, {})[ph] = url
            for h in hits:
                h["image_map"] = chunk_img_map.get(h["chunk_id"], {})
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"search_documents 查询图片失败（不影响结果）: {e}")
            for h in hits:
                h.setdefault("image_map", {})

    return hits


# ── 工具 ──────────────────────────────────────────────────────────────────────

def _guess_mime(file_name: str) -> str:
    ext = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
    return {
        "pdf": "application/pdf",
        "doc": "application/msword",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "txt": "text/plain",
        "md": "text/markdown",
        "ppt": "application/vnd.ms-powerpoint",
        "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    }.get(ext, "application/octet-stream")
