# -*- coding: utf-8 -*-
"""
切片业务逻辑
"""
import asyncio
import uuid
import logging
from typing import Optional

from app.core.exceptions import ForbiddenError, NotFoundError, ExternalServiceError
from app.db import get_chunk_repository, get_job_repository, get_chunk_image_repository, get_file_repository
from app.services.chunk_cleaner import clean_single_chunk_with_llm
from app.services.oss_service import get_oss_service

logger = logging.getLogger(__name__)


def _delete_job_images_from_oss(job_id: str) -> None:
    """删除一个 job 下所有切片图片的 OSS 文件（不删 PG，PG 由 CASCADE 处理）"""
    try:
        oss_keys = get_chunk_image_repository().get_oss_keys_by_job(job_id)
        if oss_keys:
            get_oss_service().delete_objects(oss_keys)
            logger.info(f"已删除 job {job_id} 的 {len(oss_keys)} 张 OSS 图片")
    except Exception as e:
        logger.warning(f"OSS 图片删除失败（继续）: job_id={job_id}, error={e}")


# ── 守卫 ──────────────────────────────────────────────────────────────────────

def check_not_vectorized(job_id: str) -> None:
    job = get_job_repository().get(job_id)
    if job and job.get("vectorized"):
        raise ForbiddenError("该文件已上传向量库，不允许修改切片")


# ── 查询 ──────────────────────────────────────────────────────────────────────

def get_chunks_by_job(job_id: str) -> dict:
    chunks = get_chunk_repository().get_by_job(job_id)
    return {"job_id": job_id, "chunks": chunks, "total": len(chunks)}


def list_all_job_ids() -> list:
    return get_chunk_repository().list_all_job_ids()


# ── 单切片操作 ────────────────────────────────────────────────────────────────

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


# ── 批量操作（按 job）────────────────────────────────────────────────────────

async def clean_job_chunks(job_id: str, instruction: Optional[str] = None) -> dict:
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
            await asyncio.to_thread(chunk_repo.update_content, chunk["chunk_id"], cleaned, "cleaned")
            return None
        except Exception as e:
            return {"chunk_id": chunk["chunk_id"], "error": str(e)}

    results = await asyncio.gather(*[_clean_one(c) for c in chunks])
    errors = [r for r in results if r is not None]
    return {"success": len(chunks) - len(errors), "failed": len(errors), "total": len(chunks), "errors": errors}


def revert_job_chunks(job_id: str) -> None:
    check_not_vectorized(job_id)
    get_chunk_repository().revert_job(job_id)


# ── 全局批量操作 ──────────────────────────────────────────────────────────────

async def clean_all_chunks(instruction: Optional[str] = None) -> dict:
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


# ── 向量库上传 ────────────────────────────────────────────────────────────────

async def upsert_job_chunks(job_id: str) -> dict:
    """切片编辑完成后手动触发向量化"""
    from app.services.job_service import upsert_job_to_milvus
    return await upsert_job_to_milvus(job_id)


async def batch_upsert_jobs(job_ids: list) -> dict:
    succeeded, failed = [], []
    for job_id in job_ids:
        try:
            job = get_job_repository().get(job_id)
            if job and job.get("vectorized"):
                continue  # 已向量化跳过
            await upsert_job_chunks(job_id)
            succeeded.append(job_id)
        except ForbiddenError:
            pass
        except Exception as e:
            logger.error("批量 upsert 失败", extra={"job_id": job_id, "error": str(e)})
            failed.append({"job_id": job_id, "error": str(e)})
    return {"succeeded": succeeded, "failed": failed}


# ── 图片管理 ──────────────────────────────────────────────────────────────────

def get_chunk_images(job_id: str, chunk_index: int) -> list:
    chunk = get_chunk_repository().get_by_job_and_index(job_id, chunk_index)
    if not chunk:
        return []
    records = get_chunk_image_repository().get_by_chunk(chunk["chunk_id"])
    oss_svc = get_oss_service()
    for r in records:
        if r.get("oss_key"):
            try:
                r["oss_url"] = oss_svc.get_presigned_url(r["oss_key"], expires=3600)
            except Exception as e:
                logger.warning(f"生成预签名 URL 失败: {r['oss_key']}, {e}")
                r["oss_url"] = ""
    return records


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

    # 获取 kb_name 用于 OSS 路径
    job = get_job_repository().get(job_id)
    if not job:
        raise NotFoundError("任务不存在")
    from app.db import get_kb_repository
    kb = get_kb_repository().get_by_id(job["kb_id"])
    kb_name = kb["name"] if kb else "unknown"
    file_name = get_file_repository().get_by_id(job["file_id"])
    file_name_str = file_name["file_name"] if file_name else "unknown"

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "png"
    chunk_id = chunk["chunk_id"]
    # 占位符 hex 作为 OSS 路径唯一 ID，与知识库文件生命周期解耦
    placeholder_hex = uuid.uuid4().hex[:8]
    placeholder = f"<<IMAGE:{placeholder_hex}>>"
    try:
        oss_key = get_oss_service().upload_file(
            f"conversation_assets/{placeholder_hex}",
            f"image.{ext}",
            file_content,
        )
    except Exception as e:
        raise ExternalServiceError(f"OSS 上传失败: {e}") from e

    img_repo = get_chunk_image_repository()
    sort_order = len(img_repo.get_by_chunk(chunk_id))
    record = img_repo.insert(
        chunk_id=chunk_id,
        job_id=job_id,
        placeholder=placeholder,
        oss_key=oss_key,
        page=page,
        sort_order=sort_order,
    )

    # 生成预签名 URL 供前端立即显示
    try:
        record["oss_url"] = get_oss_service().get_presigned_url(oss_key, expires=3600)
    except Exception as e:
        logger.warning(f"生成预签名 URL 失败: {oss_key}, {e}")
        record["oss_url"] = ""

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

    placeholder = record.get("placeholder", "")
    if placeholder:
        chunk_repo = get_chunk_repository()
        chunk = chunk_repo.get_by_job_and_index(job_id, chunk_index)
        if chunk:
            new_content = (chunk.get("current_content") or "").replace(placeholder, "")
            chunk_repo.update_content_by_index(job_id, chunk_index, new_content, status="edited")


def resolve_image_placeholders(placeholders: list) -> dict:
    """
    批量将占位符解析为预签名 URL。
    返回 {placeholder: presigned_url} 字典，找不到的占位符不包含在结果里。
    """
    if not placeholders:
        return {}
    img_repo = get_chunk_image_repository()
    records = img_repo.get_by_placeholders(placeholders)
    oss_svc = get_oss_service()
    result = {}
    for r in records:
        ph = r.get("placeholder", "")
        ok = r.get("oss_key", "")
        if ph and ok:
            try:
                result[ph] = oss_svc.get_presigned_url(ok, expires=3600)
            except Exception as e:
                logger.warning(f"resolve_image_placeholders: 生成预签名 URL 失败 {ok}: {e}")
    return result
