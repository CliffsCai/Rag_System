# -*- coding: utf-8 -*-
"""
切片存储仓储
表：knowledge_ns.knowledge_chunk_store
存储从 ChunkFileUrl（JSONL）下载的切片，支持编辑、LLM清洗和撤回（恢复原始内容）
"""

import json
import logging
from typing import Any, Dict, List, Optional

from app.db.base_repository import BaseRepository

logger = logging.getLogger(__name__)

CHUNK_TABLE = "knowledge_chunk_store"


class ChunkRepository(BaseRepository):

    def __init__(self):
        super().__init__()
        self.table = CHUNK_TABLE
        self._ensure_table()

    def _ensure_table(self):
        ref = self._table_ref(self.table)
        sql = f"""
        CREATE TABLE IF NOT EXISTS {ref} (
            chunk_id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL,
            file_name TEXT,
            chunk_index INTEGER,
            original_content TEXT,
            current_content TEXT,
            metadata JSONB,
            status TEXT DEFAULT 'original',
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_chunk_store_job_id
            ON {ref} (job_id);
        """
        self._execute_sql(sql)

    def bulk_insert_with_ids(self, job_id: str, file_name: str, chunks: List[Dict[str, Any]]):
        """
        图文模式专用：直接使用 parse_pdf/parse_word 返回的 chunk_id，
        chunk_index 也用 chunk_id 末尾的序号，保证与 image_records 一致。
        chunks 格式：[{"chunk_id": str, "content": str, "metadata": dict}, ...]
        """
        if not chunks:
            return
        ref = self._table_ref(self.table)
        self._execute_sql(
            f"DELETE FROM {ref} WHERE job_id = '{self._sql_escape(job_id)}';"
        )
        for enumerate_idx, chunk in enumerate(chunks):
            chunk_id = chunk.get("chunk_id") or f"{job_id}_{enumerate_idx}"
            # chunk_index 从 chunk_id 末尾取，保证和 image_records 里的 chunk_id 对应
            try:
                chunk_index = int(chunk_id.rsplit("_", 1)[-1])
            except (ValueError, IndexError):
                chunk_index = enumerate_idx
            content = chunk.get("content") or ""
            metadata = chunk.get("metadata") or {}
            meta_json = json.dumps(metadata, ensure_ascii=False)
            sql = f"""
            INSERT INTO {ref}(
                chunk_id, job_id, file_name, chunk_index,
                original_content, current_content, metadata, status, created_at, updated_at
            ) VALUES (
                '{self._sql_escape(chunk_id)}',
                '{self._sql_escape(job_id)}',
                '{self._sql_escape(file_name)}',
                {chunk_index},
                '{self._sql_escape(content)}',
                '{self._sql_escape(content)}',
                '{self._sql_escape(meta_json)}'::jsonb,
                'original',
                NOW(), NOW()
            )
            ON CONFLICT (chunk_id) DO UPDATE SET
                original_content = EXCLUDED.original_content,
                current_content = EXCLUDED.current_content,
                metadata = EXCLUDED.metadata,
                status = 'original',
                updated_at = NOW();
            """
            self._execute_sql(sql)

    def bulk_insert(self, job_id: str, file_name: str, chunks: List[Dict[str, Any]]):
        """从 JSONL 解析后批量写入，original_content 和 current_content 初始相同"""
        if not chunks:
            return
        ref = self._table_ref(self.table)
        # 先删除该 job 的旧数据（重新获取时覆盖）
        self._execute_sql(
            f"DELETE FROM {ref} WHERE job_id = '{self._sql_escape(job_id)}';"
        )
        for idx, chunk in enumerate(chunks):
            chunk_id = f"{job_id}_{idx}"
            content = chunk.get("page_content") or chunk.get("content") or ""
            metadata = chunk.get("metadata") or {}
            meta_json = json.dumps(metadata, ensure_ascii=False)
            sql = f"""
            INSERT INTO {ref}(
                chunk_id, job_id, file_name, chunk_index,
                original_content, current_content, metadata, status, created_at, updated_at
            ) VALUES (
                '{self._sql_escape(chunk_id)}',
                '{self._sql_escape(job_id)}',
                '{self._sql_escape(file_name)}',
                {idx},
                '{self._sql_escape(content)}',
                '{self._sql_escape(content)}',
                '{self._sql_escape(meta_json)}'::jsonb,
                'original',
                NOW(), NOW()
            )
            ON CONFLICT (chunk_id) DO UPDATE SET
                original_content = EXCLUDED.original_content,
                current_content = EXCLUDED.current_content,
                metadata = EXCLUDED.metadata,
                status = 'original',
                updated_at = NOW();
            """
            self._execute_sql(sql)

    def get_by_job(self, job_id: str) -> List[Dict[str, Any]]:
        ref = self._table_ref(self.table)
        sql = f"""
        SELECT chunk_id, job_id, file_name, chunk_index,
               original_content, current_content, metadata::text AS metadata, status, updated_at
        FROM {ref}
        WHERE job_id = '{self._sql_escape(job_id)}'
        ORDER BY chunk_index ASC;
        """
        rows = self._execute_select(sql)
        return [self._normalize(r) for r in rows]

    def get_by_job_and_index(self, job_id: str, chunk_index: int) -> Optional[Dict[str, Any]]:
        ref = self._table_ref(self.table)
        sql = f"""
        SELECT chunk_id, job_id, file_name, chunk_index,
               original_content, current_content, metadata::text AS metadata, status, updated_at
        FROM {ref}
        WHERE job_id = '{self._sql_escape(job_id)}' AND chunk_index = {int(chunk_index)}
        LIMIT 1;
        """
        rows = self._execute_select(sql)
        return self._normalize(rows[0]) if rows else None

    def update_content_by_index(self, job_id: str, chunk_index: int, content: str, status: str = "edited"):
        ref = self._table_ref(self.table)
        sql = f"""
        UPDATE {ref}
        SET current_content = '{self._sql_escape(content)}',
            status = '{self._sql_escape(status)}',
            updated_at = NOW()
        WHERE job_id = '{self._sql_escape(job_id)}' AND chunk_index = {int(chunk_index)};
        """
        self._execute_sql(sql)

    def revert_chunk_by_index(self, job_id: str, chunk_index: int):
        """撤回指定 chunk_index 的切片到原始内容"""
        ref = self._table_ref(self.table)
        sql = f"""
        UPDATE {ref}
        SET current_content = original_content,
            status = 'original',
            updated_at = NOW()
        WHERE job_id = '{self._sql_escape(job_id)}' AND chunk_index = {int(chunk_index)};
        """
        self._execute_sql(sql)

    def revert_chunk(self, chunk_id: str):
        """撤回单个切片到原始内容"""
        ref = self._table_ref(self.table)
        sql = f"""
        UPDATE {ref}
        SET current_content = original_content,
            status = 'original',
            updated_at = NOW()
        WHERE chunk_id = '{self._sql_escape(chunk_id)}';
        """
        self._execute_sql(sql)

    def revert_job(self, job_id: str):
        """撤回整个 job 的所有切片到原始内容"""
        ref = self._table_ref(self.table)
        sql = f"""
        UPDATE {ref}
        SET current_content = original_content,
            status = 'original',
            updated_at = NOW()
        WHERE job_id = '{self._sql_escape(job_id)}';
        """
        self._execute_sql(sql)

    def revert_all(self):
        """撤回所有切片到原始内容"""
        ref = self._table_ref(self.table)
        sql = f"""
        UPDATE {ref}
        SET current_content = original_content,
            status = 'original',
            updated_at = NOW();
        """
        self._execute_sql(sql)

    def delete_chunk(self, chunk_id: str):
        ref = self._table_ref(self.table)
        sql = f"DELETE FROM {ref} WHERE chunk_id = '{self._sql_escape(chunk_id)}';"
        self._execute_sql(sql)

    def delete_by_job(self, job_id: str):
        ref = self._table_ref(self.table)
        sql = f"DELETE FROM {ref} WHERE job_id = '{self._sql_escape(job_id)}';"
        self._execute_sql(sql)

    def list_all_job_ids(self) -> list:
        """返回 chunk_store 中所有不重复的 job_id"""
        ref = self._table_ref(self.table)
        rows = self._execute_select(f"SELECT DISTINCT job_id FROM {ref};")
        return [r.get("job_id") for r in rows if r.get("job_id")]

    def has_chunks(self, job_id: str) -> bool:
        ref = self._table_ref(self.table)
        sql = f"SELECT COUNT(*) AS cnt FROM {ref} WHERE job_id = '{self._sql_escape(job_id)}';"
        rows = self._execute_select(sql)
        if not rows:
            return False
        try:
            return int(rows[0].get("cnt", 0)) > 0
        except Exception:
            return False

    @staticmethod
    def _normalize(row: Dict[str, Any]) -> Dict[str, Any]:
        meta_raw = row.get("metadata")
        metadata = {}
        if isinstance(meta_raw, str) and meta_raw.strip():
            try:
                metadata = json.loads(meta_raw)
            except Exception:
                metadata = {}
        return {
            "chunk_id": row.get("chunk_id"),
            "job_id": row.get("job_id"),
            "file_name": row.get("file_name"),
            "chunk_index": row.get("chunk_index"),
            "original_content": row.get("original_content"),
            "current_content": row.get("current_content"),
            "metadata": metadata,
            "status": row.get("status"),
            "updated_at": str(row.get("updated_at")) if row.get("updated_at") else None,
        }


_instance: Optional[ChunkRepository] = None


def get_chunk_repository() -> ChunkRepository:
    global _instance
    if _instance is None:
        _instance = ChunkRepository()
    return _instance
