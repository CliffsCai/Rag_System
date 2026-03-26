# -*- coding: utf-8 -*-
"""
Application Configuration
Centralized configuration management
"""

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ── 必填环境变量清单 ──────────────────────────────────────────────────────────
def _validate_env() -> None:
    """
    启动时校验必填配置，缺失则直接报错，避免运行时才发现。
    OSS AK 支持两种变量名（OSS_ACCESS_KEY_ID 或 ALIBABA_CLOUD_ACCESS_KEY_ID），任一存在即可。
    """
    missing = []

    # 单一必填项
    for key in ["DASHSCOPE_API_KEY", "ADBPG_INSTANCE_ID", "BAILIAN_ADB_USER", "BAILIAN_ADB_PASSWORD", "OSS_BUCKET"]:
        if not os.getenv(key):
            missing.append(key)

    # OSS AK 支持两种变量名，任一存在即可
    if not os.getenv("OSS_ACCESS_KEY_ID") and not os.getenv("ALIBABA_CLOUD_ACCESS_KEY_ID"):
        missing.append("OSS_ACCESS_KEY_ID 或 ALIBABA_CLOUD_ACCESS_KEY_ID")
    if not os.getenv("OSS_ACCESS_KEY_SECRET") and not os.getenv("ALIBABA_CLOUD_ACCESS_KEY_SECRET"):
        missing.append("OSS_ACCESS_KEY_SECRET 或 ALIBABA_CLOUD_ACCESS_KEY_SECRET")

    if missing:
        raise EnvironmentError(
            f"缺少必要的环境变量，请检查 .env 文件: {', '.join(missing)}"
        )


class Settings:
    """Application settings"""
    
    # ==================== LLM 配置 ====================
    # API Keys
    dashscope_api_key: str = os.getenv("DASHSCOPE_API_KEY", "")
    dashscope_api_secret: str = os.getenv("DASHSCOPE_API_SECRET", "")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    
    # Model Configuration
    default_model: str = os.getenv("LLM_MODEL", "qwen-turbo")
    temperature: float = 0.0
    max_tokens: int = 2000
    timeout: int = 60
    max_retries: int = 2
    
    # DashScope Configuration
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    
    # ==================== 知识库配置 ====================
    # 阿里云百炼 ADB 向量数据库
    bailian_adb_enabled: bool = os.getenv("BAILIAN_ADB_ENABLED", "false").lower() == "true"
    bailian_adb_host: str = os.getenv("BAILIAN_ADB_HOST", "")
    bailian_adb_port: int = int(os.getenv("BAILIAN_ADB_PORT", "5432"))
    bailian_adb_database: str = os.getenv("BAILIAN_ADB_DATABASE", "")
    bailian_adb_user: str = os.getenv("BAILIAN_ADB_USER", "")
    bailian_adb_password: str = os.getenv("BAILIAN_ADB_PASSWORD", "")
    bailian_adb_table: str = os.getenv("BAILIAN_ADB_TABLE", "knowledge_chunks")
    
    # ADB 实例配置（用于API管理）
    adbpg_instance_id: str = os.getenv("ADBPG_INSTANCE_ID", "")
    adbpg_instance_region: str = os.getenv("ADBPG_INSTANCE_REGION", "cn-shanghai")
    
    # ADB 向量数据库配置
    adb_namespace: str = os.getenv("ADB_NAMESPACE", "knowledge_ns")
    adb_namespace_password: str = os.getenv("ADB_NAMESPACE_PASSWORD", "")
    adb_collection: str = os.getenv("ADB_COLLECTION", "test_api_collection")
    adb_embedding_model: str = os.getenv("ADB_EMBEDDING_MODEL", "text-embedding-v3")

    # ADB SQL 配置（ExecuteStatement）
    adb_sql_secret_arn: str = os.getenv("ADB_SQL_SECRET_ARN", "")
    adb_sql_secret_name: str = os.getenv("ADB_SQL_SECRET_NAME", "jobsqlsec")
    adb_sql_database: str = os.getenv("ADB_SQL_DATABASE", "")
    adb_job_table: str = os.getenv("ADB_JOB_TABLE", "knowledge_job")
    
    # 向量检索配置
    vector_dimension: int = int(os.getenv("VECTOR_DIMENSION", "1536"))
    vector_top_k: int = int(os.getenv("VECTOR_TOP_K", "10"))
    vector_score_threshold: float = float(os.getenv("VECTOR_SCORE_THRESHOLD", "0"))
    
    # 文档上传配置
    adb_document_loader_pdf: str = os.getenv("ADB_DOCUMENT_LOADER_PDF", "RapidOCRPDFLoader")
    adb_text_splitter: str = os.getenv("ADB_TEXT_SPLITTER", "ChineseRecursiveTextSplitter")

    # 切片清洗配置
    llm_clean_model: str = os.getenv("LLM_CLEAN_MODEL", "qwen-turbo")
    
    # ==================== 业务数据库配置 ====================
    # 用于 MCP 工具的 query_database
    business_db_enabled: bool = os.getenv("BUSINESS_DB_ENABLED", "false").lower() == "true"
    business_db_type: str = os.getenv("BUSINESS_DB_TYPE", "postgresql")
    business_db_host: str = os.getenv("BUSINESS_DB_HOST", "")
    business_db_port: int = int(os.getenv("BUSINESS_DB_PORT", "5432"))
    business_db_database: str = os.getenv("BUSINESS_DB_DATABASE", "")
    business_db_user: str = os.getenv("BUSINESS_DB_USER", "")
    business_db_password: str = os.getenv("BUSINESS_DB_PASSWORD", "")
    
    # ==================== 邮件服务配置 ====================
    # 用于 send_email 工具
    email_enabled: bool = os.getenv("EMAIL_ENABLED", "false").lower() == "true"
    smtp_host: str = os.getenv("SMTP_HOST", "")
    smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
    smtp_user: str = os.getenv("SMTP_USER", "")
    smtp_password: str = os.getenv("SMTP_PASSWORD", "")
    smtp_use_tls: bool = os.getenv("SMTP_USE_TLS", "true").lower() == "true"
    
    # ==================== 网络搜索配置 ====================
    # 用于 web_search 工具
    web_search_enabled: bool = os.getenv("WEB_SEARCH_ENABLED", "false").lower() == "true"
    web_search_api_key: str = os.getenv("WEB_SEARCH_API_KEY", "")
    web_search_engine: str = os.getenv("WEB_SEARCH_ENGINE", "google")
    
    # ==================== API Server 配置 ====================
    api_host: str = os.getenv("API_HOST", "0.0.0.0")
    api_port: int = int(os.getenv("API_PORT", "8000"))
    api_reload: bool = os.getenv("API_RELOAD", "false").lower() == "true"
    api_title: str = "Knowledge Agent API"
    api_version: str = "1.0.0"

    # ==================== OSS 配置 ====================
    oss_access_key_id: str = os.getenv("OSS_ACCESS_KEY_ID", os.getenv("ALIBABA_CLOUD_ACCESS_KEY_ID", ""))
    oss_access_key_secret: str = os.getenv("OSS_ACCESS_KEY_SECRET", os.getenv("ALIBABA_CLOUD_ACCESS_KEY_SECRET", ""))
    oss_region: str = os.getenv("OSS_REGION", "cn-shanghai")
    oss_endpoint: str = os.getenv("OSS_ENDPOINT", "https://oss-cn-shanghai.aliyuncs.com")
    oss_bucket: str = os.getenv("OSS_BUCKET", "xiaofei-adb")

    # Graph preload switch
    preload_graphs: bool = os.getenv("PRELOAD_GRAPHS", "false").lower() == "true"

    # 多租户命名空间密码加密密钥（32字节hex）
    namespace_encrypt_key: str = os.getenv("NAMESPACE_ENCRYPT_KEY", "")
    
    # CORS Configuration
    cors_origins: list = ["*"]
    
    # SSL Configuration
    ssl_verify: bool = os.getenv("SSL_VERIFY", "false").lower() == "true"
    
    # LangSmith Configuration
    langsmith_tracing: bool = os.getenv("LANGSMITH_TRACING", "false").lower() == "true"

    def __init__(self):
        _validate_env()


# Global settings instance
settings = Settings()


# Model configurations
SUPPORTED_MODELS = {
    "qwen-turbo": {
        "name": "qwen-turbo",
        "description": "快速响应，适合简单任务",
        "provider": "dashscope",
        "max_tokens": 8000,
        "cost_per_1k_tokens": 0.001,
    },
    "qwen-plus": {
        "name": "qwen-plus",
        "description": "平衡性能和成本",
        "provider": "dashscope",
        "max_tokens": 32000,
        "cost_per_1k_tokens": 0.002,
    },
    "qwen-max": {
        "name": "qwen-max",
        "description": "最强性能，适合复杂任务",
        "provider": "dashscope",
        "max_tokens": 8000,
        "cost_per_1k_tokens": 0.004,
    },
    "qwen-long": {
        "name": "qwen-long",
        "description": "支持长文本（最大2M tokens）",
        "provider": "dashscope",
        "max_tokens": 2000000,
        "cost_per_1k_tokens": 0.001,
    },
    "qwen-vl-plus": {
        "name": "qwen-vl-plus",
        "description": "视觉理解模型",
        "provider": "dashscope",
        "max_tokens": 8000
    },
    "qwen-coder-plus": {
        "name": "qwen-coder-plus", 
        "description": "代码生成专用",
        "provider": "dashscope",
        "max_tokens": 8000
    },
    "qwen-math-plus": {
        "name": "qwen-math-plus",
        "description": "数学推理专用", 
        "provider": "dashscope",
        "max_tokens": 4000
    }
}


# API Endpoints
class APIEndpoints:
    """API endpoint constants"""
    
    # DashScope
    DASHSCOPE_CHAT = f"{settings.dashscope_base_url}/chat/completions"
    
    # Health checks
    HEALTH = "/health"
    ROOT = "/"
    
    # Agent endpoints
    CHAT = "/chat"
    KNOWLEDGE = "/knowledge"
    MODELS = "/models"


# Error messages
class ErrorMessages:
    """Error message constants"""
    
    API_KEY_MISSING = "API key not configured"
    MODEL_NOT_SUPPORTED = "Model not supported"
    CONNECTION_ERROR = "Connection error occurred"
    TIMEOUT_ERROR = "Request timeout"
    INVALID_REQUEST = "Invalid request format"
    INTERNAL_ERROR = "Internal server error"


# Success messages  
class SuccessMessages:
    """Success message constants"""
    
    API_READY = "Agent API is running"
    CHAT_SUCCESS = "Chat completed successfully"
    KNOWLEDGE_SUCCESS = "Knowledge query completed successfully"