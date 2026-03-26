# -*- coding: utf-8 -*-
"""
文档管理业务逻辑
"""
import asyncio
import json
import logging
from typing import Optional

from app.core.exceptions import NotFoundError, ValidationError, ExternalServiceError
from app.services.adb_document_service import ADBDocumentService, get_adb_document_service
from app.services.oss_service import get_oss_service
from app.db import (
    get_category_repository,
    get_category_file_repository,
    get_document_job_repository,
    get_collection_config_repository,
)
from app.core.config import settings

logger = logging.getLogger(__name__)

ALLOWED_EXT = {".pdf", ".doc", ".docx", ".txt", ".md", ".ppt", ".pptx"}


# ─── 工具函数 ─────────────────────────────────────────────────────────────────

def validate_file(filename: str, size: int) -> None:
    ext = "." + filename.rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_EXT:
        raise ValidationError(f"不支持的文件格式: {ext}")
    if size > 200 * 1024 * 1024:
        raise ValidationError("文件超过 200MB 限制")


def resolve_metadata(collection: str, file_name: str, base_meta: dict) -> dict:
    try:
        config = get_collection_config_repository().get_by_collection(settings.adb_namespace, collection)
        if not config:
            return base_meta
        for field in config.get("metadata_fields") or []:
            key = field.get("key")
            if key and field.get("auto_inject") == "filename_prefix":
                base_meta[key] = file_name.rsplit(".", 1)[0] if "." in file_name else file_name
    except Exception as e:
        logger.warning("metadata 注入失败，跳过", extra={"error": str(e)})
    return base_meta


# ─── 单文件上传切分 ───────────────────────────────────────────────────────────

def upload_document(
    file_name: str,
    file_content: bytes,
    metadata_raw: Optional[str],
    chunk_size: int = 800,
    chunk_overlap: int = 100,
    zh_title_enhance: bool = True,
    vl_enhance: bool = False,
) -> dict:
    validate_file(file_name, len(file_content))

    metadata_dict: dict = {}
    if metadata_raw and metadata_raw.strip() and metadata_raw.strip().lower() not in ("undefined", "null", "none"):
        try:
            metadata_dict = json.loads(metadata_raw)
        except json.JSONDecodeError as e:
            raise ValidationError(f"元数据格式错误: {e}")
    metadata_dict["filename"] = file_name

    collection = settings.adb_collection
    metadata_dict = resolve_metadata(collection, file_name, metadata_dict)

    try:
        doc_service = ADBDocumentService(namespace=settings.adb_namespace, collection=collection)
        job_id = doc_service.upload_document_async(
            file_name=file_name,
            file_content=file_content,
            metadata=metadata_dict,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            zh_title_enhance=zh_title_enhance,
            vl_enhance=vl_enhance,
            dry_run=True,
            document_loader_name=settings.adb_document_loader_pdf if file_name.lower().endswith(".pdf") else None,
            text_splitter_name=settings.adb_text_splitter,
        )
    except Exception as e:
        raise ExternalServiceError(f"ADB 上传失败: {e}") from e

    get_document_job_repository().upsert(
        file_name=file_name, job_id=job_id, category_id=None, collection=collection
    )
    return {"job_id": job_id, "file_name": file_name}


# ─── 类目文件上传到 OSS ───────────────────────────────────────────────────────

def upload_to_category(file_name: str, file_content: bytes, category_id: str) -> dict:
    validate_file(file_name, len(file_content))

    category = get_category_repository().get(category_id)
    if not category:
        raise NotFoundError("类目不存在")

    try:
        oss_key = get_oss_service().upload_file(category["name"], file_name, file_content)
    except Exception as e:
        raise ExternalServiceError(f"OSS 上传失败: {e}") from e

    cat_file_repo = get_category_file_repository()
    existing = cat_file_repo.get_by_category_and_filename(category_id, file_name)
    if existing:
        cat_file_repo.delete(existing["id"])

    return cat_file_repo.create(category_id=category_id, file_name=file_name, oss_key=oss_key)


# ─── 类目文件批量上传到 OSS ──────────────────────────────────────────────────

async def batch_upload_to_category(
    files: list[tuple[str, bytes]],
    category_id: str,
) -> dict:
    """
    并发上传多个文件到 OSS 类目目录。
    files: [(file_name, file_content), ...]
    返回: {succeeded: [...], failed: [...]}
    """
    category = get_category_repository().get(category_id)
    if not category:
        raise NotFoundError("类目不存在")

    async def _upload_one(file_name: str, file_content: bytes) -> dict:
        # 去除路径前缀，只保留文件名（防止文件夹上传时携带路径）
        file_name = file_name.replace("\\", "/").split("/")[-1]
        try:
            validate_file(file_name, len(file_content))
        except ValidationError as e:
            return {"file_name": file_name, "success": False, "error": str(e)}

        try:
            oss_key = await asyncio.to_thread(
                get_oss_service().upload_file, category["name"], file_name, file_content
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

async def start_chunking(
    category_id: str,
    collection: str,
    chunk_size: int = 800,
    chunk_overlap: int = 100,
    zh_title_enhance: bool = True,
    vl_enhance: bool = False,
    text_splitter_name: Optional[str] = None,
    image_dpi: int = 150,
) -> dict:
    category = get_category_repository().get(category_id)
    if not category:
        raise NotFoundError("类目不存在")

    col_config = get_collection_config_repository().get_by_collection(settings.adb_namespace, collection)
    is_image_mode = bool(col_config and col_config.get("image_mode"))

    category_name = category["name"]
    cat_file_repo = get_category_file_repository()
    doc_job_repo = get_document_job_repository()
    oss_service = get_oss_service()

    all_files = cat_file_repo.list_by_category(category_id)
    if not all_files:
        return {"submitted": 0, "skipped": [], "files": [], "errors": []}

    submitted, skipped, errors = [], [], []

    if is_image_mode:
        from app.services.image_mode_service import process_image_mode_files
        result = await process_image_mode_files(
            all_files=all_files,
            category_id=category_id,
            category_name=category_name,
            collection=collection,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            image_dpi=image_dpi,
        )
        submitted = result["submitted"]
        errors = result["errors"]
    else:
        doc_service = ADBDocumentService(namespace=settings.adb_namespace, collection=collection)
        for f in all_files:
            file_name = f["file_name"]
            existing_job = doc_job_repo.get_by_filename_category_collection(file_name, category_id, collection)
            if existing_job and existing_job.get("job_id"):
                try:
                    detail = await asyncio.to_thread(doc_service.get_upload_job_detail, existing_job["job_id"])
                    if (detail.get("status") or "").lower() in ("running", "start"):
                        skipped.append(file_name)
                        continue
                except Exception:
                    pass

            try:
                url = await asyncio.to_thread(oss_service.get_presigned_url_by_category, category_name, file_name)
                metadata = resolve_metadata(
                    collection, file_name,
                    {"filename": file_name, "category": category_name},
                )
                job_id = await asyncio.to_thread(
                    doc_service.upload_document_from_url,
                    file_name, url, metadata,
                    chunk_size, chunk_overlap,
                    zh_title_enhance, vl_enhance, True,
                    settings.adb_document_loader_pdf if file_name.lower().endswith(".pdf") else None,
                    text_splitter_name or settings.adb_text_splitter,
                )
                doc_job_repo.upsert(file_name=file_name, job_id=job_id, category_id=category_id, collection=collection)
                submitted.append({"file_name": file_name, "job_id": job_id})
            except Exception as e:
                logger.error("提交切分失败", extra={"file_name": file_name, "error": str(e)})
                errors.append({"file_name": file_name, "error": str(e)})

    return {"submitted": len(submitted), "skipped": skipped, "files": submitted, "errors": errors}


async def start_chunking_direct(
    category_id: str,
    collection: str,
    chunk_size: int = 800,
    chunk_overlap: int = 100,
    zh_title_enhance: bool = True,
    vl_enhance: bool = False,
    text_splitter_name: Optional[str] = None,
) -> dict:
    """
    直接切分并入库（dry_run=False）：ADB 自动切分、向量化、写入向量库，一步到位。
    任务完成后后台自动 fetch-chunks 写入本地 knowledge_chunk_store，标记 vectorized=True。
    不支持 image_mode collection。
    """
    category = get_category_repository().get(category_id)
    if not category:
        raise NotFoundError("类目不存在")

    col_config = get_collection_config_repository().get_by_collection(settings.adb_namespace, collection)
    if col_config and col_config.get("image_mode"):
        raise ValidationError("图文模式 collection 不支持直接入库，请使用普通切分流程")

    category_name = category["name"]
    cat_file_repo = get_category_file_repository()
    doc_job_repo = get_document_job_repository()
    oss_service = get_oss_service()

    all_files = cat_file_repo.list_by_category(category_id)
    if not all_files:
        return {"submitted": 0, "skipped": [], "files": [], "errors": []}

    submitted, skipped, errors = [], [], []
    doc_service = ADBDocumentService(namespace=settings.adb_namespace, collection=collection)

    for f in all_files:
        file_name = f["file_name"]
        existing_job = doc_job_repo.get_by_filename_category_collection(file_name, category_id, collection)
        if existing_job and existing_job.get("job_id"):
            try:
                detail = await asyncio.to_thread(doc_service.get_upload_job_detail, existing_job["job_id"])
                if (detail.get("status") or "").lower() in ("running", "start"):
                    skipped.append(file_name)
                    continue
            except Exception:
                pass

        try:
            url = await asyncio.to_thread(oss_service.get_presigned_url_by_category, category_name, file_name)
            metadata = resolve_metadata(
                collection, file_name,
                {"filename": file_name, "category": category_name},
            )
            job_id = await asyncio.to_thread(
                doc_service.upload_document_from_url,
                file_name, url, metadata,
                chunk_size, chunk_overlap,
                zh_title_enhance, vl_enhance,
                False,  # dry_run=False，直接入库
                settings.adb_document_loader_pdf if file_name.lower().endswith(".pdf") else None,
                text_splitter_name or settings.adb_text_splitter,
            )
            doc_job_repo.upsert(file_name=file_name, job_id=job_id, category_id=category_id, collection=collection)
            doc_job_repo.mark_vectorized(job_id)
            submitted.append({"file_name": file_name, "job_id": job_id})

        except Exception as e:
            logger.error("直接入库失败", extra={"file_name": file_name, "error": str(e)})
            errors.append({"file_name": file_name, "error": str(e)})

    return {"submitted": len(submitted), "skipped": skipped, "files": submitted, "errors": errors}


async def _sync_chunks_after_direct(job_id: str, file_name: str, collection: str) -> None:
    """
    后台任务：轮询 ADB job 状态，完成后 fetch-chunks 写入本地表并标记 vectorized。
    """
    from app.services.job_service import fetch_and_store_chunks
    doc_service = ADBDocumentService(namespace=settings.adb_namespace, collection=collection)
    doc_job_repo = get_document_job_repository()

    max_wait = 600   # 最多等 10 分钟
    interval = 10    # 每 10 秒轮询一次
    elapsed = 0

    while elapsed < max_wait:
        await asyncio.sleep(interval)
        elapsed += interval
        try:
            detail = await asyncio.to_thread(doc_service.get_upload_job_detail, job_id)
            status = (detail.get("status") or "").lower()
            if status == "success":
                break
            if status in ("failed", "error", "cancelled"):
                logger.error(f"[直接入库] job 失败，跳过 fetch-chunks job_id={job_id} status={status}")
                return
        except Exception as e:
            logger.warning(f"[直接入库] 轮询状态失败，继续等待 job_id={job_id}: {e}")

    else:
        logger.error(f"[直接入库] 等待超时，跳过 fetch-chunks job_id={job_id}")
        return

    try:
        result = await fetch_and_store_chunks(job_id)
        doc_job_repo.mark_vectorized(job_id)
        logger.info(f"[直接入库] fetch-chunks 完成 job_id={job_id} file={file_name} chunks={result['total']}")
    except Exception as e:
        logger.error(f"[直接入库] fetch-chunks 失败 job_id={job_id}: {e}")


# ─── 文档列表 / 详情 / 删除 / 检索 ───────────────────────────────────────────

def list_documents() -> dict:
    documents = get_adb_document_service().list_documents()
    return {"documents": documents, "total": len(documents)}


def get_document_detail(file_name: str) -> dict:
    return get_adb_document_service().describe_document(file_name)


def delete_document(file_name: str) -> None:
    get_adb_document_service().delete_document(file_name)


def search_documents(
    query: str,
    top_k: int = 10,
    filter_str: Optional[str] = None,
    hybrid_search: Optional[str] = "Weight",
    hybrid_alpha: float = 0.5,
    rerank_factor: Optional[float] = None,
    include_file_url: bool = False,
    collection: Optional[str] = None,
) -> list:
    if rerank_factor is not None:
        if rerank_factor <= 1:
            raise ValidationError("rerank_factor 必须大于 1")
        if top_k * rerank_factor > 1000:
            raise ValidationError(f"top_k({top_k}) * rerank_factor({rerank_factor}) 不能超过 1000")

    hybrid_search_args = None
    if hybrid_search == "Weight":
        hybrid_search_args = {"Weight": {"alpha": hybrid_alpha}}
    elif hybrid_search == "RRF":
        hybrid_search_args = {"RRF": {"k": 60}}

    col = collection or settings.adb_collection
    try:
        results = ADBDocumentService(namespace=settings.adb_namespace, collection=col).query_content(
            query=query,
            top_k=top_k,
            filter_str=filter_str,
            rerank_factor=rerank_factor,
            hybrid_search=hybrid_search if hybrid_search else None,
            hybrid_search_args=hybrid_search_args,
            include_file_url=include_file_url,
        )
    except Exception as e:
        raise ExternalServiceError(f"检索失败: {e}") from e

    return sorted(results, key=lambda x: x.get("rerank_score") or x.get("score") or 0, reverse=True)
