# -*- coding: utf-8 -*-
"""
类目业务逻辑
"""
import uuid
import logging
from typing import Optional

from app.core.exceptions import NotFoundError, ValidationError, ExternalServiceError
from app.db import get_category_repository, get_category_file_repository
from app.services.oss_service import get_oss_service

logger = logging.getLogger(__name__)


def list_categories() -> dict:
    categories = get_category_repository().list_all()
    return {"categories": categories, "total": len(categories)}


def create_category(name: str, description: Optional[str] = None) -> dict:
    category_id = str(uuid.uuid4())
    return get_category_repository().create(
        category_id=category_id, name=name, description=description
    )


def get_category_with_files(category_id: str) -> dict:
    category = get_category_repository().get(category_id)
    if not category:
        raise NotFoundError("类目不存在")
    files = get_category_file_repository().list_by_category(category_id)
    return {"category": category, "files": files, "file_count": len(files)}


def update_category(category_id: str, name: Optional[str], description: Optional[str]) -> dict:
    repo = get_category_repository()
    if not repo.get(category_id):
        raise NotFoundError("类目不存在")
    repo.update(category_id, name=name, description=description)
    return repo.get(category_id)


def delete_category(category_id: str) -> None:
    cat_repo = get_category_repository()
    cat_file_repo = get_category_file_repository()

    if not cat_repo.get(category_id):
        raise NotFoundError("类目不存在")

    count = cat_file_repo.count_by_category(category_id)
    if count > 0:
        raise ValidationError(f"类目下还有 {count} 个文件，请先删除文件")

    cat_repo.delete(category_id)


def delete_category_file(category_id: str, file_id: str) -> str:
    """删除类目下的文件（OSS + 数据库），返回被删除的文件名"""
    cat_file_repo = get_category_file_repository()
    files = cat_file_repo.list_by_category(category_id)
    record = next((f for f in files if f["id"] == file_id), None)
    if not record:
        raise NotFoundError("文件记录不存在")

    oss_key = record.get("oss_key")
    if oss_key:
        try:
            get_oss_service().delete_objects([oss_key])
        except Exception as e:
            logger.warning("OSS 删除失败（继续）", extra={"oss_key": oss_key, "error": str(e)})

    cat_file_repo.delete(file_id)
    return record["file_name"]


def batch_delete_category_files(category_id: str, file_ids: list[str]) -> dict:
    """批量删除类目下的文件（OSS + 数据库）"""
    cat_file_repo = get_category_file_repository()
    all_files = cat_file_repo.list_by_category(category_id)
    file_map = {f["id"]: f for f in all_files}

    oss_keys, deleted, not_found = [], [], []
    for fid in file_ids:
        record = file_map.get(fid)
        if not record:
            not_found.append(fid)
            continue
        if record.get("oss_key"):
            oss_keys.append(record["oss_key"])
        deleted.append(record["file_name"])

    if oss_keys:
        try:
            get_oss_service().delete_objects(oss_keys)
        except Exception as e:
            logger.warning("OSS 批量删除失败（继续）", extra={"error": str(e)})

    for fid in file_ids:
        if fid in file_map:
            cat_file_repo.delete(fid)

    return {"deleted": deleted, "not_found": not_found}
