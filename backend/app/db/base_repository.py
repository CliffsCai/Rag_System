# -*- coding: utf-8 -*-
"""
ADB SQL 执行基类
所有 Repository 继承此类，复用 SQL 执行和结果解析逻辑
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional

from alibabacloud_gpdb20160503 import models as gpdb_20160503_models

from app.core.config import settings
from app.services.adb_vector_service import get_adb_vector_service

logger = logging.getLogger(__name__)


class BaseRepository:
    """ADB SQL 执行基类"""

    def __init__(self):
        self.vector_service = get_adb_vector_service()
        self.region_id = self.vector_service.region_id
        self.db_instance_id = self.vector_service.instance_id
        self.database = "knowledgebase"
        self.namespace = settings.adb_namespace
        self.secret_arn = self._resolve_secret_arn()

    def _resolve_secret_arn(self) -> str:
        """
        获取 SQL 访问凭证 ARN。优先级：
        1. 环境变量 ADB_SQL_SECRET_ARN（手动指定真实 ARN，直接使用）
        2. ListSecrets 查找固定名称的 Secret（复用已有）
        3. CreateSecret 创建固定名称的 Secret（首次创建）
        """
        configured_arn = settings.adb_sql_secret_arn
        # 过滤掉明显的占位符值（真实 ARN 格式为 acs:gpdb:... ）
        if configured_arn and configured_arn.startswith("acs:"):
            return configured_arn

        username = settings.bailian_adb_user
        password = settings.bailian_adb_password
        if not username or not password:
            raise ValueError(
                "缺少数据库账号，请配置 BAILIAN_ADB_USER/BAILIAN_ADB_PASSWORD 或 ADB_SQL_SECRET_ARN"
            )

        # 固定 secret_name，基于用户名派生，保证每个用户只有一个 Secret
        secret_name = self._normalize_secret_name(
            settings.adb_sql_secret_name or f"kbsec-{username}"
        )

        arn = self.vector_service.get_or_create_secret(
            username=username,
            password=password,
            secret_name=secret_name,
        )
        if not arn:
            raise ValueError(f"无法获取或创建 ADB SQL Secret（name={secret_name}），请检查账号权限")

        logger.info("ADB SQL Secret 就绪", extra={"secret_name": secret_name, "arn": arn})
        return arn

    @staticmethod
    def _normalize_secret_name(raw: str) -> str:
        name = re.sub(r"[^a-z0-9_-]", "", (raw or "").strip().lower()) or "sqlsec"
        return name[:16]

    @staticmethod
    def _sql_escape(value: Optional[str]) -> str:
        if value is None:
            return ""
        return str(value).replace("'", "''")

    @staticmethod
    def _quote(name: str) -> str:
        return '"' + str(name).replace('"', '""') + '"'

    def _table_ref(self, table_name: str) -> str:
        if "." in table_name:
            schema, table = table_name.split(".", 1)
            return f"{self._quote(schema)}.{self._quote(table)}"
        return f"{self._quote(self.namespace)}.{self._quote(table_name)}"

    @staticmethod
    def _to_bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in {"true", "t", "1", "yes"}
        return bool(value)

    @staticmethod
    def _unwrap_field(field: Any) -> Any:
        if field is None:
            return None
        if hasattr(field, "is_null") and getattr(field, "is_null"):
            return None
        for attr in ["string_value", "long_value", "double_value", "boolean_value",
                     "StringValue", "LongValue", "DoubleValue", "BooleanValue"]:
            if hasattr(field, attr):
                v = getattr(field, attr)
                if v not in (None, ""):
                    return v
        return None

    def _execute_sql(self, sql: str) -> Any:
        client = self.vector_service.get_client()
        request = gpdb_20160503_models.ExecuteStatementRequest(
            region_id=self.region_id,
            dbinstance_id=self.db_instance_id,
            secret_arn=self.secret_arn,
            database=self.database,
            run_type="synchronous",
            sql=sql,
        )
        return client.execute_statement(request)

    def _execute_select(self, sql: str) -> List[Dict[str, Any]]:
        response = self._execute_sql(sql)
        if hasattr(response.body, "to_map"):
            body_map = response.body.to_map() or {}
            data_map = body_map.get("Data") or body_map.get("data") or {}
            meta_outer = data_map.get("ColumnMetadata") or data_map.get("column_metadata") or {}
            meta_list = meta_outer.get("ColumnMetadata") or meta_outer.get("column_metadata") or []
            columns = [m.get("Name") or m.get("name") or "" for m in meta_list]
            rec_outer = data_map.get("Records") or data_map.get("records") or {}
            raw_rows = rec_outer.get("Records") or rec_outer.get("records") or []
            rows = []
            for row in raw_rows:
                fields = row.get("Record") or row.get("record") or []
                row_dict = {}
                for idx, field in enumerate(fields):
                    key = columns[idx] if idx < len(columns) and columns[idx] else f"col_{idx}"
                    value = None
                    if isinstance(field, dict):
                        if field.get("IsNull") or field.get("is_null"):
                            value = None
                        else:
                            for k in ["StringValue", "LongValue", "DoubleValue", "BooleanValue",
                                      "string_value", "long_value", "double_value", "boolean_value"]:
                                if k in field and field[k] not in (None, ""):
                                    value = field[k]
                                    break
                    row_dict[key] = value
                rows.append(row_dict)
            return rows

        body = response.body
        data = getattr(body, "data", None)
        if not data:
            return []
        meta_obj = getattr(data, "column_metadata", None) or getattr(data, "ColumnMetadata", None)
        columns = []
        if meta_obj:
            raw_cols = getattr(meta_obj, "column_metadata", None) or getattr(meta_obj, "ColumnMetadata", None) or []
            columns = [getattr(c, "name", None) or getattr(c, "Name", None) or "" for c in raw_cols]
        rec_obj = getattr(data, "records", None) or getattr(data, "Records", None)
        raw_rows = getattr(rec_obj, "records", None) or getattr(rec_obj, "Records", None) or []
        rows = []
        for row in raw_rows:
            fields = getattr(row, "record", None) or getattr(row, "Record", None) or []
            row_dict = {}
            for idx, field in enumerate(fields):
                key = columns[idx] if idx < len(columns) and columns[idx] else f"col_{idx}"
                row_dict[key] = self._unwrap_field(field)
            rows.append(row_dict)
        return rows
