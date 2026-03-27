# -*- coding: utf-8 -*-
"""
切片业务逻辑
"""
import asyncio
import uuid
import logging
from typing import Optional

from app.core.exceptions import ForbiddenError, NotFoundError, ExternalServiceError
from app.db import get_chunk_repository, get_job_repository, get_document_job_repository, get_chunk_image_repository
from app.db import get_collection_config_repository
from app.services.adb_document_service import ADBDocumentService
from app.services.chunk_cleaner import clean_single_chunk_with_llm
from app.services.oss_service import get_oss_service
from app.core.config import settings

logger = logging.getLogger(__name__)


# ─── 守卫 ─────────────────────────────────────────────────────────────────────

def check_not_vectorized(job_id: str) -> None:
    """已向量化的 job 不允许写操作"""
    record = get_document_job_repository().get_by_job_id(job_id)
    if record and record.get("vectorized"):
        raise ForbiddenError("该文件已上传向量库，不允许修改切片")


def _build_chunk_metadata(collection: str, file_name: str) -> dict:
    """
    按 collection 的 metadata_fields 配置构建 chunk metadata。
    只输出配置里声明的字段，不带 page 等解析时产生的内部字段。
    """
    try:
        config = get_collection_config_repository().get_by_collection(settings.adb_namespace, collection)
        if not config:
            return {}
        result = {}
        for field in config.get("metadata_fields") or []:
            key = field.get("key")
            if not key:
                continue
            if field.get("auto_inject") == "filename_prefix":
                result[key] = file_name.rsplit(".", 1)[0] if "." in file_name else file_name
        return result
    except Exception as e:
        logger.warning("构建 chunk metadata 失败，使用空 metadata", extra={"error": str(e)})
        return {}


# ─── 查询 ─────────────────────────────────────────────────────────────────────

def get_chunks_by_job(job_id: str) -> dict:
    chunks = get_chunk_repository().get_by_job(job_id)
    return {"job_id": job_id, "chunks": chunks, "total": len(chunks)}


def list_all_job_ids() -> list[str]:
    return get_chunk_repository().list_all_job_ids()


# ─── 单切片操作 ───────────────────────────────────────────────────────────────

def edit_chunk(job_id: str, chunk_index: int, content: str) -> None:
    check_not_vectorized(job_id)
    chunk_repo = get_chunk_repository()
    if not chunk_repo.get_by_job_and_index(job_id, chunk_index):
        raise NotFoundError(f"切片不存在: job_id={job_id}, chunk_index={chunk_index}")
    chunk_repo.update_content_by_index(job_id, chunk_index, content, status="edited")


def clean_single_chunk(job_id: str, chunk_index: int, instruction: Optional[str] = None) -> str:
    check_not_vectorized(job_id)
    chunk_repo = get_chunk_repository()
    chunk = chunk_repo.get_by_job_and_index(job_id, chunk_index)
    if not chunk:
        raise NotFoundError(f"切片不存在: job_id={job_id}, chunk_index={chunk_index}")
    cleaned = clean_single_chunk_with_llm(chunk.get("current_content") or "", instruction)
    chunk_repo.update_content_by_index(job_id, chunk_index, cleaned, status="cleaned")
    return cleaned


def revert_single_chunk(job_id: str, chunk_index: int) -> None:
    check_not_vectorized(job_id)
    chunk_repo = get_chunk_repository()
    if not chunk_repo.get_by_job_and_index(job_id, chunk_index):
        raise NotFoundError(f"切片不存在: job_id={job_id}, chunk_index={chunk_index}")
    chunk_repo.revert_chunk_by_index(job_id, chunk_index)


# ─── 批量操作（按 job） ────────────────────────────────────────────────────────

async def clean_job_chunks(job_id: str, instruction: Optional[str] = None) -> dict:
    """并发 LLM 清洗某个 job 的所有切片"""
    check_not_vectorized(job_id)
    chunk_repo = get_chunk_repository()
    chunks = chunk_repo.get_by_job(job_id)
    if not chunks:
        raise NotFoundError("该 job 暂无切片数据")

    async def _clean_one(chunk: dict) -> Optional[dict]:
        try:
            cleaned = await asyncio.to_thread(
                clean_single_chunk_with_llm, chunk["current_content"], instruction
            )
            await asyncio.to_thread(
                chunk_repo.update_content, chunk["chunk_id"], cleaned, "cleaned"
            )
            return None
        except Exception as e:
            return {"chunk_id": chunk["chunk_id"], "error": str(e)}

    results = await asyncio.gather(*[_clean_one(c) for c in chunks])
    errors = [r for r in results if r is not None]
    success_count = len(chunks) - len(errors)
    return {"success": success_count, "failed": len(errors), "total": len(chunks), "errors": errors}


def revert_job_chunks(job_id: str) -> None:
    check_not_vectorized(job_id)
    get_chunk_repository().revert_job(job_id)


# ─── 全局批量操作 ─────────────────────────────────────────────────────────────

async def clean_all_chunks(instruction: Optional[str] = None) -> dict:
    """并发 LLM 清洗所有切片"""
    chunk_repo = get_chunk_repository()
    job_ids = list_all_job_ids()

    async def _clean_chunk(chunk: dict) -> bool:
        try:
            cleaned = await asyncio.to_thread(
                clean_single_chunk_with_llm, chunk["current_content"], instruction
            )
            await asyncio.to_thread(chunk_repo.update_content, chunk["chunk_id"], cleaned, "cleaned")
            return True
        except Exception:
            return False

    all_chunks = []
    for job_id in job_ids:
        all_chunks.extend(chunk_repo.get_by_job(job_id))

    results = await asyncio.gather(*[_clean_chunk(c) for c in all_chunks])
    total_success = sum(1 for r in results if r)
    return {"success": total_success, "failed": len(results) - total_success}


def revert_all_chunks() -> None:
    get_chunk_repository().revert_all()


# ─── 向量库上传 ───────────────────────────────────────────────────────────────

def upsert_job_chunks(job_id: str) -> dict:
    check_not_vectorized(job_id)
    chunk_repo = get_chunk_repository()
    job_repo = get_job_repository()

    chunks = chunk_repo.get_by_job(job_id)
    if not chunks:
        raise NotFoundError("该 job 暂无切片数据")

    job_meta = job_repo.get_job(job_id)
    if not job_meta:
        raise NotFoundError("任务不存在")

    doc_service = ADBDocumentService(
        namespace=job_meta["namespace"],
        collection=job_meta["collection"],
    )
    chunk_metadata = _build_chunk_metadata(job_meta["collection"], job_meta["file_name"])
    upload_chunks = [
        {
            "id": c["chunk_id"],
            "content": c["current_content"],
            "metadata": chunk_metadata,
        }
        for c in chunks if c.get("current_content")
    ]

    try:
        result = doc_service.upsert_chunks(
            file_name=job_meta["file_name"],
            chunks=upload_chunks,
            should_replace_file=True,
            allow_insert_with_filter=True,
        )
    except Exception as e:
        raise ExternalServiceError(f"向量库上传失败: {e}") from e

    get_document_job_repository().mark_vectorized(job_id)
    return result


def batch_upsert_jobs(job_ids: list[str]) -> dict:
    """批量上传切片到向量库，已向量化的跳过，部分失败不中断"""
    succeeded, failed = [], []
    for job_id in job_ids:
        try:
            upsert_job_chunks(job_id)
            succeeded.append(job_id)
        except ForbiddenError:
            # 已向量化，跳过
            pass
        except Exception as e:
            logger.error("批量 upsert 单文件失败", extra={"job_id": job_id, "error": str(e)})
            failed.append({"job_id": job_id, "error": str(e)})
    return {"succeeded": succeeded, "failed": failed}


# ─── 图片管理 ─────────────────────────────────────────────────────────────────

def get_chunk_images(job_id: str, chunk_index: int) -> list:
    return get_chunk_image_repository().get_by_chunk(f"{job_id}_{chunk_index}")


def add_chunk_image(
    job_id: str,
    chunk_index: int,
    file_content: bytes,
    filename: str,
    insert_position: int = 0,
    page: Optional[int] = None,
) -> dict:
    check_not_vectorized(job_id)
    chunk_repo = get_chunk_repository()
    chunk = chunk_repo.get_by_job_and_index(job_id, chunk_index)
    if not chunk:
        raise NotFoundError(f"切片不存在: job_id={job_id}, chunk_index={chunk_index}")

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "png"
    job_meta = get_job_repository().get_job(job_id)
    if not job_meta:
        raise NotFoundError("任务不存在，无法确定图片存储路径")
    img_collection = job_meta.get("collection", "unknown")
    img_file_name = job_meta.get("file_name", "unknown")
    chunk_id = f"{job_id}_{chunk_index}"
    try:
        oss_key = get_oss_service().upload_file(
            f"rag_image/{img_collection}/{img_file_name}/{chunk_id}",
            f"{uuid.uuid4().hex[:12]}.{ext}",
            file_content,
        )
    except Exception as e:
        raise ExternalServiceError(f"OSS 上传失败: {e}") from e
    img_repo = get_chunk_image_repository()
    sort_order = len(img_repo.get_by_chunk(chunk_id))
    placeholder = f"<<IMAGE:{uuid.uuid4().hex[:8]}>>"
    record = img_repo.insert(
        chunk_id=chunk_id,
        job_id=job_id,
        placeholder=placeholder,
        oss_key=oss_key,
        page=page,
        sort_order=sort_order,
    )

    # 将占位符插入 current_content 的指定位置
    content = chunk.get("current_content") or ""
    pos = max(0, min(insert_position, len(content)))
    new_content = content[:pos] + placeholder + content[pos:]
    chunk_repo.update_content_by_index(job_id, chunk_index, new_content, status="edited")

    return record


def delete_chunk_image(job_id: str, chunk_index: int, image_id: str) -> None:
    check_not_vectorized(job_id)
    img_repo = get_chunk_image_repository()
    record = img_repo.get_by_id(image_id)
    if not record:
        raise NotFoundError("图片记录不存在")

    oss_key = record.get("oss_key")
    if oss_key:
        try:
            get_oss_service().delete_objects([oss_key])
        except Exception as e:
            logger.warning("OSS 图片删除失败（继续）", extra={"oss_key": oss_key, "error": str(e)})
    img_repo.delete(image_id)

    # 从 current_content 里删除对应占位符
    placeholder = record.get("placeholder", "")
    if placeholder:
        chunk_repo = get_chunk_repository()
        chunk = chunk_repo.get_by_job_and_index(job_id, chunk_index)
        if chunk:
            new_content = (chunk.get("current_content") or "").replace(placeholder, "")
            chunk_repo.update_content_by_index(job_id, chunk_index, new_content, status="edited")
