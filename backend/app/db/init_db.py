# -*- coding: utf-8 -*-
"""
数据库初始化脚本
按外键依赖顺序建表，幂等（IF NOT EXISTS），应用启动时调用一次。
直接运行此文件也可手动初始化：python -m app.db.init_db
"""
import logging
from app.db.pg_client import execute_sql

logger = logging.getLogger(__name__)

# ── 建表 SQL（按依赖顺序）────────────────────────────────────────────────────

_TABLES = [
    # 1. 知识库
    """
    CREATE TABLE IF NOT EXISTS knowledge_base (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        name            TEXT NOT NULL UNIQUE,
        display_name    TEXT,
        description     TEXT,
        image_mode      BOOLEAN NOT NULL DEFAULT FALSE,
        embedding_model TEXT NOT NULL DEFAULT 'text-embedding-v3',
        vector_dim      INTEGER NOT NULL DEFAULT 1536,
        metadata_fields JSONB NOT NULL DEFAULT '[]',
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    # 已存在的表补列（幂等）
    "ALTER TABLE knowledge_base ADD COLUMN IF NOT EXISTS metadata_fields JSONB NOT NULL DEFAULT '[]'",
    "ALTER TABLE knowledge_base ADD COLUMN IF NOT EXISTS retrieval_config JSONB NOT NULL DEFAULT '{}'",
    "ALTER TABLE knowledge_base ADD COLUMN IF NOT EXISTS kb_type TEXT NOT NULL DEFAULT 'standard'",

    # 2. 类目（独立体系，和知识库无关）
    """
    CREATE TABLE IF NOT EXISTS knowledge_category (
        id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        name        TEXT NOT NULL UNIQUE,
        description TEXT,
        created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,

    # 3. 类目文件（类目视图，只存 OSS 引用）
    """
    CREATE TABLE IF NOT EXISTS knowledge_category_file (
        id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        category_id UUID NOT NULL REFERENCES knowledge_category(id) ON DELETE CASCADE,
        file_name   TEXT NOT NULL,
        oss_key     TEXT NOT NULL,
        created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE(category_id, file_name)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_cat_file_category ON knowledge_category_file(category_id)",

    # 4. 知识库文件（知识库视图）
    """
    CREATE TABLE IF NOT EXISTS knowledge_file (
        id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        kb_id            UUID NOT NULL REFERENCES knowledge_base(id) ON DELETE CASCADE,
        category_file_id UUID REFERENCES knowledge_category_file(id) ON DELETE SET NULL,
        file_name        TEXT NOT NULL,
        oss_key          TEXT NOT NULL,
        file_size        BIGINT,
        mime_type        TEXT,
        status           TEXT NOT NULL DEFAULT 'pending',
        error_msg        TEXT,
        created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE(kb_id, oss_key)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_kb_file_kb ON knowledge_file(kb_id)",
    "CREATE INDEX IF NOT EXISTS idx_kb_file_status ON knowledge_file(status)",

    # 5. 处理任务
    """
    CREATE TABLE IF NOT EXISTS knowledge_job (
        id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        file_id     UUID NOT NULL REFERENCES knowledge_file(id) ON DELETE CASCADE,
        kb_id       UUID NOT NULL REFERENCES knowledge_base(id) ON DELETE CASCADE,
        status      TEXT NOT NULL DEFAULT 'pending',
        stage       TEXT,
        progress    INTEGER NOT NULL DEFAULT 0,
        chunk_count INTEGER,
        vectorized  BOOLEAN NOT NULL DEFAULT FALSE,
        error_msg   TEXT,
        created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_job_file ON knowledge_job(file_id)",
    "CREATE INDEX IF NOT EXISTS idx_job_kb ON knowledge_job(kb_id)",
    "CREATE INDEX IF NOT EXISTS idx_job_status ON knowledge_job(status)",

    # 6. 切片（当前内容）
    """
    CREATE TABLE IF NOT EXISTS knowledge_chunk (
        id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        job_id      UUID NOT NULL REFERENCES knowledge_job(id) ON DELETE CASCADE,
        chunk_index INTEGER NOT NULL,
        content     TEXT NOT NULL,
        is_modified BOOLEAN NOT NULL DEFAULT FALSE,
        metadata    JSONB NOT NULL DEFAULT '{}',
        created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE(job_id, chunk_index)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_chunk_job ON knowledge_chunk(job_id)",

    # 7. 切片原始内容（只写一次，用于撤回）
    """
    CREATE TABLE IF NOT EXISTS knowledge_chunk_origin (
        chunk_id UUID PRIMARY KEY REFERENCES knowledge_chunk(id) ON DELETE CASCADE,
        content  TEXT NOT NULL
    )
    """,

    # 8. 切片图片
    """
    CREATE TABLE IF NOT EXISTS knowledge_chunk_image (
        id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        chunk_id    UUID NOT NULL REFERENCES knowledge_chunk(id) ON DELETE CASCADE,
        placeholder TEXT NOT NULL,
        oss_key     TEXT NOT NULL,
        page        INTEGER,
        sort_order  INTEGER NOT NULL DEFAULT 0,
        created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_chunk_image_chunk ON knowledge_chunk_image(chunk_id)",
    "CREATE INDEX IF NOT EXISTS idx_chunk_image_placeholder ON knowledge_chunk_image(placeholder)",

    # 9. 对话会话元数据
    """
    CREATE TABLE IF NOT EXISTS conversation_session (
        id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id     TEXT NOT NULL DEFAULT 'default',
        kb_name     TEXT NOT NULL,
        title       TEXT NOT NULL DEFAULT '新会话',
        created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_conv_session_user_kb ON conversation_session(user_id, kb_name, updated_at DESC)",

    # 10. 对话消息（业务展示层，独立于 LangGraph checkpoint）
    """
    CREATE TABLE IF NOT EXISTS conversation_message (
        id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        session_id          UUID NOT NULL REFERENCES conversation_session(id) ON DELETE CASCADE,
        role                TEXT NOT NULL,
        content             TEXT NOT NULL,
        sources             JSONB,
        confidence          FLOAT,
        image_placeholders  TEXT[] NOT NULL DEFAULT '{}',
        query_image_oss_key TEXT,
        created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_conv_message_session ON conversation_message(session_id, created_at)",
    "ALTER TABLE conversation_message ADD COLUMN IF NOT EXISTS query_image_oss_key TEXT",
]


def init_db() -> None:
    """按顺序建表，幂等"""
    logger.info("开始初始化数据库表...")
    # 确保 pgcrypto 扩展可用（gen_random_uuid 依赖）
    try:
        execute_sql("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    except Exception:
        pass  # PostgreSQL 13+ 内置 gen_random_uuid，不需要 pgcrypto
    for sql in _TABLES:
        sql = sql.strip()
        if not sql:
            continue
        try:
            execute_sql(sql)
        except Exception as e:
            logger.error(f"建表失败: {e}\nSQL: {sql[:120]}")
            raise

    # 幂等创建 __default__ 类目（单文件直传使用，对用户不可见）
    try:
        execute_sql(
            "INSERT INTO knowledge_category(name, description) VALUES ('__default__', '系统默认类目，单文件直传使用') "
            "ON CONFLICT (name) DO NOTHING"
        )
    except Exception as e:
        logger.warning(f"创建 __default__ 类目失败（可忽略）: {e}")

    # 初始化 LangGraph PostgresSaver checkpoint 表（幂等）
    try:
        from app.core.config import settings as _s
        import psycopg
        conn_str = f"postgresql://{_s.pg_user}:{_s.pg_password}@{_s.pg_host}:{_s.pg_port}/{_s.pg_db}?sslmode=disable"
        with psycopg.connect(conn_str, autocommit=True) as conn:
            from langgraph.checkpoint.postgres import PostgresSaver
            from psycopg.rows import dict_row
            saver = PostgresSaver(conn)
            saver.setup()
        logger.info("LangGraph checkpoint 表初始化完成")
    except Exception as e:
        logger.warning(f"LangGraph checkpoint 表初始化失败（可忽略，首次安装需先 pip install）: {e}")

    logger.info("数据库表初始化完成")


if __name__ == "__main__":
    import sys
    import os
    # 支持直接运行：python -m app.db.init_db
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
    logging.basicConfig(level=logging.INFO)
    init_db()
    print("✅ 数据库初始化完成")
