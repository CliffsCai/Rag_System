# -*- coding: utf-8 -*-
"""
切片图片仓储
表：knowledge_ns.knowledge_chunk_image
存储切片与图片的一对多关联关系
"""

from urllib.parse import quote
import logging
import uuid
from typing import Any, Dict, List, Optional

from app.db.base_repository import BaseRepository

logger = logging.getLogger(__name__)

TABLE = "knowledge_chunk_image"


class ChunkImageRepository(BaseRepository):

    def __init__(self):
        super().__init__()
        self.table = TABLE

    def bulk_insert(self, records: List[Dict[str, Any]]):
        """批量插入图片记录（只存 oss_key，不存 oss_url）"""
        if not records:
            return
        ref = self._table_ref(self.table)
        for r in records:
            record_id = r.get("id") or str(uuid.uuid4())
            sql = f"""
            INSERT INTO {ref}(id, chunk_id, job_id, placeholder, oss_key, page, sort_order, created_at)
            VALUES (
                '{self._sql_escape(record_id)}',
                '{self._sql_escape(r["chunk_id"])}',
                '{self._sql_escape(r["job_id"])}',
                '{self._sql_escape(r["placeholder"])}',
                '{self._sql_escape(r.get("oss_key", ""))}',
                {r.get("page") if r.get("page") is not None else "NULL"},
                {r.get("sort_order", 0)},
                NOW()
            )
            ON CONFLICT (id) DO NOTHING;
            """
            self._execute_sql(sql)

    def insert(self, *, chunk_id: str, job_id: str, placeholder: str,
               oss_key: str, oss_url: Optional[str] = None,
               page: Optional[int] = None, sort_order: int = 0) -> Dict[str, Any]:
        """插入单条图片记录（oss_url 忽略，查询时动态生成）"""
        ref = self._table_ref(self.table)
        record_id = str(uuid.uuid4())
        sql = f"""
        INSERT INTO {ref}(id, chunk_id, job_id, placeholder, oss_key, page, sort_order, created_at)
        VALUES (
            '{self._sql_escape(record_id)}',
            '{self._sql_escape(chunk_id)}',
            '{self._sql_escape(job_id)}',
            '{self._sql_escape(placeholder)}',
            '{self._sql_escape(oss_key)}',
            {page if page is not None else "NULL"},
            {sort_order},
            NOW()
        );
        """
        self._execute_sql(sql)
        return self.get_by_id(record_id)

    def get_by_id(self, record_id: str) -> Optional[Dict[str, Any]]:
        ref = self._table_ref(self.table)
        sql = f"""
        SELECT id, chunk_id, job_id, placeholder, oss_key, page, sort_order, created_at
        FROM {ref} WHERE id = '{self._sql_escape(record_id)}' LIMIT 1;
        """
        rows = self._execute_select(sql)
        return self._normalize(rows[0]) if rows else None

    def get_by_chunk(self, chunk_id: str) -> List[Dict[str, Any]]:
        """获取某切片的所有图片，按 sort_order 排序"""
        ref = self._table_ref(self.table)
        sql = f"""
        SELECT id, chunk_id, job_id, placeholder, oss_key, page, sort_order, created_at
        FROM {ref}
        WHERE chunk_id = '{self._sql_escape(chunk_id)}'
        ORDER BY sort_order ASC, created_at ASC;
        """
        return [self._normalize(r) for r in self._execute_select(sql)]

    def get_by_job(self, job_id: str) -> List[Dict[str, Any]]:
        """获取某 job 下所有图片记录"""
        ref = self._table_ref(self.table)
        sql = f"""
        SELECT id, chunk_id, job_id, placeholder, oss_key, page, sort_order, created_at
        FROM {ref}
        WHERE job_id = '{self._sql_escape(job_id)}'
        ORDER BY chunk_id ASC, sort_order ASC;
        """
        return [self._normalize(r) for r in self._execute_select(sql)]

    def get_by_chunk_ids(self, chunk_ids: List[str]) -> List[Dict[str, Any]]:
        """批量查询多个 chunk_id 的图片"""
        if not chunk_ids:
            return []
        ref = self._table_ref(self.table)
        ids_str = ",".join(f"'{self._sql_escape(cid)}'" for cid in chunk_ids)
        sql = f"""
        SELECT id, chunk_id, job_id, placeholder, oss_key, page, sort_order, created_at
        FROM {ref}
        WHERE chunk_id IN ({ids_str})
        ORDER BY chunk_id ASC, sort_order ASC;
        """
        return [self._normalize(r) for r in self._execute_select(sql)]

    def get_oss_keys_by_job(self, job_id: str) -> List[str]:
        """获取某 job 下所有图片的 oss_key（用于删除 OSS 文件）"""
        ref = self._table_ref(self.table)
        sql = f"""
        SELECT oss_key FROM {ref}
        WHERE job_id = '{self._sql_escape(job_id)}' AND oss_key IS NOT NULL AND oss_key != '';
        """
        rows = self._execute_select(sql)
        return [r["oss_key"] for r in rows if r.get("oss_key")]

    def get_oss_keys_by_file(self, file_name: str) -> List[str]:
        """获取某文件名下所有历史 job 的 oss_key（用于彻底清理遗留图片）"""
        ref = self._table_ref(self.table)
        # chunk_id 格式为 {job_id}_{index}，通过 job_id 关联 file_name
        # 直接 JOIN document_job 表获取该文件所有历史 job_id 对应的图片
        doc_job_ref = self._table_ref("knowledge_document_job")
        sql = f"""
        SELECT ci.oss_key FROM {ref} ci
        INNER JOIN {doc_job_ref} dj ON ci.job_id = dj.job_id
        WHERE dj.file_name = '{self._sql_escape(file_name)}'
          AND ci.oss_key IS NOT NULL AND ci.oss_key != '';
        """
        rows = self._execute_select(sql)
        return [r["oss_key"] for r in rows if r.get("oss_key")]

    def delete_by_file(self, file_name: str):
        """删除某文件名下所有历史 job 的图片记录"""
        ref = self._table_ref(self.table)
        doc_job_ref = self._table_ref("knowledge_document_job")
        sql = f"""
        DELETE FROM {ref}
        WHERE job_id IN (
            SELECT job_id FROM {doc_job_ref}
            WHERE file_name = '{self._sql_escape(file_name)}'
        );
        """
        self._execute_sql(sql)

    def delete(self, record_id: str):
        ref = self._table_ref(self.table)
        self._execute_sql(f"DELETE FROM {ref} WHERE id = '{self._sql_escape(record_id)}';")

    def delete_by_chunk(self, chunk_id: str):
        ref = self._table_ref(self.table)
        self._execute_sql(f"DELETE FROM {ref} WHERE chunk_id = '{self._sql_escape(chunk_id)}';")

    def delete_by_job(self, job_id: str):
        ref = self._table_ref(self.table)
        self._execute_sql(f"DELETE FROM {ref} WHERE job_id = '{self._sql_escape(job_id)}';")

    @staticmethod
    def _normalize(row: Dict[str, Any]) -> Dict[str, Any]:
        oss_key = row.get("oss_key") or ""
        # oss_url 返回代理接口路径，前端通过后端转发访问私有 OSS 图片
        oss_url = f"/api/v1/documents/image-proxy?oss_key={quote(oss_key, safe='/')}" if oss_key else ""
        return {
            "id": row.get("id"),
            "chunk_id": row.get("chunk_id"),
            "job_id": row.get("job_id"),
            "placeholder": row.get("placeholder"),
            "oss_key": oss_key,
            "oss_url": oss_url,
            "page": row.get("page"),
            "sort_order": row.get("sort_order", 0),
            "created_at": str(row.get("created_at")) if row.get("created_at") else None,
        }


_instance: Optional[ChunkImageRepository] = None


def get_chunk_image_repository() -> ChunkImageRepository:
    global _instance
    if _instance is None:
        _instance = ChunkImageRepository()
    return _instance
