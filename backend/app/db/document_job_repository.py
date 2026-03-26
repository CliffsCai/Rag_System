# -*- coding: utf-8 -*-
"""
文档任务仓储
表：knowledge_ns.knowledge_document_job
记录文件名与 job_id 的对应关系，status 实时从 knowledge_job 查询
"""

import logging
import uuid
from typing import Any, Dict, List, Optional

from app.db.base_repository import BaseRepository

logger = logging.getLogger(__name__)

TABLE = "knowledge_document_job"
JOB_TABLE = "knowledge_job"


class DocumentJobRepository(BaseRepository):

    def __init__(self):
        super().__init__()
        self.table = TABLE

    def create(self, *, file_name: str, job_id: str, category_id: Optional[str] = None, collection: Optional[str] = None) -> Dict[str, Any]:
        ref = self._table_ref(self.table)
        record_id = str(uuid.uuid4())
        cat_val = f"'{self._sql_escape(category_id)}'" if category_id else "NULL"
        col_val = f"'{self._sql_escape(collection)}'" if collection else "NULL"
        sql = f"""
        INSERT INTO {ref}(id, file_name, job_id, category_id, collection, created_at)
        VALUES (
            '{self._sql_escape(record_id)}',
            '{self._sql_escape(file_name)}',
            '{self._sql_escape(job_id)}',
            {cat_val},
            {col_val},
            NOW()
        );
        """
        self._execute_sql(sql)
        return self.get_by_filename(file_name)

    def upsert(self, *, file_name: str, job_id: str, category_id: Optional[str] = None, collection: Optional[str] = None) -> Dict[str, Any]:
        """
        按 (file_name, category_id, collection) 三元组唯一：
        - 同一知识库同一类目下同名文件只保留一条记录
        已存在则更新 job_id，否则插入
        """
        existing = self.get_by_filename_category_collection(file_name, category_id, collection)
        if existing:
            ref = self._table_ref(self.table)
            col_val = f"'{self._sql_escape(collection)}'" if collection else "NULL"
            sql = f"""
            UPDATE {ref}
            SET job_id = '{self._sql_escape(job_id)}',
                collection = {col_val},
                created_at = NOW()
            WHERE id = '{self._sql_escape(existing["id"])}';
            """
            self._execute_sql(sql)
        else:
            self.create(file_name=file_name, job_id=job_id, category_id=category_id, collection=collection)
        return self.get_by_filename_category_collection(file_name, category_id, collection)

    def get_by_filename(self, file_name: str) -> Optional[Dict[str, Any]]:
        """兼容旧调用，返回第一条匹配记录"""
        ref = self._table_ref(self.table)
        sql = f"""
        SELECT id, file_name, job_id, category_id, collection, created_at
        FROM {ref}
        WHERE file_name = '{self._sql_escape(file_name)}'
        ORDER BY created_at DESC
        LIMIT 1;
        """
        rows = self._execute_select(sql)
        return self._normalize(rows[0]) if rows else None

    def get_by_filename_category_collection(self, file_name: str, category_id: Optional[str], collection: Optional[str]) -> Optional[Dict[str, Any]]:
        """按 (file_name, category_id, collection) 精确查找"""
        ref = self._table_ref(self.table)
        cat_cond = f"category_id = '{self._sql_escape(category_id)}'" if category_id else "category_id IS NULL"
        col_cond = f"collection = '{self._sql_escape(collection)}'" if collection else "collection IS NULL"
        sql = f"""
        SELECT id, file_name, job_id, category_id, collection, created_at
        FROM {ref}
        WHERE file_name = '{self._sql_escape(file_name)}'
          AND {cat_cond}
          AND {col_cond}
        LIMIT 1;
        """
        rows = self._execute_select(sql)
        return self._normalize(rows[0]) if rows else None

    def get_by_filename_and_category(self, file_name: str, category_id: Optional[str]) -> Optional[Dict[str, Any]]:
        """按 (file_name, category_id) 精确查找"""
        ref = self._table_ref(self.table)
        if category_id:
            cat_cond = f"category_id = '{self._sql_escape(category_id)}'"
        else:
            cat_cond = "category_id IS NULL"
        sql = f"""
        SELECT id, file_name, job_id, category_id, collection, created_at
        FROM {ref}
        WHERE file_name = '{self._sql_escape(file_name)}'
          AND {cat_cond}
        LIMIT 1;
        """
        rows = self._execute_select(sql)
        return self._normalize(rows[0]) if rows else None

    def get_by_job_id(self, job_id: str) -> Optional[Dict[str, Any]]:
        ref = self._table_ref(self.table)
        sql = f"""
        SELECT id, file_name, job_id, category_id, collection, created_at
        FROM {ref}
        WHERE job_id = '{self._sql_escape(job_id)}'
        LIMIT 1;
        """
        rows = self._execute_select(sql)
        return self._normalize(rows[0]) if rows else None

    def list_all_with_status(self, limit: int = 500, collection: Optional[str] = None) -> List[Dict[str, Any]]:
        """查询文档任务，LEFT JOIN knowledge_job 获取实时状态。传 collection 则按知识库过滤。"""
        ref = self._table_ref(self.table)
        job_ref = self._table_ref(JOB_TABLE)
        safe_limit = max(1, min(limit, 2000))
        col_filter = f"AND d.collection = '{self._sql_escape(collection)}'" if collection else ""
        sql = f"""
        SELECT
            d.id, d.file_name, d.job_id, d.category_id, d.collection, d.created_at, d.vectorized,
            j.status, j.comment, j.process, j.stage, j.dry_run
        FROM {ref} d
        LEFT JOIN {job_ref} j ON d.job_id = j.job_id
        WHERE 1=1 {col_filter}
        ORDER BY d.created_at DESC
        LIMIT {safe_limit};
        """
        return [self._normalize_with_status(r) for r in self._execute_select(sql)]

    def list_job_ids_by_collection(self, collection: str) -> List[str]:
        """查出某个 collection 下所有 job_id"""
        ref = self._table_ref(self.table)
        sql = f"""
        SELECT job_id FROM {ref}
        WHERE collection = '{self._sql_escape(collection)}';
        """
        rows = self._execute_select(sql)
        return [r["job_id"] for r in rows if r.get("job_id")]

    def delete_by_collection(self, collection: str):
        ref = self._table_ref(self.table)
        sql = f"DELETE FROM {ref} WHERE collection = '{self._sql_escape(collection)}';"
        self._execute_sql(sql)

    def mark_vectorized(self, job_id: str):
        """upsert 成功后标记为已向量化"""
        ref = self._table_ref(self.table)
        sql = f"UPDATE {ref} SET vectorized = TRUE WHERE job_id = '{self._sql_escape(job_id)}';"
        self._execute_sql(sql)

    def delete_by_filename(self, file_name: str):
        ref = self._table_ref(self.table)
        sql = f"DELETE FROM {ref} WHERE file_name = '{self._sql_escape(file_name)}';"
        self._execute_sql(sql)

    def delete_by_job_id(self, job_id: str):
        ref = self._table_ref(self.table)
        sql = f"DELETE FROM {ref} WHERE job_id = '{self._sql_escape(job_id)}';"
        self._execute_sql(sql)

    @staticmethod
    def _normalize(row: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": row.get("id"),
            "file_name": row.get("file_name"),
            "job_id": row.get("job_id"),
            "category_id": row.get("category_id"),
            "collection": row.get("collection"),
            "created_at": str(row.get("created_at")) if row.get("created_at") else None,
        }

    @staticmethod
    def _normalize_with_status(row: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": row.get("id"),
            "file_name": row.get("file_name"),
            "job_id": row.get("job_id"),
            "category_id": row.get("category_id"),
            "collection": row.get("collection"),
            "created_at": str(row.get("created_at")) if row.get("created_at") else None,
            "vectorized": bool(row.get("vectorized")),
            "status": row.get("status"),
            "comment": row.get("comment"),
            "process": row.get("process"),
            "stage": row.get("stage"),
            "dry_run": row.get("dry_run"),
        }


_instance: Optional[DocumentJobRepository] = None


def get_document_job_repository() -> DocumentJobRepository:
    global _instance
    if _instance is None:
        _instance = DocumentJobRepository()
    return _instance
