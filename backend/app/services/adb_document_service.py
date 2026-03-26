# -*- coding: utf-8 -*-
"""
ADB文档管理服务
处理文档的上传、查询、删除等操作
"""

import logging
import io
import time
import json
from typing import Dict, List, Any, Optional
from pathlib import Path
from urllib.request import urlopen

from alibabacloud_tea_util import models as util_models
from alibabacloud_gpdb20160503 import models as gpdb_20160503_models

from app.services.adb_vector_service import get_adb_vector_service, ADBException, parse_sdk_exception
from app.core.config import settings

logger = logging.getLogger(__name__)


class ADBDocumentService:
    """ADB文档管理服务"""
    
    def __init__(self, namespace: Optional[str] = None, collection: Optional[str] = None):
        """
        初始化服务
        
        Args:
            namespace: 命名空间（可选，默认使用配置文件）
            collection: 文档集合（可选，默认使用配置文件）
        """
        self.vector_service = get_adb_vector_service()
        self.namespace = namespace or settings.adb_namespace
        self.namespace_password = settings.adb_namespace_password
        self.collection = collection or settings.adb_collection
        
        logger.info(f"文档服务初始化: namespace={self.namespace}, collection={self.collection}")
    
    @staticmethod
    def resolve_document_loader(file_name: str, loader_name: Optional[str]) -> Optional[str]:
        """
        根据文件扩展名决定是否使用指定的 document_loader_name。
        只有 PDF 文件才传入 loader_name；其他格式传 None，让 ADB 自动匹配。
        """
        if not loader_name:
            return None
        ext = "." + file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
        return loader_name if ext == ".pdf" else None

    def upload_document_async(
        self,
        file_name: str,
        file_content: bytes,
        metadata: Optional[Dict[str, Any]] = None,
        chunk_size: int = 800,
        chunk_overlap: int = 100,
        zh_title_enhance: bool = True,
        vl_enhance: bool = False,
        dry_run: bool = True,
        document_loader_name: Optional[str] = None,
        text_splitter_name: Optional[str] = None,
        separators: Optional[str] = None,
        splitter_model: Optional[str] = None,
        use_full_text_retrieval: bool = True
    ) -> str:
        """
        异步上传文档
        
        Args:
            file_name: 文档名称（带扩展名）
            file_content: 文档二进制内容
            metadata: 自定义元数据（必须符合创建collection时定义的结构）
            chunk_size: 文档切分大小，默认800，最大2048
            chunk_overlap: 切分重叠大小，默认100
            zh_title_enhance: 是否开启中文标题加强，默认True
            vl_enhance: 是否开启VL增强内容识别，默认False
            dry_run: 是否只切分不入库，默认False
            document_loader_name: 文档加载器名称（可选，留空自动匹配）
            text_splitter_name: 文本切分器名称（可选）
            separators: 切分分隔符（可选）
            splitter_model: 切分模型（仅当text_splitter_name为LLMSplitter时使用）
            use_full_text_retrieval: 是否使用全文检索，默认True
            
        Returns:
            job_id: 上传任务ID
        """
        try:
            logger.info(f"开始上传文档: {file_name}, 大小: {len(file_content)} bytes")
            
            # 只有 PDF 文件才传 document_loader_name，其他格式传 None 让 ADB 自动匹配
            resolved_loader = self.resolve_document_loader(file_name, document_loader_name)
            
            logger.info(f"参数: chunk_size={chunk_size}, chunk_overlap={chunk_overlap}, "
                       f"zh_title_enhance={zh_title_enhance}, vl_enhance={vl_enhance}, "
                       f"dry_run={dry_run}, document_loader_name={resolved_loader}, "
                       f"text_splitter_name={text_splitter_name}, splitter_model={splitter_model}")
            
            # 构建请求
            request = gpdb_20160503_models.UploadDocumentAsyncAdvanceRequest(
                region_id=self.vector_service.region_id,
                dbinstance_id=self.vector_service.instance_id,
                namespace=self.namespace,
                namespace_password=self.namespace_password,
                collection=self.collection,
                file_name=file_name,
                file_url_object=io.BytesIO(file_content),
                metadata=metadata,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                zh_title_enhance=zh_title_enhance,
                vl_enhance=vl_enhance,
                dry_run=dry_run
            )
            
            # 添加可选参数
            if resolved_loader:
                request.document_loader_name = resolved_loader
            if text_splitter_name:
                request.text_splitter_name = text_splitter_name
            if separators:
                request.separators = separators
            if splitter_model:
                request.splitter_model = splitter_model
            
            # 设置更长的超时时间（60秒连接超时，300秒读取超时）
            runtime_options = util_models.RuntimeOptions(
                connect_timeout=60000,  # 60秒
                read_timeout=300000     # 300秒（5分钟）
            )
            
            client = self.vector_service.get_client()
            response = client.upload_document_async_advance(
                request, 
                runtime_options
            )
            
            job_id = response.body.job_id
            logger.info(f"✅ 文档上传任务创建成功: job_id={job_id}")
            
            return job_id
            
        except Exception as e:
            logger.error(f"❌ 文档上传失败: {str(e)}")
            raise parse_sdk_exception(e, "文档上传失败: ")
    
    def upload_document_from_url(
        self,
        file_name: str,
        file_url: str,
        metadata: Optional[Dict[str, Any]] = None,
        chunk_size: int = 800,
        chunk_overlap: int = 100,
        zh_title_enhance: bool = True,
        vl_enhance: bool = False,
        dry_run: bool = False,
        document_loader_name: Optional[str] = None,
        text_splitter_name: Optional[str] = None,
    ) -> str:
        """
        通过 URL 异步上传文档（调用 UploadDocumentAsync，适用于 OSS 临时 URL）

        Args:
            file_name: 文档名称（带扩展名）
            file_url: 文件可访问的 URL（如 OSS 临时签名 URL）
            其余参数同 upload_document_async

        Returns:
            job_id: 上传任务ID
        """
        try:
            logger.info(f"[UploadFromURL] 开始上传: {file_name}, url={file_url[:60]}...")

            resolved_loader = self.resolve_document_loader(file_name, document_loader_name)

            request = gpdb_20160503_models.UploadDocumentAsyncRequest(
                region_id=self.vector_service.region_id,
                dbinstance_id=self.vector_service.instance_id,
                namespace=self.namespace,
                namespace_password=self.namespace_password,
                collection=self.collection,
                file_name=file_name,
                file_url=file_url,
                metadata=metadata,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                zh_title_enhance=zh_title_enhance,
                vl_enhance=vl_enhance,
                dry_run=dry_run,
            )

            if resolved_loader:
                request.document_loader_name = resolved_loader
            if text_splitter_name:
                request.text_splitter_name = text_splitter_name

            client = self.vector_service.get_client()
            response = client.upload_document_async(request)

            job_id = response.body.job_id
            logger.info(f"[UploadFromURL] 任务创建成功: job_id={job_id}")
            return job_id

        except Exception as e:
            logger.error(f"[UploadFromURL] 上传失败: {e}")
            raise parse_sdk_exception(e, "URL 文档上传失败: ")

    def wait_upload_job(
        self, 
        job_id: str, 
        timeout: int = 300,
        check_interval: int = 2
    ) -> Dict[str, Any]:
        """
        等待上传任务完成
        
        Args:
            job_id: 任务ID
            timeout: 超时时间（秒），默认300秒
            check_interval: 检查间隔（秒），默认2秒
            
        Returns:
            任务结果信息
        """
        try:
            logger.info(f"等待上传任务完成: job_id={job_id}")
            
            start_time = time.time()
            
            while True:
                # 检查超时
                if time.time() - start_time > timeout:
                    raise Exception(f"上传任务超时: {timeout}秒")
                
                # 查询任务状态
                request = gpdb_20160503_models.GetUploadDocumentJobRequest(
                    region_id=self.vector_service.region_id,
                    dbinstance_id=self.vector_service.instance_id,
                    namespace=self.namespace,
                    namespace_password=self.namespace_password,
                    collection=self.collection,
                    job_id=job_id
                )
                
                client = self.vector_service.get_client()
                response = client.get_upload_document_job(request)
                
                job = response.body.job
                
                if job.completed:
                    logger.info(f"✅ 文档上传完成: job_id={job_id}")
                    return {
                        "job_id": job_id,
                        "status": job.status,
                        "completed": True,
                        "message": job.message if hasattr(job, 'message') else "上传成功"
                    }
                
                # 检查是否失败
                if hasattr(job, 'status') and job.status == 'failed':
                    error_msg = job.message if hasattr(job, 'message') else "未知错误"
                    raise Exception(f"上传任务失败: {error_msg}")
                
                # 等待后重试
                time.sleep(check_interval)
                
        except Exception as e:
            logger.error(f"❌ 等待上传任务失败: {str(e)}")
            raise parse_sdk_exception(e, "等待上传任务失败: ")

    def get_upload_job_detail(self, job_id: str) -> Dict[str, Any]:
        """
        获取上传任务详情（状态/进度/错误/ChunkResult URL）

        Args:
            job_id: 任务ID

        Returns:
            任务详情字典
        """
        try:
            request = gpdb_20160503_models.GetUploadDocumentJobRequest(
                region_id=self.vector_service.region_id,
                dbinstance_id=self.vector_service.instance_id,
                namespace=self.namespace,
                namespace_password=self.namespace_password,
                collection=self.collection,
                job_id=job_id
            )

            client = self.vector_service.get_client()
            response = client.get_upload_document_job(request)

            job = response.body.job if hasattr(response.body, 'job') else None

            # 用 to_map() 取 ChunkResult，避免 SDK 空对象陷阱
            # SDK 预定义属性即使内容为空，hasattr/getattr 也不返回 None
            chunk_file_url_val = None
            plain_url_val = None
            doc_loader_url_val = None
            try:
                body_map = response.body.to_map() or {}
                cr_map = body_map.get("ChunkResult") or body_map.get("chunk_result") or {}
                chunk_file_url_val = cr_map.get("ChunkFileUrl") or cr_map.get("chunk_file_url")
                plain_url_val = cr_map.get("PlainChunkFileUrl") or cr_map.get("plain_chunk_file_url")
                doc_loader_url_val = cr_map.get("DocumentLoaderResultFileUrl") or cr_map.get("document_loader_result_file_url")
                logger.info(f"[GetJobDetail] to_map chunk_file_url={chunk_file_url_val}")
            except Exception as map_err:
                logger.warning(f"[GetJobDetail] to_map() 失败，降级用属性访问: {map_err}")
                body_cr = getattr(response.body, 'chunk_result', None)
                if body_cr is not None:
                    chunk_file_url_val = getattr(body_cr, 'chunk_file_url', None)
                    plain_url_val = getattr(body_cr, 'plain_chunk_file_url', None)
                    doc_loader_url_val = getattr(body_cr, 'document_loader_result_file_url', None)

            def pick(obj, snake: str, camel: str):
                if obj is None:
                    return None
                if hasattr(obj, snake):
                    return getattr(obj, snake)
                if hasattr(obj, camel):
                    return getattr(obj, camel)
                return None

            detail = {
                "job_id": job_id,
                "completed": pick(job, 'completed', 'Completed') if job else None,
                "status": pick(job, 'status', 'Status') if job else None,
                "progress": pick(job, 'progress', 'Progress') if job else None,
                "error": pick(job, 'error', 'Error') if job else None,
                "error_code": pick(job, 'error_code', 'ErrorCode') if job else None,
                "message": response.body.message if hasattr(response.body, 'message') else None,
                "request_id": response.body.request_id if hasattr(response.body, 'request_id') else None,
                "chunk_file_url": chunk_file_url_val,
                "plain_chunk_file_url": plain_url_val,
                "document_loader_result_file_url": doc_loader_url_val,
            }

            return detail
        except Exception as e:
            logger.error(f"获取上传任务详情失败: {str(e)}")
            raise parse_sdk_exception(e, "获取上传任务详情失败: ")

    def cancel_upload_job(self, job_id: str) -> Dict[str, Any]:
        """
        取消上传任务

        Args:
            job_id: 任务ID

        Returns:
            取消结果
        """
        try:
            request = gpdb_20160503_models.CancelUploadDocumentJobRequest(
                region_id=self.vector_service.region_id,
                dbinstance_id=self.vector_service.instance_id,
                namespace=self.namespace,
                namespace_password=self.namespace_password,
                collection=self.collection,
                job_id=job_id
            )

            client = self.vector_service.get_client()
            response = client.cancel_upload_document_job(request)

            return {
                "status": response.body.status if hasattr(response.body, 'status') else "success",
                "message": response.body.message if hasattr(response.body, 'message') else "任务取消成功",
                "request_id": response.body.request_id if hasattr(response.body, 'request_id') else None,
                "job_id": job_id
            }
        except Exception as e:
            logger.error(f"取消上传任务失败: {str(e)}")
            raise parse_sdk_exception(e, "取消上传任务失败: ")
    
    def list_documents(self) -> List[Dict[str, Any]]:
        """
        查询文档列表
        
        Returns:
            文档列表
        """
        try:
            logger.info("查询文档列表")
            
            request = gpdb_20160503_models.ListDocumentsRequest(
                region_id=self.vector_service.region_id,
                dbinstance_id=self.vector_service.instance_id,
                namespace=self.namespace,
                namespace_password=self.namespace_password,
                collection=self.collection
            )
            
            client = self.vector_service.get_client()
            response = client.list_documents(request)
            
            documents = []
            if response.body and hasattr(response.body, 'documents'):
                docs = response.body.documents
                if docs:
                    for doc in docs:
                        documents.append({
                            "file_name": doc.file_name if hasattr(doc, 'file_name') else None,
                            "doc_size": doc.doc_size if hasattr(doc, 'doc_size') else None,
                            "chunk_count": doc.chunk_count if hasattr(doc, 'chunk_count') else None,
                            "upload_time": doc.upload_time if hasattr(doc, 'upload_time') else None
                        })
            
            logger.info(f"✅ 查询到 {len(documents)} 个文档")
            return documents
            
        except Exception as e:
            logger.error(f"❌ 查询文档列表失败: {str(e)}")
            raise parse_sdk_exception(e, "查询文档列表失败: ")
    
    def describe_document(self, file_name: str) -> Dict[str, Any]:
        """
        查询文档详情
        
        Args:
            file_name: 文档名称
            
        Returns:
            文档详细信息
        """
        try:
            logger.info(f"查询文档详情: {file_name}")
            
            request = gpdb_20160503_models.DescribeDocumentRequest(
                region_id=self.vector_service.region_id,
                dbinstance_id=self.vector_service.instance_id,
                namespace=self.namespace,
                namespace_password=self.namespace_password,
                collection=self.collection,
                file_name=file_name
            )
            
            client = self.vector_service.get_client()
            response = client.describe_document(request)
            
            if response.body:
                doc = response.body
                return {
                    "file_name": doc.file_name if hasattr(doc, 'file_name') else None,
                    "doc_size": doc.doc_size if hasattr(doc, 'doc_size') else None,
                    "chunk_count": doc.chunk_count if hasattr(doc, 'chunk_count') else None,
                    "upload_time": doc.upload_time if hasattr(doc, 'upload_time') else None,
                    "metadata": doc.metadata if hasattr(doc, 'metadata') else None
                }
            
            return {}
            
        except Exception as e:
            logger.error(f"❌ 查询文档详情失败: {str(e)}")
            raise parse_sdk_exception(e, "查询文档详情失败: ")
    
    def delete_document(self, file_name: str) -> bool:
        """
        删除文档
        
        Args:
            file_name: 文档名称
            
        Returns:
            是否删除成功
        """
        try:
            logger.info(f"删除文档: {file_name}")
            
            request = gpdb_20160503_models.DeleteDocumentRequest(
                region_id=self.vector_service.region_id,
                dbinstance_id=self.vector_service.instance_id,
                namespace=self.namespace,
                namespace_password=self.namespace_password,
                collection=self.collection,
                file_name=file_name
            )
            
            client = self.vector_service.get_client()
            response = client.delete_document(request)
            
            logger.info(f"✅ 文档删除成功: {file_name}")
            return True
            
        except Exception as e:
            logger.error(f"❌ 删除文档失败: {str(e)}")
            raise parse_sdk_exception(e, "删除文档失败: ")
    
    def query_content(
        self,
        query: str,
        top_k: int = 10,
        filter_str: Optional[str] = None,
        rerank_factor: Optional[float] = None,
        hybrid_search: Optional[str] = None,
        hybrid_search_args: Optional[Dict[str, Any]] = None,
        include_file_url: bool = False
    ) -> List[Dict[str, Any]]:
        """
        检索文档内容（支持向量检索 + 全文检索混合）
        
        Args:
            query: 查询文本
            top_k: 返回结果数量
            filter_str: 过滤条件（SQL WHERE语法）
            rerank_factor: 重排因子(1-5)
            hybrid_search: 多路召回算法(RRF/Weight/Cascaded)
            hybrid_search_args: 多路召回算法参数
            include_file_url: 是否返回文件URL
            
        Returns:
            检索结果列表
        """
        try:
            logger.info(f"检索文档: query={query}, top_k={top_k}, hybrid_search={hybrid_search}")
            
            request = gpdb_20160503_models.QueryContentRequest(
                region_id=self.vector_service.region_id,
                dbinstance_id=self.vector_service.instance_id,
                namespace=self.namespace,
                namespace_password=self.namespace_password,
                collection=self.collection,
                content=query,
                top_k=top_k,
                filter=filter_str,
                include_file_url=include_file_url
            )
            
            # 添加可选参数
            if rerank_factor is not None:
                request.rerank_factor = rerank_factor
            
            if hybrid_search:
                request.hybrid_search = hybrid_search
            
            if hybrid_search_args:
                request.hybrid_search_args = hybrid_search_args
            
            client = self.vector_service.get_client()
            response = client.query_content(request)
            
            results = []
            if response.body and hasattr(response.body, 'matches'):
                matches = response.body.matches
                if matches and hasattr(matches, 'match_list'):
                    for match in matches.match_list:
                        # 处理 metadata - 可能是字符串或字典
                        metadata = None
                        if hasattr(match, 'metadata') and match.metadata:
                            if isinstance(match.metadata, dict):
                                metadata = match.metadata
                            elif isinstance(match.metadata, str):
                                try:
                                    import json
                                    metadata = json.loads(match.metadata)
                                except:
                                    metadata = {}
                        
                        # 处理 loader_metadata - 可能是字符串或字典
                        loader_metadata = None
                        if hasattr(match, 'loader_metadata') and match.loader_metadata:
                            if isinstance(match.loader_metadata, dict):
                                loader_metadata = match.loader_metadata
                            elif isinstance(match.loader_metadata, str):
                                try:
                                    import json
                                    loader_metadata = json.loads(match.loader_metadata)
                                except:
                                    loader_metadata = {}
                        
                        result = {
                            "id": match.id if hasattr(match, 'id') else None,
                            "file_name": match.file_name if hasattr(match, 'file_name') else None,
                            "content": match.content if hasattr(match, 'content') else None,
                            "score": match.score if hasattr(match, 'score') else None,
                            "metadata": metadata,
                            "loader_metadata": loader_metadata,
                            "retrieval_source": match.retrieval_source if hasattr(match, 'retrieval_source') else None
                        }
                        
                        # 添加rerank_score
                        if hasattr(match, 'rerank_score'):
                            result["rerank_score"] = match.rerank_score
                        
                        # 添加file_url
                        if hasattr(match, 'file_url'):
                            result["file_url"] = match.file_url
                        
                        results.append(result)
            
            logger.info(f"✅ 检索到 {len(results)} 个结果")
            return results
            
        except Exception as e:
            logger.error(f"❌ 检索失败: {str(e)}")
            raise parse_sdk_exception(e, "检索失败: ")

    def preview_document_chunks(
        self,
        file_name: str,
        file_content: bytes,
        metadata: Optional[Dict[str, Any]] = None,
        chunk_size: int = 800,
        chunk_overlap: int = 100,
        zh_title_enhance: bool = True,
        vl_enhance: bool = False,
        document_loader_name: Optional[str] = None,
        text_splitter_name: Optional[str] = None,
        separators: Optional[str] = None,
        splitter_model: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        预览文档切分结果（dry_run模式）
        
        Args:
            file_name: 文档名称
            file_content: 文档二进制内容
            metadata: 自定义元数据
            chunk_size: 文档切分大小
            chunk_overlap: 切分重叠大小
            zh_title_enhance: 是否开启中文标题加强
            vl_enhance: 是否开启VL增强内容识别
            document_loader_name: 文档加载器名称
            text_splitter_name: 文本切分器名称
            separators: 切分分隔符
            splitter_model: 切分模型
            
        Returns:
            包含切分结果的字典，包括 job_id 和 chunks 列表
        """
        try:
            logger.info(f"[PreviewChunks] 开始预览文档切分: {file_name}")
            
            # 使用 dry_run=True 调用上传接口
            job_id = self.upload_document_async(
                file_name=file_name,
                file_content=file_content,
                metadata=metadata,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                zh_title_enhance=zh_title_enhance,
                vl_enhance=vl_enhance,
                dry_run=True,  # 关键：只切分不上传
                document_loader_name=document_loader_name,
                text_splitter_name=text_splitter_name,
                separators=separators,
                splitter_model=splitter_model
            )
            
            logger.info(f"[PreviewChunks] 切分任务创建: job_id={job_id}")
            
            # 等待切分完成
            result = self.wait_upload_job(job_id)
            
            # 获取切分结果
            chunks_result = self.get_upload_job_chunks(job_id)
            
            logger.info(f"[PreviewChunks] 切分完成，共 {len(chunks_result.get('chunks', []))} 个切片")
            
            return {
                "job_id": job_id,
                "file_name": file_name,
                "chunks": chunks_result.get("chunks", []),
                "total_chunks": len(chunks_result.get("chunks", [])),
                "status": "success"
            }
            
        except Exception as e:
            logger.error(f"[PreviewChunks] 预览切分失败: {str(e)}")
            raise parse_sdk_exception(e, "预览切分失败: ")
    
    def get_upload_job_chunks(self, job_id: str) -> Dict[str, Any]:
        """
        获取上传任务的切分结果
        
        Args:
            job_id: 任务ID
            
        Returns:
            切分结果，包含 chunks 列表
        """
        try:
            logger.info(f"[GetJobChunks] 获取任务切分结果: job_id={job_id}")
            
            request = gpdb_20160503_models.GetUploadDocumentJobRequest(
                region_id=self.vector_service.region_id,
                dbinstance_id=self.vector_service.instance_id,
                namespace=self.namespace,
                namespace_password=self.namespace_password,
                collection=self.collection,
                job_id=job_id
            )
            
            client = self.vector_service.get_client()
            response = client.get_upload_document_job(request)
            
            job = response.body.job
            chunks = []
            chunk_result_info: Dict[str, Any] = {}

            # 提取 Job 关键状态
            if job:
                chunk_result_info["job_status"] = job.status if hasattr(job, 'status') else None
                chunk_result_info["job_progress"] = job.progress if hasattr(job, 'progress') else None
                chunk_result_info["job_error"] = job.error if hasattr(job, 'error') else None
                chunk_result_info["job_error_code"] = job.error_code if hasattr(job, 'error_code') else None
                
                logger.info(f"[GetJobChunks] 任务状态: status={chunk_result_info['job_status']}, "
                           f"progress={chunk_result_info['job_progress']}, "
                           f"error={chunk_result_info['job_error']}")
            
            # 用 to_map() 取 ChunkResult，避免 SDK 空对象陷阱
            chunk_file_url = None
            plain_chunk_file_url = None
            document_loader_result_file_url = None
            try:
                body_map = response.body.to_map() or {}
                cr_map = body_map.get("ChunkResult") or body_map.get("chunk_result") or {}
                chunk_file_url = cr_map.get("ChunkFileUrl") or cr_map.get("chunk_file_url")
                plain_chunk_file_url = cr_map.get("PlainChunkFileUrl") or cr_map.get("plain_chunk_file_url")
                document_loader_result_file_url = cr_map.get("DocumentLoaderResultFileUrl") or cr_map.get("document_loader_result_file_url")
                logger.info(f"[GetJobChunks] chunk_file_url={chunk_file_url}, plain={plain_chunk_file_url}")
            except Exception as map_err:
                logger.warning(f"[GetJobChunks] to_map() 失败: {map_err}")

            chunk_result_info["chunk_file_url"] = chunk_file_url
            chunk_result_info["plain_chunk_file_url"] = plain_chunk_file_url
            chunk_result_info["document_loader_result_file_url"] = document_loader_result_file_url

            if not chunk_file_url:
                logger.warning(f"[GetJobChunks] 任务没有 chunk_result 或 URL 为空")

            if chunk_file_url:
                # 从 ChunkFileUrl 下载切片
                logger.info(f"[GetJobChunks] 从 ChunkFileUrl 下载切片: {chunk_file_url}")
                try:
                    with urlopen(chunk_file_url, timeout=30) as resp:
                        payload = resp.read().decode('utf-8', errors='ignore')
                        logger.info(f"[GetJobChunks] 下载成功，数据大小: {len(payload)} bytes")

                    # 兼容 JSON 数组 / JSONL 格式
                    parsed_chunks: List[Dict[str, Any]] = []
                    text = payload.strip()
                    if text:
                        if text.startswith('['):
                            data = json.loads(text)
                            if isinstance(data, list):
                                parsed_chunks = data
                        else:
                            for line in text.splitlines():
                                line = line.strip()
                                if not line:
                                    continue
                                try:
                                    parsed_chunks.append(json.loads(line))
                                except Exception as line_error:
                                    logger.warning(f"[GetJobChunks] 解析行失败: {line_error}")

                    logger.info(f"[GetJobChunks] 解析到 {len(parsed_chunks)} 个切片")
                    for item in parsed_chunks:
                        chunks.append({
                            "content": item.get("page_content") or item.get("content", ""),
                            "metadata": item.get("metadata", {}),
                            "id": item.get("id")
                        })
                except Exception as download_error:
                    logger.error(f"[GetJobChunks] 下载/解析 ChunkFileUrl 失败: {str(download_error)}", exc_info=True)
                    raise parse_sdk_exception(download_error, "下载切片文件失败: ")
            
            logger.info(f"[GetJobChunks] 最终获取到 {len(chunks)} 个切片")
            
            return {
                "chunks": chunks,
                "total": len(chunks),
                "chunk_result_info": chunk_result_info
            }
            
        except Exception as e:
            logger.error(f"[GetJobChunks] 获取切分结果失败: {str(e)}", exc_info=True)
            raise parse_sdk_exception(e, "获取切分结果失败: ")
    
    def get_chunk_file_url(self, job_id: str) -> str:
        """
        获取 job 的 ChunkFileUrl（直接调用 SDK，确保拿到最新 URL）

        Args:
            job_id: 任务ID

        Returns:
            ChunkFileUrl 字符串

        Raises:
            Exception: job 未完成或 URL 不可用时抛出
        """
        request = gpdb_20160503_models.GetUploadDocumentJobRequest(
            region_id=self.vector_service.region_id,
            dbinstance_id=self.vector_service.instance_id,
            namespace=self.namespace,
            namespace_password=self.namespace_password,
            collection=self.collection,
            job_id=job_id,
        )
        client = self.vector_service.get_client()
        response = client.get_upload_document_job(request)
        body = response.body

        # 优先用 SDK 属性取，取不到再降级 to_map()
        chunk_file_url = None
        cr = getattr(body, "chunk_result", None)
        if cr is not None:
            chunk_file_url = getattr(cr, "chunk_file_url", None)

        if not chunk_file_url:
            try:
                body_map = body.to_map() or {}
                cr_map = body_map.get("ChunkResult") or body_map.get("chunk_result") or {}
                chunk_file_url = cr_map.get("ChunkFileUrl") or cr_map.get("chunk_file_url")
            except Exception as e:
                logger.warning(f"[GetChunkFileUrl] to_map() 失败: {e}")

        if not chunk_file_url:
            raise Exception(f"ChunkFileUrl 不可用，job 未完成或请重新上传文件 (job_id={job_id})")

        return chunk_file_url

    def upsert_chunks(
        self,
        file_name: str,
        chunks: List[Dict[str, Any]],
        should_replace_file: bool = True,
        allow_insert_with_filter: bool = True
    ) -> Dict[str, Any]:
        """
        直接上传切片到 ADB（使用 UpsertChunks）
        
        Args:
            file_name: 文件名
            chunks: 切片列表，每个切片包含 content, metadata, id(可选), filter(可选)
            should_replace_file: 是否覆盖同名文件
            allow_insert_with_filter: 是否允许在指定Filter时插入数据
            
        Returns:
            上传结果
        """
        try:
            logger.info(f"[UpsertChunks] 开始上传切片: {file_name}, 共 {len(chunks)} 个")
            
            # 构建 TextChunks
            text_chunks = []
            for chunk in chunks:
                chunk_obj = gpdb_20160503_models.UpsertChunksRequestTextChunks()
                chunk_obj.content = chunk.get("content", "")
                
                # 处理 metadata
                if "metadata" in chunk and chunk["metadata"]:
                    chunk_obj.metadata = chunk["metadata"]
                
                # 处理可选字段
                if "id" in chunk:
                    chunk_obj.id = chunk["id"]
                if "filter" in chunk:
                    chunk_obj.filter = chunk["filter"]
                
                text_chunks.append(chunk_obj)
            
            # 构建请求
            request = gpdb_20160503_models.UpsertChunksRequest(
                region_id=self.vector_service.region_id,
                dbinstance_id=self.vector_service.instance_id,
                namespace=self.namespace,
                namespace_password=self.namespace_password,
                collection=self.collection,
                file_name=file_name,
                text_chunks=text_chunks,
                should_replace_file=should_replace_file,
                allow_insert_with_filter=allow_insert_with_filter
            )
            
            # 设置超时
            client = self.vector_service.get_client()
            response = client.upsert_chunks(request)
            
            logger.info(f"[UpsertChunks] 上传成功")
            
            return {
                "status": response.body.status if hasattr(response.body, 'status') else "success",
                "message": response.body.message if hasattr(response.body, 'message') else "上传成功",
                "request_id": response.body.request_id if hasattr(response.body, 'request_id') else None,
                "embedding_tokens": response.body.embedding_tokens if hasattr(response.body, 'embedding_tokens') else None
            }
            
        except Exception as e:
            logger.error(f"[UpsertChunks] 上传切片失败: {str(e)}")
            raise parse_sdk_exception(e, "上传切片失败: ")


# 全局服务实例
adb_document_service = None


def get_adb_document_service() -> ADBDocumentService:
    """获取ADB文档服务实例（单例模式）"""
    global adb_document_service
    if adb_document_service is None:
        try:
            adb_document_service = ADBDocumentService()
        except Exception as e:
            logger.error(f"初始化ADB文档服务失败: {str(e)}")
            raise e
    return adb_document_service
