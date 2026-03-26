# -*- coding: utf-8 -*-
"""
命名空间注册表仓储
存储多租户命名空间信息，密码 AES-256-GCM 加密后入库
表位于 public schema，不依赖任何 namespace 密码即可访问
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional

from app.db.base_repository import BaseRepository
from app.core.config import settings

logger = logging.getLogger(__name__)

# ── 加密工具 ──────────────────────────────────────────────────────────────────

def _get_cipher_key() -> bytes:
    key_hex = settings.namespace_encrypt_key
    if not key_hex or len(key_hex) < 64:
        raise ValueError("NAMESPACE_ENCRYPT_KEY 未配置或长度不足，需要 32 字节 hex（64字符）")
    return bytes.fromhex(key_hex[:64])


def encrypt_password(plaintext: str) -> str:
    """AES-256-GCM 加密，返回 hex(nonce + tag + ciphertext)"""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    import os as _os
    key = _get_cipher_key()
    nonce = _os.urandom(12)
    aesgcm = AESGCM(key)
    ct = aesgcm.encrypt(nonce, plaintext.encode(), None)  # ct 包含 tag
    return (nonce + ct).hex()


def decrypt_password(ciphertext_hex: str) -> str:
    """解密 encrypt_password 的输出"""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    key = _get_cipher_key()
    raw = bytes.fromhex(ciphertext_hex)
    nonce, ct = raw[:12], raw[12:]
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ct, None).decode()


# ── Repository ────────────────────────────────────────────────────────────────

class NamespaceRepository(BaseRepository):
    """
    namespace_registry 表操作
    schema: public（不依赖 namespace 密码）
    """

    TABLE = "public.namespace_registry"

    def ensure_table(self):
        """建表（幂等）"""
        sql = f"""
        CREATE TABLE IF NOT EXISTS {self.TABLE} (
            namespace        TEXT PRIMARY KEY,
            display_name     TEXT,
            description      TEXT,
            password_enc     TEXT NOT NULL,
            created_by       TEXT,
            created_at       TIMESTAMPTZ DEFAULT NOW(),
            updated_at       TIMESTAMPTZ DEFAULT NOW(),
            extra            JSONB DEFAULT '{{}}'::jsonb
        );
        """
        self._execute_sql(sql)
        logger.info(f"[NamespaceRepo] 表 {self.TABLE} 已就绪")

    def register(
        self,
        namespace: str,
        password: str,
        display_name: Optional[str] = None,
        description: Optional[str] = None,
        created_by: Optional[str] = None,
    ) -> Dict[str, Any]:
        """注册命名空间（upsert）"""
        self.ensure_table()
        enc = encrypt_password(password)
        dn = self._sql_escape(display_name or namespace)
        desc = self._sql_escape(description or "")
        cb = self._sql_escape(created_by or "admin")
        ns = self._sql_escape(namespace)
        sql = f"""
        INSERT INTO {self.TABLE}(namespace, display_name, description, password_enc, created_by, created_at, updated_at)
        VALUES ('{ns}', '{dn}', '{desc}', '{enc}', '{cb}', NOW(), NOW())
        ON CONFLICT (namespace) DO UPDATE SET
            display_name = EXCLUDED.display_name,
            description  = EXCLUDED.description,
            password_enc = EXCLUDED.password_enc,
            updated_at   = NOW();
        """
        self._execute_sql(sql)
        logger.info(f"[NamespaceRepo] 注册命名空间: {namespace}")
        return {"namespace": namespace, "display_name": display_name or namespace}

    def get_password(self, namespace: str) -> Optional[str]:
        """获取命名空间密码（解密）"""
        self.ensure_table()
        ns = self._sql_escape(namespace)
        rows = self._execute_select(
            f"SELECT password_enc FROM {self.TABLE} WHERE namespace = '{ns}' LIMIT 1;"
        )
        if not rows:
            return None
        return decrypt_password(rows[0]["password_enc"])

    def get(self, namespace: str) -> Optional[Dict[str, Any]]:
        """获取命名空间信息（不含密码）"""
        self.ensure_table()
        ns = self._sql_escape(namespace)
        rows = self._execute_select(
            f"SELECT namespace, display_name, description, created_by, created_at, updated_at "
            f"FROM {self.TABLE} WHERE namespace = '{ns}' LIMIT 1;"
        )
        return rows[0] if rows else None

    def list_all(self) -> List[Dict[str, Any]]:
        """列出所有命名空间（不含密码）"""
        self.ensure_table()
        return self._execute_select(
            f"SELECT namespace, display_name, description, created_by, created_at, updated_at "
            f"FROM {self.TABLE} ORDER BY created_at DESC;"
        )

    def delete(self, namespace: str):
        """从注册表删除（不影响 ADB 中的实际命名空间）"""
        self.ensure_table()
        ns = self._sql_escape(namespace)
        self._execute_sql(f"DELETE FROM {self.TABLE} WHERE namespace = '{ns}';")
        logger.info(f"[NamespaceRepo] 删除注册记录: {namespace}")


# ── 单例 ──────────────────────────────────────────────────────────────────────

_repo: Optional[NamespaceRepository] = None


def get_namespace_repository() -> NamespaceRepository:
    global _repo
    if _repo is None:
        _repo = NamespaceRepository()
    return _repo
