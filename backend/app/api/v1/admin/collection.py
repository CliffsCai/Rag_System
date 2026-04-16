# -*- coding: utf-8 -*-
"""知识库管理 API（原 collection）"""
from typing import Optional, List
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.db import get_kb_repository
from app.services.milvus_service import get_milvus_service
from app.core.exceptions import NotFoundError, ConflictError

router = APIRouter(prefix="/collections", tags=["admin-collections"])


class MetadataFieldConfig(BaseModel):
    key: str
    type: str = "text"
    fulltext: bool = False
    index: bool = False
    auto_inject: Optional[str] = None


class RetrievalConfig(BaseModel):
    ranker: str = "RRF"
    rrf_k: int = 60
    hybrid_alpha: float = 0.5
    multi_doc_top_k: int = 20
    multi_doc_group_size: int = 3
    strict_group_size: bool = False
    single_doc_top_k: int = 20
    llm_context_top_k: int = 10
    image_vector_dim: int = 1024
    # Rerank 配置
    rerank_enabled: bool = False
    rerank_model_name: str = "qwen3-rerank"
    single_doc_rerank_top_k: int = 5
    multi_doc_rerank_top_k: int = 10


class CreateKbRequest(BaseModel):
    name: str
    display_name: Optional[str] = None
    description: Optional[str] = None
    image_mode: bool = False
    kb_type: str = "standard"               # "standard" | "multimodal"
    embedding_model: str = "text-embedding-v3"
    vector_dim: int = 1536
    metadata_fields: Optional[List[MetadataFieldConfig]] = None
    retrieval_config: Optional[RetrievalConfig] = None


class UpdateKbRequest(BaseModel):
    display_name: Optional[str] = None
    description: Optional[str] = None
    image_mode: Optional[bool] = None
    retrieval_config: Optional[RetrievalConfig] = None


@router.get("")
async def list_collections():
    kbs = get_kb_repository().list_all()
    return JSONResponse(content={"success": True, "data": {"collections": kbs, "total": len(kbs)}})


@router.post("")
async def create_collection(req: CreateKbRequest):
    kb_repo = get_kb_repository()
    if kb_repo.get_by_name(req.name):
        raise ConflictError(f"知识库「{req.name}」已存在")

    mf = [f.model_dump() for f in req.metadata_fields] if req.metadata_fields else []
    rc = req.retrieval_config.model_dump() if req.retrieval_config else {}

    # 多模态 kb：强制使用 qwen3-vl-embedding，且 dense 和 image_dense 维度必须一致
    embedding_model = req.embedding_model
    vector_dim = req.vector_dim
    if req.kb_type == "multimodal":
        embedding_model = "qwen3-vl-embedding"
        image_vector_dim = rc.get("image_vector_dim", 1024)
        vector_dim = image_vector_dim  # dense 和 image_dense 用同一维度
        rc["image_vector_dim"] = image_vector_dim

    # 在 Milvus 中创建 collection（传入 metadata_fields 以建倒排索引）
    get_milvus_service().get_or_create_collection(
        collection_name=req.name,
        dim=vector_dim,
        image_mode=req.image_mode,
        metadata_fields=mf,
        kb_type=req.kb_type,
        image_vector_dim=rc.get("image_vector_dim", 1024),
    )

    # 在 PG 中记录配置
    kb = kb_repo.create(
        name=req.name,
        display_name=req.display_name,
        description=req.description,
        image_mode=req.image_mode,
        kb_type=req.kb_type,
        embedding_model=embedding_model,
        vector_dim=vector_dim,
        metadata_fields=mf,
        retrieval_config=rc,
    )
    return JSONResponse(content={"success": True, "message": f"知识库「{req.name}」创建成功", "data": kb})


@router.get("/{kb_name}")
async def get_collection(kb_name: str):
    kb = get_kb_repository().get_by_name(kb_name)
    if not kb:
        raise NotFoundError(f"知识库「{kb_name}」不存在")
    return JSONResponse(content={"success": True, "data": kb})


@router.put("/{kb_name}")
async def update_collection(kb_name: str, req: UpdateKbRequest):
    kb_repo = get_kb_repository()
    kb = kb_repo.get_by_name(kb_name)
    if not kb:
        raise NotFoundError(f"知识库「{kb_name}」不存在")
    updated = kb_repo.update(
        kb["id"],
        display_name=req.display_name,
        description=req.description,
        image_mode=req.image_mode,
        retrieval_config=req.retrieval_config.model_dump() if req.retrieval_config else None,
    )
    return JSONResponse(content={"success": True, "data": updated})


@router.delete("/{kb_name}")
async def delete_collection(kb_name: str):
    kb_repo = get_kb_repository()
    kb = kb_repo.get_by_name(kb_name)
    if not kb:
        raise NotFoundError(f"知识库「{kb_name}」不存在")

    # 检查是否有文件
    from app.db import get_file_repository
    files = get_file_repository().list_by_kb(kb["id"], limit=1)
    if files:
        raise ConflictError(f"知识库「{kb_name}」中还有文件，请先删除所有文件后再删除知识库")

    # 删除 Milvus collection
    try:
        get_milvus_service().delete_collection(kb_name)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Milvus collection 删除失败（继续）: {e}")

    # 删除 PG 记录（级联删除 file/job/chunk）
    kb_repo.delete(kb["id"])
    return JSONResponse(content={"success": True, "message": f"知识库「{kb_name}」已删除"})
