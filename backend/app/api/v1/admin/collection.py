# -*- coding: utf-8 -*-
"""知识库（Document Collection）管理：创建、查询列表、删除"""
import logging
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

from app.services.adb_vector_service import get_adb_vector_service
from app.db import get_collection_config_repository
from app.core.config import settings
from ._deps import manager_credentials, get_ns_password

logger = logging.getLogger(__name__)
router = APIRouter()


class MetaFieldConfig(BaseModel):
    key: str
    type: str = "text"
    fulltext: bool = False
    index: bool = False
    auto_inject: Optional[str] = None  # "filename_prefix" | null


class CreateCollectionRequest(BaseModel):
    namespace: str = Field(..., description="命名空间名称")
    collection: str = Field(..., description="知识库名称")
    metadata_fields: Optional[List[MetaFieldConfig]] = Field(default=None, description="元数据字段配置")
    parser: Optional[str] = Field("zh_cn", description="分词器")
    embedding_model: Optional[str] = Field(None, description="Embedding模型")
    dimension: Optional[int] = Field(None, description="向量维度")
    metrics: Optional[str] = Field("cosine", description="向量索引算法")
    hnsw_m: Optional[int] = Field(None, description="HNSW最大邻居数")
    hnsw_ef_construction: Optional[int] = Field(None, description="HNSW构建索引候选集大小")
    pq_enable: Optional[int] = Field(0, description="是否开启PQ算法加速，0或1")
    external_storage: Optional[int] = Field(0, description="是否使用外部存储，0或1")
    image_mode: bool = Field(False, description="是否启用图文模式（自定义切分+图片关联）")


class DeleteCollectionRequest(BaseModel):
    namespace: str = Field(..., description="命名空间名称")
    collection: str = Field(..., description="知识库名称")


def _build_metadata_str(fields: List[MetaFieldConfig]) -> Optional[str]:
    import json
    obj = {f.key: f.type for f in fields if f.key}
    return json.dumps(obj) if obj else None


def _build_fulltext_str(fields: List[MetaFieldConfig]) -> Optional[str]:
    text_types = {"text", "jsonb"}
    keys = [f.key for f in fields if f.key and f.fulltext and f.type in text_types]
    return ",".join(keys) if keys else None


def _build_indices_str(fields: List[MetaFieldConfig]) -> Optional[str]:
    keys = [f.key for f in fields if f.key and f.index]
    return ",".join(keys) if keys else None


@router.post("/collection/create")
async def create_collection(req: CreateCollectionRequest):
    """创建知识库，并将配置写入 knowledge_collection_config"""
    try:
        account, mgr_pwd = manager_credentials()
        vs = get_adb_vector_service()

        fields = req.metadata_fields or []
        metadata_str = _build_metadata_str(fields)
        fulltext_str = _build_fulltext_str(fields)
        indices_str = _build_indices_str(fields)

        result = vs.create_document_collection(
            manager_account=account,
            manager_account_password=mgr_pwd,
            namespace=req.namespace,
            collection=req.collection,
            metadata=metadata_str,
            full_text_retrieval_fields=fulltext_str,
            parser=req.parser,
            embedding_model=req.embedding_model,
            dimension=req.dimension,
            metrics=req.metrics,
            hnsw_m=req.hnsw_m,
            hnsw_ef_construction=req.hnsw_ef_construction,
            pq_enable=req.pq_enable,
            external_storage=req.external_storage,
            metadata_indices=indices_str,
        )
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("message", "创建失败"))

        # 写入 knowledge_collection_config
        config_repo = get_collection_config_repository()
        config_repo.upsert(
            namespace=req.namespace,
            collection=req.collection,
            metadata_fields=[f.model_dump() for f in fields],
            full_text_retrieval_fields=fulltext_str,
            metadata_indices=indices_str,
            parser=req.parser,
            embedding_model=req.embedding_model,
            dimension=req.dimension,
            metrics=req.metrics,
            hnsw_m=req.hnsw_m,
            hnsw_ef_construction=req.hnsw_ef_construction,
            pq_enable=req.pq_enable or 0,
            external_storage=req.external_storage or 0,
            image_mode=req.image_mode,
        )

        return JSONResponse(status_code=200, content={
            "success": True,
            "message": f"知识库 '{req.collection}' 创建成功",
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建知识库失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/collection/list")
async def list_collections(namespace: str = Query(default=None, description="命名空间名称，不传则用默认")):
    """从 knowledge_collection_config 查询知识库列表"""
    try:
        ns = namespace or settings.adb_namespace
        config_repo = get_collection_config_repository()
        collections = config_repo.list_by_namespace(ns)
        return JSONResponse(status_code=200, content={
            "success": True,
            "data": {"collections": collections}
        })
    except Exception as e:
        logger.error(f"查询知识库列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/collection/delete")
async def delete_collection(req: DeleteCollectionRequest):
    """先调 ADB SDK 删除 collection，成功后级联清理本地数据"""
    try:
        # 0. 检查知识库下是否还有文件，有则拒绝删除
        from app.db import get_document_job_repository, get_chunk_repository
        doc_job_repo = get_document_job_repository()
        chunk_repo = get_chunk_repository()
        existing_jobs = doc_job_repo.list_job_ids_by_collection(req.collection)
        if existing_jobs:
            raise HTTPException(
                status_code=400,
                detail=f"知识库下还有 {len(existing_jobs)} 个文件，请先删除所有文件再删除知识库"
            )

        # 1. 调 ADB SDK 删除（失败则直接报错，不删本地数据）
        ns_pwd = get_ns_password(req.namespace)
        result = get_adb_vector_service().delete_document_collection(
            namespace=req.namespace,
            collection=req.collection,
            namespace_password=ns_pwd,
        )
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("message", "ADB 删除失败"))

        # 2. 清理 knowledge_collection_config（文件已在步骤0确认为空，无需清理切片）
        get_collection_config_repository().delete_by_collection(req.namespace, req.collection)

        return JSONResponse(status_code=200, content={
            "success": True,
            "message": f"知识库 '{req.collection}' 已删除"
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除知识库失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
