# -*- coding: utf-8 -*-
"""
切片仓储
表：knowledge_chunk（当前内容）+ knowledge_chunk_origin（原始内容，只写一次）
chunk_id: UUID
"""
import json
import uuid
import logging
from typing import Any, Dict, List, Optional
from app.db.base_repository import BaseRepository

logger = logging.getLogger(__name__)


class ChunkRepository(BaseRepository):

    # ── 写入 ──────────────────────────────────────────────────────────────────

    def bulk_insert(self, job_id: str, file_name: str, chunks: List[Dict[str, Any]]):
        """
        标准模式批量写入。
        chunks 格式：[{"page_content": str, "metadata": dict}, ...]
        chunk_id = UUID
        """
        if not chunks:
            return
        self._execute_sql("DELETE FROM knowledge_chunk WHERE job_id = %s", (job_id,))

        chunk_params, origin_params = [], []
        for idx, chunk in enumerate(chunks):
            chunk_id = str(uuid.uuid4())
            content = chunk.get("page_content") or chunk.get("content") or ""
            metadata = json.dumps(chunk.get("metadata") or {}, ensure_ascii=False)
            chunk_params.append((chunk_id, job_id, idx, content, metadata))
            origin_params.append((chunk_id, content))

        self._execute_many(
            "INSERT INTO knowledge_chunk(id, job_id, chunk_index, content, metadata) VALUES (%s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING",
            chunk_params,
        )
        self._execute_many(
            "INSERT INTO knowledge_chunk_origin(chunk_id, content) VALUES (%s, %s) ON CONFLICT (chunk_id) DO NOTHING",
            origin_params,
        )

    def bulk_insert_with_ids(self, job_id: str, file_name: str, chunks: List[Dict[str, Any]]):
        """
        图文模式专用：使用 parse_pdf/parse_word 返回的 UUID chunk_id。
        chunks 格式：[{"chunk_id": str(UUID), "content": str, "metadata": dict, "chunk_index": int}, ...]
        """
        if not chunks:
            return
        self._execute_sql("DELETE FROM knowledge_chunk WHERE job_id = %s", (job_id,))

        chunk_params, origin_params = [], []
        for enumerate_idx, chunk in enumerate(chunks):
            chunk_id = str(chunk.get("chunk_id") or uuid.uuid4())
            chunk_index = chunk.get("chunk_index", enumerate_idx)
            content = chunk.get("content") or ""
            metadata = json.dumps(chunk.get("metadata") or {}, ensure_ascii=False)
            chunk_params.append((chunk_id, job_id, chunk_index, content, metadata))
            origin_params.append((chunk_id, content))

        self._execute_many(
            "INSERT INTO knowledge_chunk(id, job_id, chunk_index, content, metadata) VALUES (%s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING",
            chunk_params,
        )
        self._execute_many(
            "INSERT INTO knowledge_chunk_origin(chunk_id, content) VALUES (%s, %s) ON CONFLICT (chunk_id) DO NOTHING",
            origin_params,
        )

    # ── 查询 ──────────────────────────────────────────────────────────────────

    def get_by_job(self, job_id: str) -> List[Dict[str, Any]]:
        rows = self._execute_select(
            "SELECT * FROM knowledge_chunk WHERE job_id = %s ORDER BY chunk_index ASC",
            (job_id,),
        )
        return [self._normalize(r) for r in rows]

    def get_by_job_and_index(self, job_id: str, chunk_index: int) -> Optional[Dict[str, Any]]:
        rows = self._execute_select(
            "SELECT * FROM knowledge_chunk WHERE job_id = %s AND chunk_index = %s LIMIT 1",
            (job_id, chunk_index),
        )
        return self._normalize(rows[0]) if rows else None

    def get_by_id(self, chunk_id: str) -> Optional[Dict[str, Any]]:
        rows = self._execute_select(
            "SELECT * FROM knowledge_chunk WHERE id = %s LIMIT 1", (chunk_id,)
        )
        return self._normalize(rows[0]) if rows else None

    def get_by_ids(self, chunk_ids: List[str]) -> List[Dict[str, Any]]:
        """批量查询切片（用于检索后回填 PG 原始内容）"""
        if not chunk_ids:
            return []
        placeholders = ",".join(["%s"] * len(chunk_ids))
        rows = self._execute_select(
            f"SELECT * FROM knowledge_chunk WHERE id IN ({placeholders})",
            tuple(chunk_ids),
        )
        return [self._normalize(r) for r in rows]

    def list_all_job_ids(self) -> List[str]:
        rows = self._execute_select("SELECT DISTINCT job_id FROM knowledge_chunk")
        return [str(r["job_id"]) for r in rows if r.get("job_id")]

    def has_chunks(self, job_id: str) -> bool:
        rows = self._execute_select(
            "SELECT COUNT(*) AS cnt FROM knowledge_chunk WHERE job_id = %s", (job_id,)
        )
        return int(rows[0]["cnt"]) > 0 if rows else False

    # ── 更新 ──────────────────────────────────────────────────────────────────

    def update_content_by_index(self, job_id: str, chunk_index: int, content: str, status: str = "edited"):
        is_modified = status != "original"
        self._execute_sql(
            "UPDATE knowledge_chunk SET content = %s, is_modified = %s, updated_at = NOW() WHERE job_id = %s AND chunk_index = %s",
            (content, is_modified, job_id, chunk_index),
        )

    def update_content(self, chunk_id: str, content: str, status: str = "edited"):
        is_modified = status != "original"
        self._execute_sql(
            "UPDATE knowledge_chunk SET content = %s, is_modified = %s, updated_at = NOW() WHERE id = %s",
            (content, is_modified, chunk_id),
        )

    # ── 撤回（从 origin 表恢复）──────────────────────────────────────────────

    def revert_chunk_by_index(self, job_id: str, chunk_index: int):
        self._execute_sql(
            """
            UPDATE knowledge_chunk c
            SET content = o.content, is_modified = FALSE, updated_at = NOW()
            FROM knowledge_chunk_origin o
            WHERE c.id = o.chunk_id
              AND c.job_id = %s AND c.chunk_index = %s
            """,
            (job_id, chunk_index),
        )

    def revert_chunk(self, chunk_id: str):
        self._execute_sql(
            """
            UPDATE knowledge_chunk c
            SET content = o.content, is_modified = FALSE, updated_at = NOW()
            FROM knowledge_chunk_origin o
            WHERE c.id = o.chunk_id AND c.id = %s
            """,
            (chunk_id,),
        )

    def revert_job(self, job_id: str):
        self._execute_sql(
            """
            UPDATE knowledge_chunk c
            SET content = o.content, is_modified = FALSE, updated_at = NOW()
            FROM knowledge_chunk_origin o
            WHERE c.id = o.chunk_id AND c.job_id = %s
            """,
            (job_id,),
        )

    def revert_all(self):
        self._execute_sql(
            """
            UPDATE knowledge_chunk c
            SET content = o.content, is_modified = FALSE, updated_at = NOW()
            FROM knowledge_chunk_origin o
            WHERE c.id = o.chunk_id
            """
        )

    # ── 删除 ──────────────────────────────────────────────────────────────────

    def delete_by_job(self, job_id: str):
        # ON DELETE CASCADE 会自动删 origin 和 image
        self._execute_sql("DELETE FROM knowledge_chunk WHERE job_id = %s", (job_id,))

    def delete_chunk(self, chunk_id: str):
        self._execute_sql("DELETE FROM knowledge_chunk WHERE id = %s", (chunk_id,))

    # ── 序列化 ────────────────────────────────────────────────────────────────

    @staticmethod
    def _normalize(row: Dict[str, Any]) -> Dict[str, Any]:
        meta_raw = row.get("metadata")
        metadata = {}
        if isinstance(meta_raw, str) and meta_raw.strip():
            try:
                metadata = json.loads(meta_raw)
            except Exception:
                metadata = {}
        elif isinstance(meta_raw, dict):
            metadata = meta_raw
        return {
            "chunk_id": str(row["id"]),
            "job_id": str(row["job_id"]),
            "chunk_index": row.get("chunk_index"),
            # 兼容旧接口：current_content / original_content
            "current_content": row.get("content", ""),
            "original_content": row.get("content", ""),  # 查询时不 JOIN origin，保持接口兼容
            "content": row.get("content", ""),
            "is_modified": bool(row.get("is_modified", False)),
            "status": "edited" if row.get("is_modified") else "original",
            "metadata": metadata,
            "updated_at": str(row["updated_at"]) if row.get("updated_at") else None,
        }


_instance: Optional[ChunkRepository] = None


def get_chunk_repository() -> ChunkRepository:
    global _instance
    if _instance is None:
        _instance = ChunkRepository()
    return _instance
