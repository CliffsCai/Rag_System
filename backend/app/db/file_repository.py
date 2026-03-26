# -*- coding: utf-8 -*-
"""
文件-类目关联仓储
表：knowledge_ns.knowledge_file
一个文件属于一个类目，记录上传状态
"""

import logging
from typing import Any, Dict, List, Optional

from app.db.base_repository import BaseRepository

logger = logging.getLogger(__name__)

FILE_TABLE = "knowledge_upload_file"


class FileRepository(BaseRepository):

    def __init__(self):
        super().__init__()
        self.table = FILE_TABLE
        self._ensure_table()

    def _ensure_table(self):
        ref = self._table_ref(self.table)
        sql = f"""
        CREATE TABLE IF NOT EXISTS {ref} (
            file_id TEXT PRIMARY KEY,
            category_id TEXT NOT NULL,
            file_name TEXT NOT NULL,
            job_id TEXT,
            namespace TEXT DEFAULT 'knowledge_ns',
            collection TEXT DEFAULT 'test_api_collection',
            status TEXT DEFAULT 'pending',
            error TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        );
        """
        self._execute_sql(sql)

    def create(
        self,
        *,
        file_id: str,
        category_id: str,
        file_name: str,
        namespace: str = "knowledge_ns",
        collection: str = "test_api_collection",
        status: str = "pending",
    ) -> Dict[str, Any]:
        ref = self._table_ref(self.table)
        sql = f"""
        INSERT INTO {ref}(file_id, category_id, file_name, namespace, collection, status, created_at, updated_at)
        VALUES (
            '{self._sql_escape(file_id)}',
            '{self._sql_escape(category_id)}',
            '{self._sql_escape(file_name)}',
            '{self._sql_escape(namespace)}',
            '{self._sql_escape(collection)}',
            '{self._sql_escape(status)}',
            NOW(), NOW()
        );
        """
        self._execute_sql(sql)
        return self.get(file_id)

    def update_job(self, file_id: str, job_id: str, status: str = "processing"):
        ref = self._table_ref(self.table)
        sql = f"""
        UPDATE {ref}
        SET job_id = '{self._sql_escape(job_id)}',
            status = '{self._sql_escape(status)}',
            updated_at = NOW()
        WHERE file_id = '{self._sql_escape(file_id)}';
        """
        self._execute_sql(sql)

    def update_status(self, file_id: str, status: str, error: Optional[str] = None):
        ref = self._table_ref(self.table)
        parts = [f"status = '{self._sql_escape(status)}'", "updated_at = NOW()"]
        if error is not None:
            parts.append(f"error = '{self._sql_escape(error)}'")
        sql = f"UPDATE {ref} SET {', '.join(parts)} WHERE file_id = '{self._sql_escape(file_id)}';"
        self._execute_sql(sql)

    def update_status_by_job(self, job_id: str, status: str, error: Optional[str] = None):
        """通过 job_id 更新文件状态（knowledge_upload_file 是我们自己管理的表）"""
        ref = self._table_ref(self.table)
        parts = [f"status = '{self._sql_escape(status)}'", "updated_at = NOW()"]
        if error is not None:
            parts.append(f"error = '{self._sql_escape(error)}'")
        sql = f"UPDATE {ref} SET {', '.join(parts)} WHERE job_id = '{self._sql_escape(job_id)}';"
        self._execute_sql(sql)

    def get(self, file_id: str) -> Optional[Dict[str, Any]]:
        ref = self._table_ref(self.table)
        sql = f"""
        SELECT file_id, category_id, file_name, job_id, namespace, collection, status, error, created_at, updated_at
        FROM {ref}
        WHERE file_id = '{self._sql_escape(file_id)}'
        LIMIT 1;
        """
        rows = self._execute_select(sql)
        return self._normalize(rows[0]) if rows else None

    def list_by_category(self, category_id: str) -> List[Dict[str, Any]]:
        ref = self._table_ref(self.table)
        sql = f"""
        SELECT file_id, category_id, file_name, job_id, namespace, collection, status, error, created_at, updated_at
        FROM {ref}
        WHERE category_id = '{self._sql_escape(category_id)}'
        ORDER BY created_at DESC;
        """
        return [self._normalize(r) for r in self._execute_select(sql)]

    def list_all(self, limit: int = 500) -> List[Dict[str, Any]]:
        ref = self._table_ref(self.table)
        sql = f"""
        SELECT file_id, category_id, file_name, job_id, namespace, collection, status, error, created_at, updated_at
        FROM {ref}
        ORDER BY created_at DESC
        LIMIT {max(1, min(limit, 2000))};
        """
        return [self._normalize(r) for r in self._execute_select(sql)]

    def list_with_category_name(
        self,
        category_id: Optional[str] = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        """查询文件列表，JOIN knowledge_category 表附加 category_name 字段。

        Args:
            category_id: 可选，按类目过滤；为 None 时返回全量。
            limit: 返回条数上限，默认 200，最大 2000。
        """
        safe_limit = max(1, min(limit, 2000))
        # _table_ref 会加上 schema 前缀，例如 "knowledge_ns"."knowledge_upload_file"
        # 对于 JOIN 的第二张表，手动拼接相同的 schema 前缀
        file_ref = self._table_ref(self.table)
        cat_ref = self._table_ref("knowledge_category")

        where_clause = ""
        if category_id is not None:
            where_clause = f"WHERE f.category_id = '{self._sql_escape(category_id)}'"

        sql = f"""
        SELECT f.file_id, f.category_id, c.name AS category_name,
               f.file_name, f.job_id, f.status, f.error, f.created_at, f.updated_at
        FROM {file_ref} f
        LEFT JOIN {cat_ref} c ON f.category_id = c.category_id
        {where_clause}
        ORDER BY f.created_at DESC
        LIMIT {safe_limit};
        """
        return [self._normalize_with_category(r) for r in self._execute_select(sql)]

    @staticmethod
    def _normalize_with_category(row: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "file_id": row.get("file_id"),
            "category_id": row.get("category_id"),
            "category_name": row.get("category_name"),
            "file_name": row.get("file_name"),
            "job_id": row.get("job_id"),
            "status": row.get("status"),
            "error": row.get("error"),
            "created_at": str(row.get("created_at")) if row.get("created_at") else None,
            "updated_at": str(row.get("updated_at")) if row.get("updated_at") else None,
        }

    def delete(self, file_id: str):
        ref = self._table_ref(self.table)
        sql = f"DELETE FROM {ref} WHERE file_id = '{self._sql_escape(file_id)}';"
        self._execute_sql(sql)

    @staticmethod
    def _normalize(row: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "file_id": row.get("file_id"),
            "category_id": row.get("category_id"),
            "file_name": row.get("file_name"),
            "job_id": row.get("job_id"),
            "namespace": row.get("namespace"),
            "collection": row.get("collection"),
            "status": row.get("status"),
            "error": row.get("error"),
            "created_at": str(row.get("created_at")) if row.get("created_at") else None,
            "updated_at": str(row.get("updated_at")) if row.get("updated_at") else None,
        }


_instance: Optional[FileRepository] = None


def get_file_repository() -> FileRepository:
    global _instance
    if _instance is None:
        _instance = FileRepository()
    return _instance
