# -*- coding: utf-8 -*-
"""
阿里云 OSS 服务
负责文件上传和临时 URL 生成
"""

import logging
import datetime
from typing import Optional
import urllib3
import alibabacloud_oss_v2 as oss

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from app.core.config import settings

logger = logging.getLogger(__name__)


class OSSService:
    """阿里云 OSS 服务"""

    def __init__(self):
        credentials_provider = oss.credentials.StaticCredentialsProvider(
            access_key_id=settings.oss_access_key_id,
            access_key_secret=settings.oss_access_key_secret,
        )
        cfg = oss.config.load_default()
        cfg.credentials_provider = credentials_provider
        cfg.region = settings.oss_region
        cfg.endpoint = settings.oss_endpoint
        cfg.insecure_skip_verify = True
        self.client = oss.Client(cfg)
        self.bucket = settings.oss_bucket
        logger.info(f"OSS 服务初始化: bucket={self.bucket}, region={settings.oss_region}")

    def upload_file(self, category_name: str, file_name: str, file_content: bytes) -> str:
        """
        上传文件到 OSS

        Args:
            category_name: 类目名称，作为 OSS 目录
            file_name: 文件名
            file_content: 文件二进制内容

        Returns:
            object_key: OSS 对象路径，格式为 类目名/文件名
        """
        object_key = f"{category_name}/{file_name}"
        try:
            result = self.client.put_object(
                oss.PutObjectRequest(
                    bucket=self.bucket,
                    key=object_key,
                    body=file_content,
                )
            )
            logger.info(f"OSS 上传成功: {object_key}, status={result.status_code}")
            return object_key
        except Exception as e:
            logger.error(f"OSS 上传失败: {object_key}, error={e}")
            raise Exception(f"OSS 上传失败: {e}")

    def get_object_bytes(self, object_key: str) -> bytes:
        """用 SDK 直接下载 OSS 对象，返回字节内容（后端专用，不需要预签名）"""
        try:
            result = self.client.get_object(
                oss.GetObjectRequest(bucket=self.bucket, key=object_key)
            )
            with result.body as body:
                data = body.read()
            logger.info(f"OSS 下载成功: {object_key}, size={len(data)}")
            return data
        except Exception as e:
            logger.error(f"OSS 下载失败: {object_key}, error={e}")
            raise Exception(f"OSS 下载失败: {e}")

    def delete_objects(self, object_keys: list) -> int:
        """批量删除 OSS 对象，返回实际删除数量。失败不抛异常，只记录日志。"""
        if not object_keys:
            return 0
        try:
            objects = [oss.DeleteObject(key=k) for k in object_keys]
            result = self.client.delete_multiple_objects(
                oss.DeleteMultipleObjectsRequest(bucket=self.bucket, objects=objects)
            )
            # OSS 默认静默模式：deleted_objects 只含失败项，成功项不返回
            failed = len(result.deleted_objects) if result.deleted_objects else 0
            logger.info(f"OSS 批量删除: 请求 {len(object_keys)} 个, 失败 {failed} 个")
            return len(object_keys) - failed
        except Exception as e:
            logger.error(f"OSS 批量删除失败: {e}")
            return 0

    def get_presigned_url(self, object_key: str, expires: int = 3600) -> str:
        """
        生成临时签名 URL

        Args:
            object_key: OSS 对象路径
            expires: 有效期（秒），默认 3600

        Returns:
            临时访问 URL
        """
        try:
            result = self.client.presign(
                oss.GetObjectRequest(
                    bucket=self.bucket,
                    key=object_key,
                ),
                expires=datetime.timedelta(seconds=expires),
            )
            logger.info(f"生成临时 URL: {object_key}, expires={expires}s")
            return result.url
        except Exception as e:
            logger.error(f"生成临时 URL 失败: {object_key}, error={e}")
            raise Exception(f"生成临时 URL 失败: {object_key}, error={e}")

    def get_presigned_url_by_category(
        self, category_name: str, file_name: str, expires: int = 3600
    ) -> str:
        """通过类目名和文件名生成临时 URL"""
        object_key = f"{category_name}/{file_name}"
        return self.get_presigned_url(object_key, expires)


_instance: Optional[OSSService] = None


def get_oss_service() -> OSSService:
    global _instance
    if _instance is None:
        _instance = OSSService()
    return _instance
