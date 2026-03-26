# -*- coding: utf-8 -*-
"""
阿里云 ADB PostgreSQL 向量数据库管理服务
使用官方API进行向量数据库初始化、命名空间和文档集合管理
"""

import logging
import os
import re
from typing import Optional, Dict, Any
from alibabacloud_tea_openapi import models as open_api_models
from alibabacloud_gpdb20160503.client import Client
from alibabacloud_gpdb20160503 import models as gpdb_20160503_models

from app.core.config import settings

logger = logging.getLogger(__name__)


class ADBException(Exception):
    """ADB SDK 异常，携带原始 HTTP 状态码"""

    def __init__(self, message: str, status_code: int = 500):
        super().__init__(message)
        self.status_code = status_code


def parse_sdk_exception(e: Exception, prefix: str = "") -> ADBException:
    """
    将任意异常（含 ADB SDK TeaException）解析为 ADBException，
    尽量保留原始 HTTP 状态码。

    SDK 异常通常把信息序列化在字符串里，格式类似：
      Error: Service.Exception code: 400, ... Response: {'statusCode': 400, ...}
    """
    if isinstance(e, ADBException):
        return e

    status_code = 500
    try:
        # 1. SDK 对象上直接有 status_code 属性
        if hasattr(e, "status_code") and e.status_code:
            status_code = int(e.status_code)
        # 2. 字符串里的 'statusCode': 400
        elif m := re.search(r"'statusCode':\s*(\d+)", str(e)):
            status_code = int(m.group(1))
        # 3. 字符串里的 code: 400
        elif m := re.search(r"\bcode:\s*(\d+)", str(e), re.IGNORECASE):
            status_code = int(m.group(1))
    except Exception:
        pass

    msg = f"{prefix}{e}" if prefix else str(e)
    return ADBException(msg, status_code)

class ADBVectorService:
    """阿里云 ADB PostgreSQL 向量数据库管理服务"""
    
    def __init__(self):
        """初始化服务"""
        # 从环境变量获取配置
        self.access_key_id = os.getenv('ALIBABA_CLOUD_ACCESS_KEY_ID')
        self.access_key_secret = os.getenv('ALIBABA_CLOUD_ACCESS_KEY_SECRET')
        self.instance_id = self._extract_instance_id()
        self.region_id = self._extract_region_id()
        
        # 验证必需的配置
        if not all([self.access_key_id, self.access_key_secret, self.instance_id, self.region_id]):
            raise ValueError("缺少必需的ADB配置参数")
        
        logger.info(f"ADB向量服务初始化: 实例={self.instance_id}, 区域={self.region_id}")
    
    def _extract_instance_id(self) -> str:
        """从环境变量或主机地址提取实例ID"""
        # 优先使用环境变量
        instance_id = os.getenv('ADBPG_INSTANCE_ID')
        if instance_id:
            logger.info(f"从环境变量获取实例ID: {instance_id}")
            return instance_id
        
        # 从主机地址提取
        host = settings.bailian_adb_host
        if not host:
            raise ValueError("BAILIAN_ADB_HOST未配置")
        
        # 格式: gp-xxxxxxxxx-master.gpdb.rds.aliyuncs.com
        instance_id = host.split('-master')[0]
        logger.info(f"从主机地址提取实例ID: {instance_id}")
        return instance_id
    
    def _extract_region_id(self) -> str:
        """从主机地址提取区域ID，或使用环境变量"""
        # 优先使用环境变量
        region = os.getenv('ADBPG_INSTANCE_REGION')
        if region:
            return region
        
        # 从主机地址推断
        host = settings.bailian_adb_host
        if 'cn-shanghai' in host:
            return 'cn-shanghai'
        elif 'cn-beijing' in host:
            return 'cn-beijing'
        elif 'cn-hangzhou' in host:
            return 'cn-hangzhou'
        elif 'cn-shenzhen' in host:
            return 'cn-shenzhen'
        else:
            # 默认使用cn-shanghai
            logger.warning("无法从主机地址推断区域，使用默认区域: cn-shanghai")
            return 'cn-shanghai'
    
    def get_client(self) -> Client:
        """构建并返回ADB API客户端"""
        config = open_api_models.Config(
            access_key_id=self.access_key_id,
            access_key_secret=self.access_key_secret
        )
        config.region_id = self.region_id
        
        # 根据区域设置endpoint
        if self.region_id in ("cn-beijing", "cn-hangzhou", "cn-shanghai", "cn-shenzhen", 
                             "cn-hongkong", "ap-southeast-1"):
            config.endpoint = "gpdb.aliyuncs.com"
        else:
            config.endpoint = f'gpdb.{self.region_id}.aliyuncs.com'
        
        return Client(config)
    
    def create_secret(
        self,
        username: str,
        password: str,
        secret_name: Optional[str] = None,
        description: Optional[str] = None,
        test_connection: bool = True
    ) -> Dict[str, Any]:
        """
        创建访问凭证（Secret）
        
        用于后续需要 SecretArn 的操作（如 ListTables）
        
        Args:
            username: 数据库访问用户名
            password: 数据库访问密码
            secret_name: 凭证名称（可选，默认使用 username）
            description: 凭证描述（可选）
            test_connection: 是否测试连接（默认 True）
            
        Returns:
            包含 SecretArn 和 SecretName 的字典
        """
        try:
            logger.info(f"创建访问凭证: username={username}, secret_name={secret_name}")
            
            request = gpdb_20160503_models.CreateSecretRequest(
                region_id=self.region_id,
                dbinstance_id=self.instance_id,
                username=username,
                password=password,
                secret_name=secret_name,
                description=description,
                test_connection=test_connection
            )
            
            client = self.get_client()
            response = client.create_secret(request)
            
            secret_arn = response.body.secret_arn if hasattr(response.body, 'secret_arn') else None
            secret_name_result = response.body.secret_name if hasattr(response.body, 'secret_name') else None
            
            logger.info(f"✅ 访问凭证创建成功: secret_name={secret_name_result}")
            
            return {
                "success": True,
                "status_code": response.status_code,
                "secret_arn": secret_arn,
                "secret_name": secret_name_result,
                "message": "访问凭证创建成功"
            }
            
        except Exception as e:
            logger.error(f"❌ 创建访问凭证失败: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "message": "创建访问凭证失败"
            }
    
    def delete_secret(
        self,
        secret_arn: str
    ) -> Dict[str, Any]:
        """
        删除访问凭证（Secret）
        
        Args:
            secret_arn: 要删除的 Secret ARN
            
        Returns:
            删除结果字典
        """
        try:
            logger.info(f"删除访问凭证: secret_arn={secret_arn}")
            
            request = gpdb_20160503_models.DeleteSecretRequest(
                region_id=self.region_id,
                dbinstance_id=self.instance_id,
                secret_arn=secret_arn
            )
            
            client = self.get_client()
            response = client.delete_secret(request)
            
            logger.info(f"✅ 访问凭证删除成功")
            
            return {
                "success": True,
                "status_code": response.status_code,
                "message": "访问凭证删除成功"
            }
            
        except Exception as e:
            logger.error(f"❌ 删除访问凭证失败: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "message": "删除访问凭证失败"
            }
    
    def list_secrets(self) -> Dict[str, Any]:
        """
        查询当前实例下所有 Secret 列表。
        返回 {"success": bool, "secrets": [{"secret_name": str, "secret_arn": str, ...}]}
        """
        try:
            request = gpdb_20160503_models.ListSecretsRequest(
                region_id=self.region_id,
                dbinstance_id=self.instance_id,
            )
            client = self.get_client()
            response = client.list_secrets(request)

            secrets = []
            if response.body and hasattr(response.body, "secrets"):
                raw = response.body.secrets
                raw_list = getattr(raw, "secrets", None) or []
                for s in raw_list:
                    if isinstance(s, dict):
                        secrets.append({
                            "secret_name": s.get("SecretName") or s.get("secret_name", ""),
                            "secret_arn": s.get("SecretArn") or s.get("secret_arn", ""),
                            "username": s.get("Username") or s.get("username", ""),
                        })
                    else:
                        secrets.append({
                            "secret_name": getattr(s, "secret_name", "") or getattr(s, "SecretName", ""),
                            "secret_arn": getattr(s, "secret_arn", "") or getattr(s, "SecretArn", ""),
                            "username": getattr(s, "username", "") or getattr(s, "Username", ""),
                        })

            logger.info(f"查询 Secret 列表成功，共 {len(secrets)} 个")
            return {"success": True, "secrets": secrets}
        except Exception as e:
            logger.error(f"查询 Secret 列表失败: {e}")
            return {"success": False, "secrets": [], "error": str(e)}

    def find_secret_arn_by_name(self, secret_name: str) -> Optional[str]:
        """通过 secret_name 查找已存在的 SecretArn，不存在返回 None"""
        result = self.list_secrets()
        for s in result.get("secrets", []):
            if s.get("secret_name") == secret_name:
                return s.get("secret_arn") or None
        return None

    def get_or_create_secret(
        self,
        username: str,
        password: str,
        secret_name: Optional[str] = None
    ) -> Optional[str]:
        """
        获取或创建访问凭证，返回 SecretArn。
        优先通过 ListSecrets 查找同名 Secret 复用，不存在才创建。
        """
        if not secret_name:
            secret_name = self._normalize_secret_name(username)

        # 先查是否已存在
        existing_arn = self.find_secret_arn_by_name(secret_name)
        if existing_arn:
            logger.info(f"复用已有 Secret: {secret_name}")
            return existing_arn

        # 不存在则创建
        result = self.create_secret(username, password, secret_name)
        if result.get("success"):
            return result.get("secret_arn")

        logger.error(f"创建 Secret 失败: {result.get('error')}")
        return None

    @staticmethod
    def _normalize_secret_name(raw: str) -> str:
        import re
        name = re.sub(r"[^a-z0-9_-]", "", (raw or "").strip().lower()) or "sqlsec"
        return name[:20]
    
    def init_vector_database(self, manager_account: str, manager_account_password: str) -> Dict[str, Any]:
        """
        初始化向量数据库Microsoft Teams
        
        作用：
        - 创建knowledgebase库，并赋予此库的读写权限
        - 创建中文分词器和全文检索相关功能（库级别）
        
        Args:
            manager_account: 数据库初始账号
            manager_account_password: 初始账号密码
            
        Returns:
            响应结果字典
        """
        try:
            logger.info("开始初始化向量数据库...")
            
            request = gpdb_20160503_models.InitVectorDatabaseRequest(
                region_id=self.region_id,
                dbinstance_id=self.instance_id,
                manager_account=manager_account,
                manager_account_password=manager_account_password
            )
            
            client = self.get_client()
            response = client.init_vector_database(request)
            
            logger.info(f"✅ 向量数据库初始化成功: status_code={response.status_code}")
            
            return {
                "success": True,
                "status_code": response.status_code,
                "message": "向量数据库初始化成功",
                "body": response.body.to_map() if response.body else {}
            }
            
        except Exception as e:
            logger.error(f"❌ 向量数据库初始化失败: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "message": "向量数据库初始化失败"
            }
    
    def create_namespace(
        self, 
        manager_account: str, 
        manager_account_password: str,
        namespace: str,
        namespace_password: str
    ) -> Dict[str, Any]:
        """
        创建命名空间（Namespace）
        
        命名空间用于隔离不同的文档库，每个命名空间有独立的密码
        
        Args:
            manager_account: 数据库初始账号
            manager_account_password: 初始账号密码
            namespace: 命名空间名称
            namespace_password: 命名空间密码（用于后续数据读写）
            
        Returns:
            响应结果字典
        """
        try:
            logger.info(f"开始创建命名空间: {namespace}")
            
            request = gpdb_20160503_models.CreateNamespaceRequest(
                region_id=self.region_id,
                dbinstance_id=self.instance_id,
                manager_account=manager_account,
                manager_account_password=manager_account_password,
                namespace=namespace,
                namespace_password=namespace_password
            )
            
            client = self.get_client()
            response = client.create_namespace(request)
            
            logger.info(f"✅ 命名空间创建成功: {namespace}, status_code={response.status_code}")
            
            return {
                "success": True,
                "status_code": response.status_code,
                "namespace": namespace,
                "message": f"命名空间 {namespace} 创建成功",
                "body": response.body.to_map() if response.body else {}
            }
            
        except Exception as e:
            logger.error(f"❌ 命名空间创建失败: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "message": f"命名空间 {namespace} 创建失败"
            }
    
    def list_namespaces(
        self,
        manager_account: str,
        manager_account_password: str,
    ) -> Dict[str, Any]:
        """查询命名空间列表（ListNamespaces API）"""
        try:
            request = gpdb_20160503_models.ListNamespacesRequest(
                region_id=self.region_id,
                dbinstance_id=self.instance_id,
                manager_account=manager_account,
                manager_account_password=manager_account_password,
            )
            client = self.get_client()
            response = client.list_namespaces(request)
            namespaces = []
            if response.body and hasattr(response.body, 'namespaces'):
                raw = response.body.namespaces
                if isinstance(raw, list):
                    namespaces = raw
            logger.info(f"✅ 查询命名空间列表成功，共 {len(namespaces)} 个")
            return {"success": True, "namespaces": namespaces, "count": len(namespaces)}
        except Exception as e:
            logger.error(f"❌ 查询命名空间列表失败: {str(e)}")
            return {"success": False, "error": str(e), "namespaces": []}

    def describe_namespace(
        self,
        manager_account: str,
        manager_account_password: str,
        namespace: str,
    ) -> Dict[str, Any]:
        """查询命名空间详情（DescribeNamespace API）"""
        try:
            request = gpdb_20160503_models.DescribeNamespaceRequest(
                region_id=self.region_id,
                dbinstance_id=self.instance_id,
                manager_account=manager_account,
                manager_account_password=manager_account_password,
                namespace=namespace,
            )
            client = self.get_client()
            response = client.describe_namespace(request)
            info = {}
            if response.body and hasattr(response.body, 'namespace_info'):
                raw = response.body.namespace_info
                info = raw if isinstance(raw, dict) else (raw.to_map() if hasattr(raw, 'to_map') else {})
            return {
                "success": True,
                "namespace": namespace,
                "namespace_info": info,
                "status": response.body.status if response.body and hasattr(response.body, 'status') else None,
            }
        except Exception as e:
            logger.error(f"❌ 查询命名空间详情失败: {str(e)}")
            return {"success": False, "error": str(e)}

    def delete_namespace(
        self,
        manager_account: str,
        manager_account_password: str,
        namespace: str,
    ) -> Dict[str, Any]:
        """删除命名空间（DeleteNamespace API）"""
        try:
            request = gpdb_20160503_models.DeleteNamespaceRequest(
                region_id=self.region_id,
                dbinstance_id=self.instance_id,
                manager_account=manager_account,
                manager_account_password=manager_account_password,
                namespace=namespace,
            )
            client = self.get_client()
            response = client.delete_namespace(request)
            logger.info(f"✅ 命名空间删除成功: {namespace}")
            return {
                "success": True,
                "namespace": namespace,
                "message": f"命名空间 {namespace} 删除成功",
                "body": response.body.to_map() if response.body else {}
            }
        except Exception as e:
            logger.error(f"❌ 命名空间删除失败: {str(e)}")
            return {"success": False, "error": str(e), "message": f"命名空间 {namespace} 删除失败"}

    def create_document_collection(
        self,
        manager_account: str,
        manager_account_password: str,
        namespace: str,
        collection: str,
        metadata: Optional[str] = None,
        full_text_retrieval_fields: Optional[str] = None,
        parser: Optional[str] = None,
        embedding_model: Optional[str] = None,
        dimension: Optional[int] = None,
        metrics: Optional[str] = None,
        hnsw_m: Optional[int] = None,
        hnsw_ef_construction: Optional[int] = None,
        pq_enable: Optional[int] = None,
        external_storage: Optional[int] = None,
        metadata_indices: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        创建文档集合（Document Collection）
        
        文档集合用于存储Chunks文本和向量数据
        
        Args:
            manager_account: 数据库初始账号
            manager_account_password: 初始账号密码
            namespace: 命名空间名称
            collection: 文档集合名称
            metadata: 自定义map结构的数据元信息，格式: '{"field1":"type1", "field2":"type2"}'
            full_text_retrieval_fields: 全文检索字段，逗号分隔，必须属于metadata的key
            parser: 分词器，默认zh_cn（中文）
            embedding_model: Embedding模型，如: m3e-small, text-embedding-v3等
            metrics: 向量索引算法
            hnsw_m: HNSW算法中的最大邻居数，范围1～1000
            pq_enable: 是否开启PQ算法加速，0或1
            external_storage: 是否使用外部存储
            
        Returns:
            响应结果字典
        """
        try:
            logger.info(f"开始创建文档集合: namespace={namespace}, collection={collection}")
            
            request = gpdb_20160503_models.CreateDocumentCollectionRequest(
                region_id=self.region_id,
                dbinstance_id=self.instance_id,
                manager_account=manager_account,
                manager_account_password=manager_account_password,
                namespace=namespace,
                collection=collection,
                metadata=metadata,
                full_text_retrieval_fields=full_text_retrieval_fields,
                parser=parser,
                embedding_model=embedding_model,
                dimension=dimension,
                metrics=metrics,
                hnsw_m=hnsw_m,
                hnsw_ef_construction=hnsw_ef_construction,
                pq_enable=pq_enable,
                external_storage=external_storage,
                metadata_indices=metadata_indices,
            )
            
            client = self.get_client()
            response = client.create_document_collection(request)
            
            logger.info(f"✅ 文档集合创建成功: {collection}, status_code={response.status_code}")
            
            return {
                "success": True,
                "status_code": response.status_code,
                "namespace": namespace,
                "collection": collection,
                "message": f"文档集合 {collection} 创建成功",
                "body": response.body.to_map() if response.body else {}
            }
            
        except Exception as e:
            logger.error(f"❌ 文档集合创建失败: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "message": f"文档集合 {collection} 创建失败"
            }
    
    def delete_document_collection(
        self,
        namespace: str,
        collection: str,
        namespace_password: str,
    ) -> Dict[str, Any]:
        """删除文档集合"""
        try:
            logger.info(f"删除文档集合: namespace={namespace}, collection={collection}")
            request = gpdb_20160503_models.DeleteDocumentCollectionRequest(
                region_id=self.region_id,
                dbinstance_id=self.instance_id,
                namespace=namespace,
                collection=collection,
                namespace_password=namespace_password,
            )
            client = self.get_client()
            response = client.delete_document_collection(request)
            logger.info(f"✅ 文档集合删除成功: {collection}")
            return {
                "success": True,
                "status_code": response.status_code,
                "namespace": namespace,
                "collection": collection,
                "message": f"文档集合 {collection} 删除成功",
                "body": response.body.to_map() if response.body else {}
            }
        except Exception as e:
            logger.error(f"❌ 文档集合删除失败: {str(e)}")
            return {"success": False, "error": str(e), "message": f"文档集合 {collection} 删除失败"}

    def list_tables(
        self,
        secret_arn: str,
        database: str = "knowledgebase",
        schema: str = "public",
        table_pattern: Optional[str] = None,
        max_results: int = 100
    ) -> Dict[str, Any]:
        """
        列出数据库中的表
        
        Args:
            secret_arn: 访问凭证 ARN（通过 CreateSecret 创建）
            database: 数据库名称（默认: knowledgebase）
            schema: Schema 名称（默认: public）
            table_pattern: 表名称匹配模式（可选）
            max_results: 返回的最大结果数（默认: 100）
            
        Returns:
            包含表列表的字典
        """
        try:
            logger.info(f"列出数据表: database={database}, schema={schema}")
            
            request = gpdb_20160503_models.ListTablesRequest(
                region_id=self.region_id,
                dbinstance_id=self.instance_id,
                secret_arn=secret_arn,
                database=database,
                schema=schema,
                table_pattern=table_pattern,
                max_results=max_results
            )
            
            client = self.get_client()
            response = client.list_tables(request)
            
            tables = []
            if response.body and hasattr(response.body, 'tables'):
                tables_obj = response.body.tables
                if tables_obj and hasattr(tables_obj, 'tables'):
                    tables = tables_obj.tables if tables_obj.tables else []
            
            logger.info(f"✅ 成功列出 {len(tables)} 个数据表")
            
            return {
                "success": True,
                "status_code": response.status_code,
                "database": database,
                "schema": schema,
                "count": len(tables),
                "tables": tables,
                "message": f"成功列出 {len(tables)} 个数据表"
            }
            
        except Exception as e:
            logger.error(f"❌ 列出数据表失败: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "message": f"列出数据表失败"
            }
    
    def list_document_collections(
        self,
        namespace: str,
        namespace_password: str
    ) -> Dict[str, Any]:
        """
        列出指定命名空间下的所有文档集合
        
        Args:
            namespace: 命名空间名称
            namespace_password: 命名空间密码
            
        Returns:
            包含文档集合列表的字典
        """
        try:
            logger.info(f"列出文档集合: namespace={namespace}")
            
            request = gpdb_20160503_models.ListDocumentCollectionsRequest(
                region_id=self.region_id,
                dbinstance_id=self.instance_id,
                namespace=namespace,
                namespace_password=namespace_password
            )
            
            client = self.get_client()
            response = client.list_document_collections(request)
            
            collections = []
            if response.body and hasattr(response.body, 'items'):
                items = response.body.items
                if items and hasattr(items, 'collection_list'):
                    for collection in items.collection_list:
                        collections.append({
                            "collection_name": collection.collection_name if hasattr(collection, 'collection_name') else None,
                            "embedding_model": collection.embedding_model if hasattr(collection, 'embedding_model') else None,
                            "dimension": collection.dimension if hasattr(collection, 'dimension') else None,
                            "full_text_retrieval_fields": collection.full_text_retrieval_fields if hasattr(collection, 'full_text_retrieval_fields') else None,
                            "metadata": collection.metadata if hasattr(collection, 'metadata') else None,
                            "parser": collection.parser if hasattr(collection, 'parser') else None,
                            "metrics": collection.metrics if hasattr(collection, 'metrics') else None,
                            "support_sparse": collection.support_sparse if hasattr(collection, 'support_sparse') else False,
                            "sparse_retrieval_fields": collection.sparse_retrieval_fields if hasattr(collection, 'sparse_retrieval_fields') else None
                        })
            
            logger.info(f"✅ 成功列出 {len(collections)} 个文档集合")
            
            return {
                "success": True,
                "status_code": response.status_code,
                "namespace": namespace,
                "count": len(collections),
                "collections": collections,
                "message": f"成功列出 {len(collections)} 个文档集合"
            }
            
        except Exception as e:
            logger.error(f"❌ 列出文档集合失败: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "message": f"列出文档集合失败"
            }
    
    def setup_knowledge_base(
        self,
        manager_account: str,
        manager_account_password: str,
        namespace: str = "knowledge_ns",
        namespace_password: str = "Knowledge@2024",
        collection: str = "knowledge_collection",
        embedding_model: str = "text-embedding-v3"
    ) -> Dict[str, Any]:
        """
        一键设置知识库环境
        
        执行完整的初始化流程：
        1. 初始化向量数据库
        2. 创建命名空间
        3. 创建文档集合
        
        Args:
            manager_account: 数据库初始账号
            manager_account_password: 初始账号密码
            namespace: 命名空间名称，默认: knowledge_ns
            namespace_password: 命名空间密码，默认: Knowledge@2024
            collection: 文档集合名称，默认: knowledge_collection
            embedding_model: Embedding模型，默认: text-embedding-v3
            
        Returns:
            包含所有步骤结果的字典
        """
        results = {
            "init_database": None,
            "create_namespace": None,
            "create_collection": None,
            "overall_success": False
        }
        
        try:
            # 步骤1: 初始化向量数据库
            logger.info("=" * 60)
            logger.info("步骤1: 初始化向量数据库")
            logger.info("=" * 60)
            init_result = self.init_vector_database(manager_account, manager_account_password)
            results["init_database"] = init_result
            
            if not init_result.get("success"):
                logger.error("向量数据库初始化失败，终止后续步骤")
                return results
            
            # 步骤2: 创建命名空间
            logger.info("\n" + "=" * 60)
            logger.info("步骤2: 创建命名空间")
            logger.info("=" * 60)
            ns_result = self.create_namespace(
                manager_account, 
                manager_account_password,
                namespace,
                namespace_password
            )
            results["create_namespace"] = ns_result
            
            if not ns_result.get("success"):
                logger.error("命名空间创建失败，终止后续步骤")
                return results
            
            # 步骤3: 创建文档集合
            logger.info("\n" + "=" * 60)
            logger.info("步骤3: 创建文档集合")
            logger.info("=" * 60)
            
            # 定义元数据结构 - 避免使用系统保留字段
            # 系统保留字段: id, vector, doc_name, content, loader_metadata, to_tsvector, source
            # 只使用自定义业务字段
            metadata = '{"title":"text", "author":"text", "category":"text", "page":"int", "section":"text", "url":"text", "doc_type":"text"}'
            full_text_fields = "title"
            
            collection_result = self.create_document_collection(
                manager_account=manager_account,
                manager_account_password=manager_account_password,
                namespace=namespace,
                collection=collection,
                metadata=metadata,
                full_text_retrieval_fields=full_text_fields,
                parser="zh_cn",  # 中文分词器
                embedding_model=embedding_model
            )
            results["create_collection"] = collection_result
            
            if collection_result.get("success"):
                results["overall_success"] = True
                logger.info("\n" + "=" * 60)
                logger.info("🎉 知识库环境设置完成！")
                logger.info("=" * 60)
                logger.info(f"命名空间: {namespace}")
                logger.info(f"文档集合: {collection}")
                logger.info(f"Embedding模型: {embedding_model}")
            else:
                logger.error("文档集合创建失败")
            
            return results
            
        except Exception as e:
            logger.error(f"❌ 知识库环境设置失败: {str(e)}")
            results["error"] = str(e)
            return results


# 全局服务实例
adb_vector_service = None


def get_adb_vector_service() -> ADBVectorService:
    """获取ADB向量服务实例（单例模式）"""
    global adb_vector_service
    if adb_vector_service is None:
        try:
            adb_vector_service = ADBVectorService()
        except Exception as e:
            logger.error(f"初始化ADB向量服务失败: {str(e)}")
            raise e
    return adb_vector_service
