# -*- coding: utf-8 -*-
"""
类目文件仓储
表：knowledge_ns.knowledge_category_file
记录文件与类目的关系及 OSS 存储信息
"""

import logging
import uuid
from typing import Any, Dict, List, Optional

from app.db.base_repository import BaseRepository

logger = logging.getLogger(__name__)

TABLE = "knowledge_category_file"


class CategoryFileRepository(BaseRepository):

    def __init__(self):
        super().__init__()
        self.table = TABLE

    def create(self, *, category_id: str, file_name: str, oss_key: str) -> Dict[str, Any]:
        ref = self._table_ref(self.table)
        file_id = str(uuid.uuid4())
        sql = f"""
        INSERT INTO {ref}(id, category_id, file_name, oss_key, created_at)
        VALUES (
            '{self._sql_escape(file_id)}',
            '{self._sql_escape(category_id)}',
            '{self._sql_escape(file_name)}',
            '{self._sql_escape(oss_key)}',
            NOW()
        );
        """
        self._execute_sql(sql)
        return self.get_by_category_and_filename(category_id, file_name)

    def get_by_category_and_filename(self, category_id: str, file_name: str) -> Optional[Dict[str, Any]]:
        ref = self._table_ref(self.table)
        sql = f"""
        SELECT id, category_id, file_name, oss_key, created_at
        FROM {ref}
        WHERE category_id = '{self._sql_escape(category_id)}'
          AND file_name = '{self._sql_escape(file_name)}'
        LIMIT 1;
        """
        rows = self._execute_select(sql)
        return self._normalize(rows[0]) if rows else None

    def list_by_category(self, category_id: str) -> List[Dict[str, Any]]:
        ref = self._table_ref(self.table)
        sql = f"""
        SELECT id, category_id, file_name, oss_key, created_at
        FROM {ref}
        WHERE category_id = '{self._sql_escape(category_id)}'
        ORDER BY created_at DESC;
        """
        return [self._normalize(r) for r in self._execute_select(sql)]

    def delete(self, record_id: str):
        ref = self._table_ref(self.table)
        sql = f"DELETE FROM {ref} WHERE id = '{self._sql_escape(record_id)}';"
        self._execute_sql(sql)

    def delete_by_category_and_filename(self, category_id: str, file_name: str):
        ref = self._table_ref(self.table)
        sql = f"""
        DELETE FROM {ref}
        WHERE category_id = '{self._sql_escape(category_id)}'
          AND file_name = '{self._sql_escape(file_name)}';
        """
        self._execute_sql(sql)

    def count_by_category(self, category_id: str) -> int:
        ref = self._table_ref(self.table)
        sql = f"""
        SELECT COUNT(*) as cnt FROM {ref}
        WHERE category_id = '{self._sql_escape(category_id)}';
        """
        rows = self._execute_select(sql)
        return int(rows[0].get("cnt") or 0) if rows else 0

    @staticmethod
    def _normalize(row: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": row.get("id"),
            "category_id": row.get("category_id"),
            "file_name": row.get("file_name"),
            "oss_key": row.get("oss_key"),
            "created_at": str(row.get("created_at")) if row.get("created_at") else None,
        }


_instance: Optional[CategoryFileRepository] = None


def get_category_file_repository() -> CategoryFileRepository:
    global _instance
    if _instance is None:
        _instance = CategoryFileRepository()
    return _instance
