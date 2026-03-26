# -*- coding: utf-8 -*-
"""
上传任务仓储（knowledge_job 表，不修改表结构）
"""

import logging
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.db.base_repository import BaseRepository

logger = logging.getLogger(__name__)


class JobRepository(BaseRepository):

    def __init__(self):
        super().__init__()
        self.table = settings.adb_job_table  # knowledge_job

    def _ensure_table(self):
        ref = self._table_ref(self.table)
        sql = f"""
        CREATE TABLE IF NOT EXISTS {ref} (
            job_id TEXT PRIMARY KEY,
            file_name TEXT,
            namespace TEXT,
            collection TEXT,
            splitting_method TEXT,
            dry_run BOOLEAN DEFAULT FALSE,
            status TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            message TEXT,
            error TEXT,
            detail JSONB
        );
        """
        self._execute_sql(sql)

    def upsert_job(
        self,
        *,
        job_id: str,
        file_name: str,
        namespace: str,
        collection: str,
        splitting_method: str = "smart",
        dry_run: bool = True,
        status: str = "queued",
        message: Optional[str] = None,
        error: Optional[str] = None,
        detail: Optional[Dict[str, Any]] = None,
    ):
        ref = self._table_ref(self.table)
        # 映射到 knowledge_job 真实字段
        # stage = splitting_method, comment = message, status = status
        stage = self._sql_escape(splitting_method)
        comment = self._sql_escape(message or "")
        sql = f"""
        INSERT INTO {ref}(
            job_id, file_name, namespace, collection,
            stage, dry_run, status, comment,
            gmt_created, gmt_modified
        ) VALUES (
            '{self._sql_escape(job_id)}',
            '{self._sql_escape(file_name)}',
            '{self._sql_escape(namespace)}',
            '{self._sql_escape(collection)}',
            '{stage}',
            {str(bool(dry_run)).upper()},
            '{self._sql_escape(status)}',
            '{comment}',
            NOW(), NOW()
        )
        ON CONFLICT (job_id) DO UPDATE SET
            file_name       = EXCLUDED.file_name,
            namespace       = EXCLUDED.namespace,
            collection      = EXCLUDED.collection,
            stage           = EXCLUDED.stage,
            dry_run         = EXCLUDED.dry_run,
            status          = EXCLUDED.status,
            comment         = EXCLUDED.comment,
            gmt_modified    = NOW();
        """
        self._execute_sql(sql)

    def update_job_status(
        self,
        job_id: str,
        status: str,
        message: Optional[str] = None,
        error: Optional[str] = None,
        detail: Optional[Dict[str, Any]] = None,
    ):
        ref = self._table_ref(self.table)
        parts = [f"status = '{self._sql_escape(status)}'", "gmt_modified = NOW()"]
        if message is not None:
            parts.append(f"comment = '{self._sql_escape(message)}'")
        sql = f"UPDATE {ref} SET {', '.join(parts)} WHERE job_id = '{self._sql_escape(job_id)}';"
        self._execute_sql(sql)

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        ref = self._table_ref(self.table)
        sql = f"""
        SELECT job_id, file_name, namespace, collection,
               stage, dry_run, status, comment, process,
               gmt_created, gmt_modified
        FROM {ref}
        WHERE job_id = '{self._sql_escape(job_id)}'
        LIMIT 1;
        """
        rows = self._execute_select(sql)
        return self._normalize_row(rows[0]) if rows else None

    def list_jobs(self, limit: int = 200) -> List[Dict[str, Any]]:
        ref = self._table_ref(self.table)
        sql = f"""
        SELECT job_id, file_name, namespace, collection,
               stage, dry_run, status, comment, process,
               gmt_created, gmt_modified
        FROM {ref}
        ORDER BY gmt_created DESC
        LIMIT {max(1, min(limit, 1000))};
        """
        return [self._normalize_row(r) for r in self._execute_select(sql)]

    def count_jobs(self) -> int:
        ref = self._table_ref(self.table)
        rows = self._execute_select(f"SELECT COUNT(*) AS total FROM {ref};")
        if not rows:
            return 0
        try:
            return int(rows[0].get("total", 0))
        except Exception:
            return 0

    def get_debug_context(self) -> Dict[str, Any]:
        return {
            "region_id": self.region_id,
            "db_instance_id": self.db_instance_id,
            "database": self.database,
            "namespace": self.namespace,
            "table": self.table,
            "table_ref": self._table_ref(self.table),
            "has_secret_arn": bool(self.secret_arn),
        }

    def _normalize_row(self, row: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "job_id": row.get("job_id"),
            "file_name": row.get("file_name"),
            "namespace": row.get("namespace"),
            "collection": row.get("collection"),
            "splitting_method": row.get("stage"),   # stage → splitting_method
            "dry_run": self._to_bool(row.get("dry_run")),
            "status": row.get("status"),
            "message": row.get("comment"),           # comment → message
            "error": None,
            "detail": {},
            "process": row.get("process"),
            "created_at": str(row.get("gmt_created")) if row.get("gmt_created") else None,
            "updated_at": str(row.get("gmt_modified")) if row.get("gmt_modified") else None,
        }


_job_repo: Optional[JobRepository] = None


def get_job_repository() -> JobRepository:
    global _job_repo
    if _job_repo is None:
        _job_repo = JobRepository()
    return _job_repo
