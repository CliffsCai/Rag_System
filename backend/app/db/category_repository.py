# -*- coding: utf-8 -*-
"""
类目（文件夹）仓储
表：knowledge_ns.knowledge_category
"""

import json
import logging
from typing import Any, Dict, List, Optional

from app.db.base_repository import BaseRepository

logger = logging.getLogger(__name__)

CATEGORY_TABLE = "knowledge_category"


class CategoryRepository(BaseRepository):

    def __init__(self):
        super().__init__()
        self.table = CATEGORY_TABLE
        self._ensure_table()

    def _ensure_table(self):
        ref = self._table_ref(self.table)
        sql = f"""
        CREATE TABLE IF NOT EXISTS {ref} (
            category_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        );
        """
        self._execute_sql(sql)

    def create(self, *, category_id: str, name: str, description: Optional[str] = None) -> Dict[str, Any]:
        ref = self._table_ref(self.table)
        sql = f"""
        INSERT INTO {ref}(category_id, name, description, created_at, updated_at)
        VALUES (
            '{self._sql_escape(category_id)}',
            '{self._sql_escape(name)}',
            '{self._sql_escape(description)}',
            NOW(), NOW()
        );
        """
        self._execute_sql(sql)
        return self.get(category_id)

    def get(self, category_id: str) -> Optional[Dict[str, Any]]:
        ref = self._table_ref(self.table)
        sql = f"""
        SELECT category_id, name, description, created_at, updated_at
        FROM {ref}
        WHERE category_id = '{self._sql_escape(category_id)}'
        LIMIT 1;
        """
        rows = self._execute_select(sql)
        return self._normalize(rows[0]) if rows else None

    def list_all(self) -> List[Dict[str, Any]]:
        ref = self._table_ref(self.table)
        sql = f"""
        SELECT category_id, name, description, created_at, updated_at
        FROM {ref}
        ORDER BY created_at DESC;
        """
        return [self._normalize(r) for r in self._execute_select(sql)]

    def update(self, category_id: str, *, name: Optional[str] = None, description: Optional[str] = None):
        ref = self._table_ref(self.table)
        parts = ["updated_at = NOW()"]
        if name is not None:
            parts.append(f"name = '{self._sql_escape(name)}'")
        if description is not None:
            parts.append(f"description = '{self._sql_escape(description)}'")
        sql = f"UPDATE {ref} SET {', '.join(parts)} WHERE category_id = '{self._sql_escape(category_id)}';"
        self._execute_sql(sql)

    def delete(self, category_id: str):
        ref = self._table_ref(self.table)
        sql = f"DELETE FROM {ref} WHERE category_id = '{self._sql_escape(category_id)}';"
        self._execute_sql(sql)

    @staticmethod
    def _normalize(row: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "category_id": row.get("category_id"),
            "name": row.get("name"),
            "description": row.get("description"),
            "created_at": str(row.get("created_at")) if row.get("created_at") else None,
            "updated_at": str(row.get("updated_at")) if row.get("updated_at") else None,
        }


_instance: Optional[CategoryRepository] = None


def get_category_repository() -> CategoryRepository:
    global _instance
    if _instance is None:
        _instance = CategoryRepository()
    return _instance
