# -*- coding: utf-8 -*-
"""
LangGraph AsyncPostgresSaver 单例
使用 psycopg3 连接池，与业务层 psycopg2 完全隔离
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_checkpointer = None
_pool = None


async def init_checkpointer():
    """应用启动时调用，初始化 psycopg3 连接池 + AsyncPostgresSaver"""
    global _checkpointer, _pool
    if _checkpointer is not None:
        return _checkpointer

    try:
        from psycopg_pool import AsyncConnectionPool
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from app.core.config import settings

        conn_str = (
            f"postgresql://{settings.pg_user}:{settings.pg_password}"
            f"@{settings.pg_host}:{settings.pg_port}/{settings.pg_db}"
        )

        _pool = AsyncConnectionPool(
            conninfo=conn_str,
            min_size=2,
            max_size=10,
            kwargs={"autocommit": True},
            open=False,
        )
        await _pool.open()

        _checkpointer = AsyncPostgresSaver(_pool)
        # setup() 是幂等的，已在 init_db 同步调用过，这里跳过
        logger.info("LangGraph AsyncPostgresSaver 初始化完成")
        return _checkpointer

    except Exception as e:
        logger.error(f"LangGraph checkpointer 初始化失败: {e}")
        # 降级为内存 checkpointer，不影响基本功能
        from langgraph.checkpoint.memory import MemorySaver
        _checkpointer = MemorySaver()
        logger.warning("已降级为 MemorySaver（对话记忆不持久化）")
        return _checkpointer


async def close_checkpointer():
    """应用关闭时调用"""
    global _pool
    if _pool is not None:
        try:
            await _pool.close()
            logger.info("LangGraph checkpointer 连接池已关闭")
        except Exception as e:
            logger.warning(f"关闭 checkpointer 连接池失败: {e}")


def get_checkpointer():
    """同步获取已初始化的 checkpointer（lifespan 之后调用）"""
    return _checkpointer
