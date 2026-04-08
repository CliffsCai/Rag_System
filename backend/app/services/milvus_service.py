# -*- coding: utf-8 -*-
"""
Milvus 向量数据库服务
负责 collection 管理、向量写入、混合检索、删除
"""
import re
import logging
from typing import Any, Dict, List, Optional

from pymilvus import (
    MilvusClient,
    DataType,
    Function,
    FunctionType,
    AnnSearchRequest,
    RRFRanker,
    WeightedRanker,
)

from app.core.config import settings
from app.services.embedding_service import get_embedding_service

logger = logging.getLogger(__name__)

# 图片占位符正则（用于向量化前剥离）
_IMAGE_PH_RE = re.compile(r'<<IMAGE:[0-9a-f]+>>')

_ANALYZER_PARAMS = {"type": "chinese"}


class MilvusService:

    def __init__(self):
        uri = f"http://{settings.milvus_host}:{settings.milvus_port}"
        token = f"{settings.milvus_user}:{settings.milvus_password}"
        self.client = MilvusClient(uri=uri, token=token)
        logger.info(f"Milvus 连接成功: {uri}")

    # ── Collection 管理 ───────────────────────────────────────────────────────

    def get_or_create_collection(
        self,
        collection_name: str,
        dim: int = 1536,
        image_mode: bool = False,
        metadata_fields: Optional[List[Dict[str, Any]]] = None,
        kb_type: str = "standard",
        image_vector_dim: int = 1024,
    ) -> None:
        """幂等建 collection。
        kb_type="multimodal" 时额外加 image_dense 字段（nullable FLOAT_VECTOR）。
        metadata_fields: [{"key": "title", "type": "text", "fulltext": True, "index": False}, ...]
        fulltext=True 的字段会显式加入 schema 并开启 enable_match，支持 TEXT_MATCH 关键词检索。
        """
        if self.client.has_collection(collection_name):
            logger.info(f"Collection 已存在: {collection_name}")
            return

        schema = MilvusClient.create_schema(enable_dynamic_field=True)
        schema.add_field("chunk_id",    DataType.VARCHAR, max_length=36, is_primary=True)
        schema.add_field("job_id",      DataType.VARCHAR, max_length=128)
        schema.add_field("file_name",   DataType.VARCHAR, max_length=512)
        schema.add_field("chunk_index", DataType.INT64)
        schema.add_field(
            "content", DataType.VARCHAR, max_length=65535,
            enable_analyzer=True,
            analyzer_params=_ANALYZER_PARAMS,
            enable_match=True,
        )
        schema.add_field("sparse_bm25", DataType.SPARSE_FLOAT_VECTOR)
        schema.add_field("dense",       DataType.FLOAT_VECTOR, dim=dim)

        # 多模态知识库：额外加图片向量字段（无图片切片填零向量，FLOAT_VECTOR 不支持 nullable）
        if kb_type == "multimodal":
            schema.add_field(
                "image_dense", DataType.FLOAT_VECTOR, dim=image_vector_dim
            )
            logger.info(f"[Milvus] 多模态 collection，image_dense dim={image_vector_dim}")

        # 用户自定义元数据字段：fulltext=True 的显式加入 schema 并开启倒排索引
        fulltext_fields = []
        for mf in (metadata_fields or []):
            if mf.get("fulltext") and mf.get("key"):
                key = mf["key"]
                schema.add_field(
                    key, DataType.VARCHAR, max_length=1024,
                    enable_analyzer=True,
                    analyzer_params=_ANALYZER_PARAMS,
                    enable_match=True,
                    nullable=True,
                )
                fulltext_fields.append(key)
                logger.info(f"[Milvus] 元数据字段 '{key}' 已加入 schema（enable_match=True）")

        schema.add_function(Function(
            name="bm25",
            function_type=FunctionType.BM25,
            input_field_names=["content"],
            output_field_names="sparse_bm25",
        ))

        index_params = self.client.prepare_index_params()
        index_params.add_index(
            field_name="dense",
            index_name="dense_hnsw",
            index_type="HNSW",
            metric_type="IP",
            params={"M": 16, "efConstruction": 200},
        )
        index_params.add_index(
            field_name="sparse_bm25",
            index_name="sparse_bm25_idx",
            index_type="SPARSE_WAND",
            metric_type="BM25",
        )

        # 多模态：为 image_dense 加 HNSW 索引
        if kb_type == "multimodal":
            index_params.add_index(
                field_name="image_dense",
                index_name="image_dense_hnsw",
                index_type="HNSW",
                metric_type="IP",
                params={"M": 16, "efConstruction": 200},
            )

        self.client.create_collection(
            collection_name=collection_name,
            schema=schema,
            index_params=index_params,
        )
        logger.info(f"Collection 创建成功: {collection_name}")

    def delete_collection(self, collection_name: str) -> None:
        if self.client.has_collection(collection_name):
            self.client.drop_collection(collection_name)
            logger.info(f"Collection 已删除: {collection_name}")

    def list_collections(self) -> List[str]:
        return self.client.list_collections()

    def has_collection(self, collection_name: str) -> bool:
        return self.client.has_collection(collection_name)

    # ── 数据写入 ──────────────────────────────────────────────────────────────

    def upsert_chunks(
        self,
        collection_name: str,
        chunks: List[Dict[str, Any]],
        vector_dim: Optional[int] = None,
        embedding_model: Optional[str] = None,
        metadata_fields: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        批量 upsert 切片到 Milvus。
        metadata_fields: kb 的元数据字段配置，fulltext=True 的字段值会拼接到 content 前面参与 BM25 和 dense 检索。
        
        优化：向量化前剥离图片占位符（<<IMAGE:xxx>>），避免污染向量和 BM25。
        """
        if not chunks:
            return {"upsert_count": 0}

        # 找出需要拼接到 content 的 fulltext 字段
        fulltext_keys = [
            mf["key"] for mf in (metadata_fields or [])
            if mf.get("fulltext") and mf.get("key")
        ]

        embedding_svc = get_embedding_service()
        # 临时切换模型（如果 kb 指定了不同模型）
        original_model = embedding_svc.model
        if embedding_model and embedding_model != original_model:
            embedding_svc.model = embedding_model

        try:
            texts = []
            for c in chunks:
                content = c["content"]
                # 剥离图片占位符（向量化和 BM25 不感知占位符）
                clean_content = _IMAGE_PH_RE.sub('', content).strip()
                
                # fulltext 前缀拼接在 clean_content 上
                if fulltext_keys:
                    meta = c.get("metadata") or {}
                    prefix_parts = [
                        f"{k}：{meta[k]}" for k in fulltext_keys
                        if meta.get(k)
                    ]
                    if prefix_parts:
                        indexed_content = "\n".join(prefix_parts) + "\n\n" + clean_content
                    else:
                        indexed_content = clean_content
                else:
                    indexed_content = clean_content
                texts.append(indexed_content)
            vectors = embedding_svc.embed_texts(texts, dimension=vector_dim)
        finally:
            embedding_svc.model = original_model  # 还原

        if len(vectors) != len(chunks):
            raise RuntimeError(f"Embedding 数量不匹配: {len(vectors)} vs {len(chunks)}")

        # 校验维度
        if vectors and vector_dim and len(vectors[0]) != vector_dim:
            raise RuntimeError(
                f"向量维度不匹配：collection 期望 {vector_dim} 维，"
                f"embedding 实际返回 {len(vectors[0])} 维。"
                f"请检查知识库的 embedding 模型和维度配置。"
            )

        data = []
        for chunk, vec, indexed_content in zip(chunks, vectors, texts):
            row: Dict[str, Any] = {
                "chunk_id":    chunk["chunk_id"],
                "job_id":      chunk.get("job_id", ""),
                "file_name":   chunk.get("file_name", ""),
                "chunk_index": int(chunk.get("chunk_index", 0)),
                "content":     indexed_content,  # fulltext前缀 + clean纯文本（不含占位符），BM25 和 dense 都基于此
                "dense":       vec,
            }
            for k, v in (chunk.get("metadata") or {}).items():
                if k not in row:
                    row[k] = v
            data.append(row)

        batch_size = 200
        total = 0
        for i in range(0, len(data), batch_size):
            batch = data[i: i + batch_size]
            res = self.client.upsert(collection_name=collection_name, data=batch)
            total += res.get("upsert_count", len(batch))

        logger.info(f"[Milvus] upsert {total} 条到 {collection_name}")
        return {"upsert_count": total}

    # ── 删除 ──────────────────────────────────────────────────────────────────

    def delete_by_job(self, collection_name: str, job_id: str) -> None:
        if not self.client.has_collection(collection_name):
            return
        self.client.delete(
            collection_name=collection_name,
            filter=f'job_id == "{job_id}"',
        )
        logger.info(f"[Milvus] 删除 job_id={job_id} from {collection_name}")

    def delete_by_file(self, collection_name: str, file_name: str) -> None:
        if not self.client.has_collection(collection_name):
            return
        escaped = file_name.replace('"', '\\"')
        self.client.delete(
            collection_name=collection_name,
            filter=f'file_name == "{escaped}"',
        )
        logger.info(f"[Milvus] 删除 file_name={file_name} from {collection_name}")

    def delete_by_chunk_ids(self, collection_name: str, chunk_ids: List[str]) -> None:
        if not chunk_ids or not self.client.has_collection(collection_name):
            return
        ids_str = ", ".join(f'"{cid}"' for cid in chunk_ids)
        self.client.delete(
            collection_name=collection_name,
            filter=f"chunk_id in [{ids_str}]",
        )

    # ── 检索 ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _build_text_match_filter(keywords: str, base_filter: Optional[str] = None) -> str:
        """把关键词字符串构建成 TEXT_MATCH filter，多词之间 OR 逻辑"""
        text_match = f"TEXT_MATCH(content, '{keywords}')"
        if base_filter:
            return f"({base_filter}) and {text_match}"
        return text_match

    def hybrid_search(
        self,
        collection_name: str,
        query: str,
        top_k: int = 10,
        filter_expr: Optional[str] = None,
        ranker: str = "RRF",
        rrf_k: int = 60,
        hybrid_alpha: float = 0.5,
        keyword_filter: Optional[str] = None,
        group_by_field: Optional[str] = None,
        group_size: int = 1,
        strict_group_size: bool = False,
        query_image_vector: Optional[List[float]] = None,
        query_text_vector: Optional[List[float]] = None,  # 多模态：外部传入文字向量（qwen3-vl-embedding）
    ) -> List[Dict[str, Any]]:
        """Dense + BM25 双路混合检索。
        keyword_filter: 若传入，先用 TEXT_MATCH 倒排索引预过滤候选集，再做双路 ANN。
        ranker: 'RRF'（默认）或 'Weight'（hybrid_alpha 控制 dense 权重）。
        group_by_field: 分组字段（如 'file_name'），用于多文档场景保证结果多样性。
        group_size: 每组返回的 chunk 数量，默认 1。
        strict_group_size: 是否严格按 group_size 返回，默认 False。
        """
        if not self.client.has_collection(collection_name):
            logger.warning(f"[Milvus] collection 不存在: {collection_name}")
            return []

        # 构建最终 filter：TEXT_MATCH 预过滤 + 可选的标量过滤
        if keyword_filter:
            final_filter = self._build_text_match_filter(keyword_filter, filter_expr)
        else:
            final_filter = filter_expr

        # 文字向量：多模态时用外部传入的（qwen3-vl-embedding），否则用默认 embedding service
        query_vector = query_text_vector if query_text_vector else get_embedding_service().embed_query(query)

        dense_kwargs: Dict[str, Any] = {
            "data": [query_vector],
            "anns_field": "dense",
            "param": {"metric_type": "IP", "params": {"ef": 100}},
            "limit": top_k,
        }
        if final_filter:
            dense_kwargs["expr"] = final_filter

        bm25_kwargs: Dict[str, Any] = {
            "data": [query],
            "anns_field": "sparse_bm25",
            "param": {"metric_type": "BM25", "params": {"drop_ratio_search": 0.2}},
            "limit": top_k,
        }
        if final_filter:
            bm25_kwargs["expr"] = final_filter

        if ranker == "Weight":
            sparse_weight = round(1.0 - hybrid_alpha, 2)
            reranker = WeightedRanker(hybrid_alpha, sparse_weight)
        else:
            reranker = RRFRanker(k=rrf_k)

        output_fields = ["chunk_id", "job_id", "file_name", "chunk_index", "content"]

        reqs = [AnnSearchRequest(**dense_kwargs), AnnSearchRequest(**bm25_kwargs)]

        # 多模态：加入图片向量检索路
        if query_image_vector:
            image_kwargs: Dict[str, Any] = {
                "data": [query_image_vector],
                "anns_field": "image_dense",
                "param": {"metric_type": "IP", "params": {"ef": 100}},
                "limit": top_k,
            }
            if final_filter:
                image_kwargs["expr"] = final_filter
            reqs.append(AnnSearchRequest(**image_kwargs))
            logger.info(f"[Milvus] 多模态检索：加入 image_dense 路")

        search_kwargs: Dict[str, Any] = {
            "collection_name": collection_name,
            "reqs": reqs,
            "ranker": reranker,
            "limit": top_k,
            "output_fields": output_fields,
        }
        if group_by_field:
            search_kwargs["group_by_field"] = group_by_field
            search_kwargs["group_size"] = group_size
            search_kwargs["strict_group_size"] = strict_group_size

        try:
            results = self.client.hybrid_search(**search_kwargs)
        except Exception as e:
            logger.error(f"[Milvus] hybrid_search 失败: {e}")
            raise

        hits = []
        for hit in (results[0] if results else []):
            entity = hit.get("entity", {})
            hits.append({
                "chunk_id":    entity.get("chunk_id") or hit.get("id"),
                "job_id":      entity.get("job_id", ""),
                "file_name":   entity.get("file_name", ""),
                "chunk_index": entity.get("chunk_index", 0),
                "content":     entity.get("content", ""),  # Milvus 存的是 clean 版本（不含占位符）
                "score":       hit.get("distance", 0.0),
                "retrieval_source": 3,  # hybrid
                "metadata":    {
                    k: v for k, v in entity.items()
                    if k not in ("chunk_id", "job_id", "file_name", "chunk_index", "content")
                },
            })

        # 批量回填 PG 原始内容（含图片占位符），供 generate 节点使用
        if hits:
            try:
                from app.db import get_chunk_repository
                chunk_repo = get_chunk_repository()
                chunk_ids = [h["chunk_id"] for h in hits if h.get("chunk_id")]
                if chunk_ids:
                    pg_rows = chunk_repo.get_by_ids(chunk_ids)
                    pg_map = {r["chunk_id"]: r["current_content"] for r in pg_rows}
                    for h in hits:
                        if h["chunk_id"] in pg_map:
                            h["content"] = pg_map[h["chunk_id"]]
                    logger.info(f"[Milvus] 回填 PG 原始内容: {len(pg_map)}/{len(chunk_ids)} 条")
            except Exception as e:
                logger.warning(f"[Milvus] 回填 PG 内容失败（使用 Milvus clean 版本）: {e}")

        mode = f"keyword_filter+hybrid" if keyword_filter else "hybrid"
        logger.info(f"[Milvus] {mode} 返回 {len(hits)} 条 (collection={collection_name})")
        return hits

    def vector_search(
        self,
        collection_name: str,
        query: str,
        top_k: int = 10,
        filter_expr: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """纯 dense 向量检索（备用）"""
        if not self.client.has_collection(collection_name):
            return []

        query_vector = get_embedding_service().embed_query(query)
        search_kwargs: Dict[str, Any] = {
            "collection_name": collection_name,
            "data": [query_vector],
            "anns_field": "dense",
            "search_params": {"metric_type": "IP", "params": {"ef": 100}},
            "limit": top_k,
            "output_fields": ["chunk_id", "job_id", "file_name", "chunk_index", "content"],
        }
        if filter_expr:
            search_kwargs["filter"] = filter_expr

        results = self.client.search(**search_kwargs)
        hits = []
        for hit in (results[0] if results else []):
            entity = hit.get("entity", {})
            hits.append({
                "chunk_id":    entity.get("chunk_id") or hit.get("id"),
                "job_id":      entity.get("job_id", ""),
                "file_name":   entity.get("file_name", ""),
                "chunk_index": entity.get("chunk_index", 0),
                "content":     entity.get("content", ""),
                "score":       hit.get("distance", 0.0),
                "metadata":    {},
            })
        return hits


_instance: Optional[MilvusService] = None


def get_milvus_service() -> MilvusService:
    global _instance
    if _instance is None:
        _instance = MilvusService()
    return _instance
