# -*- coding: utf-8 -*-
"""
切片图片仓储
表：knowledge_chunk_image
"""
import logging
from typing import Any, Dict, List, Optional
from app.db.base_repository import BaseRepository

logger = logging.getLogger(__name__)


class ChunkImageRepository(BaseRepository):

    def bulk_insert(self, records: List[Dict[str, Any]]):
        if not records:
            return
        # chunk_image 表无 job_id 字段，通过 chunk_id → knowledge_chunk → knowledge_job 关联
        params_list = [
            (r["chunk_id"], r.get("placeholder", ""), r.get("oss_key", ""), r.get("page"), r.get("sort_order", 0))
            for r in records
        ]
        self._execute_many(
            "INSERT INTO knowledge_chunk_image(chunk_id, placeholder, oss_key, page, sort_order) VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
            params_list,
        )

    def insert(
        self,
        *,
        chunk_id: str,
        job_id: str,
        placeholder: str,
        oss_key: str,
        oss_url: Optional[str] = None,
        page: Optional[int] = None,
        sort_order: int = 0,
    ) -> Dict[str, Any]:
        rows = self._execute_returning(
            "INSERT INTO knowledge_chunk_image(chunk_id, placeholder, oss_key, page, sort_order) VALUES (%s, %s, %s, %s, %s) RETURNING *",
            (chunk_id, placeholder, oss_key, page, sort_order),
        )
        return self._normalize(rows[0]) if rows else {}

    def get_by_id(self, record_id: str) -> Optional[Dict[str, Any]]:
        rows = self._execute_select(
            "SELECT * FROM knowledge_chunk_image WHERE id = %s LIMIT 1", (record_id,)
        )
        return self._normalize(rows[0]) if rows else None

    def get_by_chunk(self, chunk_id: str) -> List[Dict[str, Any]]:
        rows = self._execute_select(
            "SELECT * FROM knowledge_chunk_image WHERE chunk_id = %s ORDER BY sort_order ASC, created_at ASC",
            (chunk_id,),
        )
        return [self._normalize(r) for r in rows]

    def get_by_chunk_ids(self, chunk_ids: List[str]) -> List[Dict[str, Any]]:
        if not chunk_ids:
            return []
        placeholders = ",".join(["%s"] * len(chunk_ids))
        rows = self._execute_select(
            f"SELECT * FROM knowledge_chunk_image WHERE chunk_id IN ({placeholders}) ORDER BY chunk_id, sort_order ASC",
            tuple(chunk_ids),
        )
        return [self._normalize(r) for r in rows]

    def get_by_placeholders(self, placeholders: List[str]) -> List[Dict[str, Any]]:
        if not placeholders:
            return []
        ph_params = ",".join(["%s"] * len(placeholders))
        rows = self._execute_select(
            f"SELECT * FROM knowledge_chunk_image WHERE placeholder IN ({ph_params})",
            tuple(placeholders),
        )
        return [self._normalize(r) for r in rows]

    def get_oss_keys_by_job(self, job_id: str) -> List[str]:
        """通过 job_id 关联 chunk 查图片 oss_key"""
        rows = self._execute_select(
            """
            SELECT ci.oss_key FROM knowledge_chunk_image ci
            JOIN knowledge_chunk c ON ci.chunk_id = c.id
            WHERE c.job_id = %s AND ci.oss_key IS NOT NULL AND ci.oss_key != ''
            """,
            (job_id,),
        )
        return [r["oss_key"] for r in rows if r.get("oss_key")]

    def get_oss_keys_by_file_id(self, file_id: str) -> List[str]:
        """通过 file_id 关联 job → chunk 查图片 oss_key"""
        rows = self._execute_select(
            """
            SELECT ci.oss_key FROM knowledge_chunk_image ci
            JOIN knowledge_chunk c ON ci.chunk_id = c.id
            JOIN knowledge_job j ON c.job_id = j.id
            WHERE j.file_id = %s AND ci.oss_key IS NOT NULL AND ci.oss_key != ''
            """,
            (file_id,),
        )
        return [r["oss_key"] for r in rows if r.get("oss_key")]

    def delete(self, record_id: str):
        self._execute_sql("DELETE FROM knowledge_chunk_image WHERE id = %s", (record_id,))

    def delete_by_chunk(self, chunk_id: str):
        self._execute_sql("DELETE FROM knowledge_chunk_image WHERE chunk_id = %s", (chunk_id,))

    def delete_by_job(self, job_id: str):
        self._execute_sql(
            """
            DELETE FROM knowledge_chunk_image
            WHERE chunk_id IN (SELECT id FROM knowledge_chunk WHERE job_id = %s)
            """,
            (job_id,),
        )

    @staticmethod
    def _normalize(row: Dict[str, Any]) -> Dict[str, Any]:
        oss_key = row.get("oss_key") or ""
        return {
            "id": str(row["id"]),
            "chunk_id": str(row["chunk_id"]),
            "placeholder": row.get("placeholder", ""),
            "oss_key": oss_key,
            "oss_url": "",   # 由 service 层按需生成预签名 URL，repository 不依赖 oss_service
            "page": row.get("page"),
            "sort_order": row.get("sort_order", 0),
            "created_at": str(row["created_at"]) if row.get("created_at") else None,
        }


_instance: Optional[ChunkImageRepository] = None


def get_chunk_image_repository() -> ChunkImageRepository:
    global _instance
    if _instance is None:
        _instance = ChunkImageRepository()
    return _instance
