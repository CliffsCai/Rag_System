# -*- coding: utf-8 -*-
"""
Collection 配置仓储
表：knowledge_ns.knowledge_collection_config
存储 collection 的完整配置（含 metadata 字段、auto_inject 规则、向量参数等）
"""

import json
import logging
import uuid
from typing import Any, Dict, List, Optional

from app.db.base_repository import BaseRepository

logger = logging.getLogger(__name__)

TABLE = "knowledge_collection_config"


class CollectionConfigRepository(BaseRepository):

    def __init__(self):
        super().__init__()
        self.table = TABLE

    def upsert(
        self,
        *,
        namespace: str,
        collection: str,
        metadata_fields: Optional[List[Dict]] = None,
        full_text_retrieval_fields: Optional[str] = None,
        metadata_indices: Optional[str] = None,
        parser: Optional[str] = None,
        embedding_model: Optional[str] = None,
        dimension: Optional[int] = None,
        metrics: Optional[str] = None,
        hnsw_m: Optional[int] = None,
        hnsw_ef_construction: Optional[int] = None,
        pq_enable: int = 0,
        external_storage: int = 0,
        image_mode: bool = False,
    ) -> Dict[str, Any]:
        existing = self.get_by_collection(namespace, collection)
        fields_json = json.dumps(metadata_fields or [], ensure_ascii=False).replace("'", "''")
        ref = self._table_ref(self.table)

        def _val(v):
            if v is None:
                return "NULL"
            if isinstance(v, int):
                return str(v)
            return f"'{self._sql_escape(str(v))}'"

        if existing:
            sql = f"""
            UPDATE {ref}
            SET metadata_fields = '{fields_json}'::jsonb,
                full_text_retrieval_fields = {_val(full_text_retrieval_fields)},
                metadata_indices = {_val(metadata_indices)},
                parser = {_val(parser)},
                embedding_model = {_val(embedding_model)},
                dimension = {_val(dimension)},
                metrics = {_val(metrics)},
                hnsw_m = {_val(hnsw_m)},
                hnsw_ef_construction = {_val(hnsw_ef_construction)},
                pq_enable = {pq_enable},
                external_storage = {external_storage},
                image_mode = {str(image_mode).upper()},
                updated_at = NOW()
            WHERE namespace = '{self._sql_escape(namespace)}'
              AND collection = '{self._sql_escape(collection)}';
            """
            self._execute_sql(sql)
        else:
            record_id = str(uuid.uuid4())
            sql = f"""
            INSERT INTO {ref}(
                id, namespace, collection, metadata_fields,
                full_text_retrieval_fields, metadata_indices,
                parser, embedding_model, dimension, metrics,
                hnsw_m, hnsw_ef_construction, pq_enable, external_storage,
                image_mode, created_at, updated_at
            ) VALUES (
                '{self._sql_escape(record_id)}',
                '{self._sql_escape(namespace)}',
                '{self._sql_escape(collection)}',
                '{fields_json}'::jsonb,
                {_val(full_text_retrieval_fields)},
                {_val(metadata_indices)},
                {_val(parser)},
                {_val(embedding_model)},
                {_val(dimension)},
                {_val(metrics)},
                {_val(hnsw_m)},
                {_val(hnsw_ef_construction)},
                {pq_enable},
                {external_storage},
                {str(image_mode).upper()},
                NOW(), NOW()
            );
            """
            self._execute_sql(sql)
        return self.get_by_collection(namespace, collection)

    def get_by_collection(self, namespace: str, collection: str) -> Optional[Dict[str, Any]]:
        ref = self._table_ref(self.table)
        sql = f"""
        SELECT id, namespace, collection, metadata_fields,
               full_text_retrieval_fields, metadata_indices,
               parser, embedding_model, dimension, metrics,
               hnsw_m, hnsw_ef_construction, pq_enable, external_storage,
               image_mode, created_at, updated_at
        FROM {ref}
        WHERE namespace = '{self._sql_escape(namespace)}'
          AND collection = '{self._sql_escape(collection)}'
        LIMIT 1;
        """
        rows = self._execute_select(sql)
        return self._normalize(rows[0]) if rows else None

    def list_by_namespace(self, namespace: str) -> List[Dict[str, Any]]:
        ref = self._table_ref(self.table)
        sql = f"""
        SELECT id, namespace, collection, metadata_fields,
               full_text_retrieval_fields, metadata_indices,
               parser, embedding_model, dimension, metrics,
               hnsw_m, hnsw_ef_construction, pq_enable, external_storage,
               image_mode, created_at, updated_at
        FROM {ref}
        WHERE namespace = '{self._sql_escape(namespace)}'
        ORDER BY created_at DESC;
        """
        return [self._normalize(r) for r in self._execute_select(sql)]

    def delete_by_collection(self, namespace: str, collection: str):
        ref = self._table_ref(self.table)
        sql = f"""
        DELETE FROM {ref}
        WHERE namespace = '{self._sql_escape(namespace)}'
          AND collection = '{self._sql_escape(collection)}';
        """
        self._execute_sql(sql)

    @staticmethod
    def _normalize(row: Dict[str, Any]) -> Dict[str, Any]:
        fields = row.get("metadata_fields")
        if isinstance(fields, str):
            try:
                fields = json.loads(fields)
            except Exception:
                fields = []
        return {
            "id": row.get("id"),
            "namespace": row.get("namespace"),
            "collection": row.get("collection"),
            "collection_name": row.get("collection"),  # 兼容前端展示
            "metadata_fields": fields or [],
            "full_text_retrieval_fields": row.get("full_text_retrieval_fields"),
            "metadata_indices": row.get("metadata_indices"),
            "parser": row.get("parser"),
            "embedding_model": row.get("embedding_model"),
            "dimension": row.get("dimension"),
            "metrics": row.get("metrics"),
            "hnsw_m": row.get("hnsw_m"),
            "hnsw_ef_construction": row.get("hnsw_ef_construction"),
            "pq_enable": row.get("pq_enable"),
            "external_storage": row.get("external_storage"),
            "image_mode": bool(row.get("image_mode", False)),
            "created_at": str(row.get("created_at")) if row.get("created_at") else None,
            "updated_at": str(row.get("updated_at")) if row.get("updated_at") else None,
        }


_instance: Optional[CollectionConfigRepository] = None


def get_collection_config_repository() -> CollectionConfigRepository:
    global _instance
    if _instance is None:
        _instance = CollectionConfigRepository()
    return _instance
