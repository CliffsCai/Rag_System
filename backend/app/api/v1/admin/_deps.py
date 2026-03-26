# -*- coding: utf-8 -*-
"""公共依赖：管理员凭据、命名空间密码获取"""
from fastapi import HTTPException
from app.core.config import settings
from app.db.namespace_repository import get_namespace_repository


def manager_credentials():
    account = settings.bailian_adb_user
    password = settings.bailian_adb_password
    if not account or not password:
        raise HTTPException(
            status_code=500,
            detail="未配置数据库管理账号，请检查 BAILIAN_ADB_USER / BAILIAN_ADB_PASSWORD"
        )
    return account, password


def get_ns_password(namespace: str) -> str:
    """从注册表取密码，取不到降级用 .env"""
    repo = get_namespace_repository()
    pwd = repo.get_password(namespace)
    if pwd:
        return pwd
    # 降级：单租户场景直接用 .env 中的密码
    fallback = settings.adb_namespace_password
    if fallback:
        return fallback
    raise HTTPException(
        status_code=404,
        detail=f"命名空间 '{namespace}' 未找到密码，请先通过管理页面创建该命名空间"
    )
