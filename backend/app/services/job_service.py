# -*- coding: utf-8 -*-
"""
任务业务逻辑
run_job_pipeline：切分 → 写 chunk → embedding → 写 Milvus → done
"""
import asyncio
import logging
from typing import Optional

from app.core.exceptions import NotFoundError
from app.db import get_job_repository, get_chunk_repository, get_file_repository, get_chunk_image_repository

logger = logging.getLogger(__name__)


# ── 查询 ──────────────────────────────────────────────────────────────────────

def list_jobs(kb_name: str, limit: int = 200) -> dict:
    from app.db import get_kb_repository
    kb = get_kb_repository().get_by_name(kb_name)
    if not kb:
        return {"jobs": [], "total": 0}
    jobs = get_job_repository().list_by_kb(kb["id"], limit=limit)
    return {"jobs": jobs, "total": len(jobs)}


def get_job_detail(job_id: str) -> dict:
    job = get_job_repository().get(job_id)
    if not job:
        raise NotFoundError("任务不存在")
    return {"job": job}


# ── 流水线 ────────────────────────────────────────────────────────────────────

async def run_job_pipeline(
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
    sync_graph: bool = False,
    excel_rows_per_chunk: int = 50,
) -> None:
    """
    完整流水线：
    pending → chunking → chunked → embedding → done
    任何阶段失败 → error
    如果 sync_graph=True，向量化完成后同步到知识图谱
    """
    job_repo = get_job_repository()
    file_repo = get_file_repository()

    try:
        # ── Step 1: 切分 ──────────────────────────────────────────────────────
        job_repo.update_status(job_id, "chunking", stage="正在切分文档")
        file_repo.update_status(file_id, "processing")

        file_content = await asyncio.to_thread(_download_file, oss_key)

        if image_mode:
            chunks, image_records = await asyncio.to_thread(
                _parse_image_mode,
                file_content=file_content,
                job_id=job_id,
                kb_name=kb_name,
                file_name=file_name,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                image_dpi=image_dpi,
            )
        else:
            chunks = await asyncio.to_thread(
                _parse_text_mode,
                file_content=file_content,
                file_name=file_name,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                excel_rows_per_chunk=excel_rows_per_chunk,
            )
            image_records = []

        # ── Step 2: 写 chunk 到 PG ────────────────────────────────────────────
        # 先清理旧切片的 OSS 图片（bulk_insert 内部会 DELETE 旧 chunk，CASCADE 删 PG 图片记录，但 OSS 需手动清）
        from app.services.chunk_service import _delete_job_images_from_oss
        await asyncio.to_thread(_delete_job_images_from_oss, job_id)

        # 注入 auto_inject 元数据字段（如 title = 文件名前缀）
        from app.db import get_kb_repository
        kb = get_kb_repository().get_by_id(kb_id)
        metadata_fields = kb.get("metadata_fields") or [] if kb else []
        inject_map = {}
        for mf in metadata_fields:
            if mf.get("auto_inject") == "filename_prefix":
                inject_map[mf["key"]] = file_name.rsplit(".", 1)[0]
        if inject_map:
            for chunk in chunks:
                meta = chunk.get("metadata") or {}
                meta.update(inject_map)
                chunk["metadata"] = meta
            logger.info(f"[pipeline] 注入元数据: {inject_map}")

        chunk_repo = get_chunk_repository()
        if image_mode:
            await asyncio.to_thread(chunk_repo.bulk_insert_with_ids, job_id, file_name, chunks)
        else:
            await asyncio.to_thread(chunk_repo.bulk_insert, job_id, file_name, chunks)

        if image_records:
            await asyncio.to_thread(get_chunk_image_repository().bulk_insert, image_records)

        chunk_count = len(chunks)
        job_repo.update_status(job_id, "chunked", stage="切分完成，可审查切片后手动向量化", chunk_count=chunk_count, progress=50)
        file_repo.update_status(file_id, "chunked")
        logger.info(f"[pipeline] job_id={job_id} 切分完成，共 {chunk_count} 个切片，等待手动向量化")

    except Exception as e:
        logger.error(f"[pipeline] job_id={job_id} 失败: {e}")
        job_repo.update_status(job_id, "error", stage="处理失败", error_msg=str(e))
        file_repo.update_status(file_id, "error", error_msg=str(e))


# ── 手动触发向量化（切片编辑后重新上传）─────────────────────────────────────

async def upsert_job_to_milvus(job_id: str) -> dict:
    """将已切分的 job 重新向量化写入 Milvus（用于切片编辑后手动触发）"""
    job_repo = get_job_repository()
    job = job_repo.get(job_id)
    if not job:
        raise NotFoundError("任务不存在")

    from app.db import get_kb_repository, get_file_repository
    file_record = get_file_repository().get_by_id(job["file_id"])
    kb = get_kb_repository().get_by_id(job["kb_id"])
    if not file_record or not kb:
        raise NotFoundError("文件或知识库不存在")

    chunk_repo = get_chunk_repository()
    pg_chunks = chunk_repo.get_by_job(job_id)
    if not pg_chunks:
        raise NotFoundError("该 job 暂无切片数据")

    milvus_chunks = [
        {
            "chunk_id":    c["chunk_id"],
            "job_id":      job_id,
            "file_name":   file_record["file_name"],
            "chunk_index": c["chunk_index"],
            "content":     c["current_content"],
            "metadata":    c.get("metadata") or {},
        }
        for c in pg_chunks if c.get("current_content")
    ]

    from app.services.milvus_service import get_milvus_service
    milvus_svc = get_milvus_service()
    milvus_svc.get_or_create_collection(
        kb["name"], dim=kb["vector_dim"],
        kb_type=kb.get("kb_type", "standard"),
        image_vector_dim=kb.get("retrieval_config", {}).get("image_vector_dim", 1024),
    )

    if kb.get("kb_type") == "multimodal":
        result = await asyncio.to_thread(
            _upsert_multimodal_chunks, kb, job_id, milvus_chunks
        )
    else:
        result = await asyncio.to_thread(
            _upsert_chunks_in_batches,
            milvus_svc, kb, milvus_chunks,
        )

    failed_batches = result.get("failed_batches", [])
    if failed_batches:
        # 部分批次失败：job 保持 chunked，提示用户重试（已写入的批次 upsert 幂等，重试安全）
        total_batches = result.get("total_batches", "?")
        stage = (
            f"部分向量化失败（{len(failed_batches)}/{total_batches} 批次），"
            f"已写入 {result['upsert_count']} 条，请重新点击「上传向量库」重试"
        )
        get_job_repository().update_status(job_id, "chunked", stage=stage)
        logger.warning(f"[upsert] job_id={job_id} 部分失败，失败批次: {failed_batches}")
        return result

    job_repo.mark_vectorized(job_id)

    # 如果用户选择了"同步到知识图谱"，向量化完成后同步到 KT
    if file_record.get("sync_graph"):
        try:
            from app.services.kg_graph_sync_service import get_kg_graph_sync_service
            kg_sync = get_kg_graph_sync_service()
            chunk_vectors = {
                c["chunk_id"]: c.get("dense") or c.get("embedding", [])
                for c in milvus_chunks
            }
            await kg_sync.sync_chunks_to_graph(
                job_id=job_id,
                kb_name=kb["name"],
                file_name=file_record["file_name"],
                chunks=[
                    {
                        "chunk_id": c["chunk_id"],
                        "content": c["current_content"],
                        "chunk_index": c["chunk_index"],
                        "vector": chunk_vectors.get(c["chunk_id"], [])
                    }
                    for c in pg_chunks if c.get("current_content")
                ],
            )
            logger.info(f"[pipeline] 图谱同步完成 job_id={job_id}")
        except Exception as e:
            logger.error(f"[pipeline] 图谱同步失败 job_id={job_id}: {e}")

    return result


# ── 内部：分批向量化写入（大文件容错）────────────────────────────────────────

# 每次向量化+写入的切片数，控制单次 API 调用量和内存占用
_UPSERT_BATCH = 100

def _upsert_chunks_in_batches(milvus_svc, kb: dict, chunks: list) -> dict:
    """
    将 chunks 分批 embed + upsert，每批独立重试。
    单批网络失败最多重试 5 次（指数退避），不影响其他批次已写入的数据。

    原子性说明：
    - Milvus 不支持事务，无法真正回滚。
    - 失败时不抛异常，让 job 保持 chunked 状态（未 mark_vectorized）。
    - upsert 按 chunk_id 幂等覆盖，用户重试时已写入的批次安全重跑，最终收敛到完整状态。
    - 返回 failed_count > 0 时，调用方应更新 job stage 提示用户重试。
    """
    from app.services.embedding_service import get_embedding_service
    import re
    import time

    _IMAGE_PH_RE = re.compile(r'<<IMAGE:[0-9a-f]+>>')

    kb_name = kb["name"]
    vector_dim = kb["vector_dim"]
    embedding_model = kb.get("embedding_model")
    metadata_fields = kb.get("metadata_fields") or []

    fulltext_keys = [
        mf["key"] for mf in metadata_fields
        if mf.get("fulltext") and mf.get("key")
    ]

    embedding_svc = get_embedding_service()
    original_model = embedding_svc.model
    if embedding_model and embedding_model != original_model:
        embedding_svc.model = embedding_model

    total_upserted = 0
    failed_batches = []
    total_batches = (len(chunks) + _UPSERT_BATCH - 1) // _UPSERT_BATCH

    try:
        for batch_start in range(0, len(chunks), _UPSERT_BATCH):
            batch = chunks[batch_start: batch_start + _UPSERT_BATCH]
            batch_no = batch_start // _UPSERT_BATCH + 1

            texts = []
            for c in batch:
                clean = _IMAGE_PH_RE.sub('', c["content"]).strip()
                if fulltext_keys:
                    meta = c.get("metadata") or {}
                    prefix = "\n".join(
                        f"{k}：{meta[k]}" for k in fulltext_keys if meta.get(k)
                    )
                    texts.append(f"{prefix}\n\n{clean}" if prefix else clean)
                else:
                    texts.append(clean)

            success = False
            for attempt in range(5):
                try:
                    vectors = embedding_svc.embed_texts(texts, dimension=vector_dim)
                    if len(vectors) != len(batch):
                        raise RuntimeError(f"向量数量不匹配: {len(vectors)} vs {len(batch)}")

                    data = []
                    for chunk, vec, indexed_content in zip(batch, vectors, texts):
                        row = {
                            "chunk_id":    chunk["chunk_id"],
                            "job_id":      chunk.get("job_id", ""),
                            "file_name":   chunk.get("file_name", ""),
                            "chunk_index": int(chunk.get("chunk_index", 0)),
                            "content":     indexed_content,
                            "dense":       vec,
                        }
                        for k, v in (chunk.get("metadata") or {}).items():
                            if k not in row:
                                row[k] = v
                        data.append(row)

                    res = milvus_svc.client.upsert(collection_name=kb_name, data=data)
                    total_upserted += res.get("upsert_count", len(data))
                    logger.info(f"[upsert] 批次 {batch_no}/{total_batches} 完成，累计 {total_upserted} 条")
                    success = True
                    break
                except Exception as e:
                    wait = min(2 ** attempt * 2, 60)
                    if attempt < 4:
                        logger.warning(f"[upsert] 批次 {batch_no} 第 {attempt+1} 次失败，{wait}s 后重试: {e}")
                        time.sleep(wait)
                    else:
                        logger.error(f"[upsert] 批次 {batch_no} 最终失败: {e}")
                        failed_batches.append(batch_no)

    finally:
        embedding_svc.model = original_model

    return {
        "upsert_count": total_upserted,
        "failed_batches": failed_batches,
        "total_batches": total_batches,
    }


# ── 内部：文件下载 ────────────────────────────────────────────────────────────

def _download_file(oss_key: str) -> bytes:
    from app.services.oss_service import get_oss_service
    return get_oss_service().get_object_bytes(oss_key)


# ── 内部：图文模式切分 ────────────────────────────────────────────────────────

def _parse_image_mode(
    file_content: bytes,
    job_id: str,
    kb_name: str,
    file_name: str,
    chunk_size: int,
    chunk_overlap: int,
    image_dpi: int,
):
    from app.services.doc_image_parser import parse_pdf, parse_word
    ext = file_name.lower().rsplit(".", 1)[-1]
    if ext == "pdf":
        return parse_pdf(
            file_content=file_content,
            job_id=job_id,
            collection=kb_name,
            file_name=file_name,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            image_dpi=image_dpi,
        )
    elif ext in ("docx", "doc"):
        return parse_word(
            file_content=file_content,
            job_id=job_id,
            collection=kb_name,
            file_name=file_name,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
    else:
        raise ValueError(f"图文模式不支持格式: {ext}")


# ── 内部：标准模式切分 ────────────────────────────────────────────────────────

def _parse_text_mode(
    file_content: bytes,
    file_name: str,
    chunk_size: int,
    chunk_overlap: int,
    excel_rows_per_chunk: int = 50,
) -> list:
    """
    标准模式：提取文本 → chunk_splitter 切分
    支持 PDF / DOCX / TXT / MD / XLSX / XLS
    """
    from app.services.chunk_splitter import split_text_with_metadata, split_excel

    ext = file_name.lower().rsplit(".", 1)[-1]

    # Excel 走专用切分逻辑
    if ext in ("xlsx", "xls"):
        return split_excel(
            file_content=file_content,
            file_name=file_name,
            rows_per_chunk=excel_rows_per_chunk,
            base_metadata={"file_name": file_name, "source": ext},
        )

    text = _extract_text(file_content, ext, file_name)
    return split_text_with_metadata(
        text=text,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        base_metadata={"file_name": file_name, "source": ext},
    )


def _extract_text(file_content: bytes, ext: str, file_name: str) -> str:
    if ext == "pdf":
        import fitz  # PyMuPDF
        doc = fitz.open(stream=file_content, filetype="pdf")
        return "\n\n".join(page.get_text() for page in doc)
    elif ext in ("docx", "doc"):
        import io
        from docx import Document
        doc = Document(io.BytesIO(file_content))
        return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
    elif ext in ("txt", "md"):
        for enc in ("utf-8", "gbk", "utf-16"):
            try:
                return file_content.decode(enc)
            except UnicodeDecodeError:
                continue
        return file_content.decode("utf-8", errors="ignore")
    else:
        # 尝试 UTF-8 文本
        return file_content.decode("utf-8", errors="ignore")


# ── 多模态向量化 ──────────────────────────────────────────────────────────────

def _upsert_multimodal_chunks(kb: dict, job_id: str, milvus_chunks: list) -> dict:
    """
    多模态知识库向量化：
    - 文本向量：qwen3-vl-embedding embed_text（与图片在同一语义空间）
    - 图片向量：qwen3-vl-embedding embed_image（nullable，无图片切片设为 None）
    
    优化：向量化前剥离图片占位符（<<IMAGE:xxx>>），避免污染向量和 BM25。
    """
    import re
    from app.services.multimodal_embedding_service import get_multimodal_embedding_service
    from app.services.milvus_service import get_milvus_service
    from app.services.oss_service import get_oss_service
    from app.db import get_chunk_image_repository

    _IMAGE_PH_RE = re.compile(r'<<IMAGE:[0-9a-f]+>>')
    
    mm_svc = get_multimodal_embedding_service()
    milvus_svc = get_milvus_service()
    oss_svc = get_oss_service()
    img_repo = get_chunk_image_repository()
    # 多模态 kb 的 vector_dim 已在创建时与 image_vector_dim 强制对齐
    image_dim = kb.get("vector_dim", 1024)
    kb_name = kb["name"]

    # 批量查询所有切片的图片记录
    chunk_ids = [c["chunk_id"] for c in milvus_chunks]
    img_records = img_repo.get_by_chunk_ids(chunk_ids) if chunk_ids else []
    # chunk_id → 第一张图片的 oss_key
    chunk_img_map: dict = {}
    for r in img_records:
        cid = r["chunk_id"]
        if cid not in chunk_img_map:
            chunk_img_map[cid] = r["oss_key"]

    data = []
    for chunk in milvus_chunks:
        content = chunk["content"]
        if not content:
            continue

        # 剥离图片占位符（向量化和 BM25 不感知占位符）
        clean_content = _IMAGE_PH_RE.sub('', content).strip()

        # 文本向量（qwen3-vl-embedding，与图片同语义空间）
        try:
            text_vec = mm_svc.embed_text(clean_content, dimension=image_dim)
        except Exception as e:
            logger.error(f"[MultimodalUpsert] 文本向量化失败 chunk_id={chunk['chunk_id']}: {e}")
            continue

        # 图片向量（有图片则生成，否则填零向量，IP 相似度下零向量得分为 0 不影响排名）
        image_vec = [0.0] * image_dim
        oss_key = chunk_img_map.get(chunk["chunk_id"])
        if oss_key:
            try:
                img_url = oss_svc.get_presigned_url(oss_key, expires=600)
                vec = mm_svc.embed_image(img_url, dimension=image_dim)
                if vec:
                    image_vec = vec
            except Exception as e:
                logger.warning(f"[MultimodalUpsert] 图片向量化失败，填零向量: {e}")

        row = {
            "chunk_id":    chunk["chunk_id"],
            "job_id":      job_id,
            "file_name":   chunk.get("file_name", ""),
            "chunk_index": int(chunk.get("chunk_index", 0)),
            "content":     clean_content,  # Milvus 存 clean 版本（不含占位符），BM25 基于此
            "dense":       text_vec,
            "image_dense": image_vec,
        }
        for k, v in (chunk.get("metadata") or {}).items():
            if k not in row:
                row[k] = v
        data.append(row)

    if not data:
        return {"upsert_count": 0}

    batch_size = 50  # 多模态向量化较慢，批次小一点
    total = 0
    for i in range(0, len(data), batch_size):
        batch = data[i: i + batch_size]
        res = milvus_svc.client.upsert(collection_name=kb_name, data=batch)
        total += res.get("upsert_count", len(batch))

    logger.info(f"[MultimodalUpsert] upsert {total} 条到 {kb_name}")
    return {"upsert_count": total}
