# -*- coding: utf-8 -*-
"""
PostgreSQL 连接池
提供参数化查询，彻底避免 SQL 注入
"""
import logging
from typing import Any, Dict, List, Optional, Tuple

import psycopg2
import psycopg2.pool
import psycopg2.extras

from app.core.config import settings

logger = logging.getLogger(__name__)

_pool: Optional[psycopg2.pool.ThreadedConnectionPool] = None


def get_pool() -> psycopg2.pool.ThreadedConnectionPool:
    global _pool
    if _pool is None:
        _pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=2,
            maxconn=20,
            host=settings.pg_host,
            port=settings.pg_port,
            dbname=settings.pg_db,
            user=settings.pg_user,
            password=settings.pg_password,
            connect_timeout=10,
            sslmode="disable",
        )
        logger.info(f"PostgreSQL 连接池已创建: {settings.pg_host}:{settings.pg_port}/{settings.pg_db}")
    return _pool


def execute_sql(sql: str, params: Optional[Tuple] = None) -> None:
    """执行 INSERT / UPDATE / DELETE / CREATE，无返回值"""
    pool = get_pool()
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


def execute_returning(sql: str, params: Optional[Tuple] = None) -> List[Dict[str, Any]]:
    """执行带 RETURNING 的 INSERT/UPDATE，返回结果行"""
    pool = get_pool()
    conn = pool.getconn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        conn.commit()
        return [dict(r) for r in rows]
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


def execute_select(sql: str, params: Optional[Tuple] = None) -> List[Dict[str, Any]]:
    """执行 SELECT，返回字典列表"""
    pool = get_pool()
    conn = pool.getconn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        return [dict(r) for r in rows]
    finally:
        pool.putconn(conn)


def execute_many(sql: str, params_list: List[Tuple]) -> None:
    """批量执行，用于 bulk insert"""
    if not params_list:
        return
    pool = get_pool()
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.executemany(sql, params_list)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)
