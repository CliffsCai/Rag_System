# -*- coding: utf-8 -*-
"""
FastAPI Application
Main application factory and configuration
"""

import ssl
import urllib3
import requests

# 本地开发环境：全局禁用 SSL 证书验证
ssl._create_default_https_context = ssl._create_unverified_context
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
requests.packages.urllib3.disable_warnings()
_original_request = requests.Session.request
def _patched_request(self, method, url, **kwargs):
    kwargs.setdefault("verify", False)
    return _original_request(self, method, url, **kwargs)
requests.Session.request = _patched_request

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.logging import setup_logging
from app.core.config import settings
from app.core.exceptions import AppError
from app.api.v1 import router as v1_router
from app.services.adb_vector_service import ADBException

# 初始化结构化日志（最早执行）
setup_logging(level="DEBUG" if settings.api_reload else "INFO")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("应用启动中")
    yield
    # 应用关闭时清理 ADB SQL Secret，避免长期积累
    _cleanup_sql_secret()
    logger.info("应用已关闭")


def _cleanup_sql_secret() -> None:
    """删除本次应用运行期间使用的 ADB SQL Secret"""
    try:
        from app.db.base_repository import BaseRepository
        from app.services.adb_vector_service import get_adb_vector_service
        from app.core.config import settings

        if settings.adb_sql_secret_arn and settings.adb_sql_secret_arn.startswith("acs:"):
            # 手动指定的真实 ARN，不自动删除
            return

        secret_name = BaseRepository._normalize_secret_name(
            settings.adb_sql_secret_name or f"kbsec-{settings.bailian_adb_user}"
        )
        vs = get_adb_vector_service()
        arn = vs.find_secret_arn_by_name(secret_name)
        if arn:
            result = vs.delete_secret(arn)
            if result.get("success"):
                logger.info("ADB SQL Secret 已清理", extra={"secret_name": secret_name})
            else:
                logger.warning("ADB SQL Secret 清理失败", extra={"error": result.get("error")})
    except Exception as e:
        logger.warning("ADB SQL Secret 清理异常（不影响关闭）", extra={"error": str(e)})


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.api_title,
        version=settings.api_version,
        description="Professional LangGraph-based RAG system for enterprise knowledge base Q&A",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(v1_router, prefix="/api")

    # ── 全局异常 handler ──────────────────────────────────────────────────────

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        logger.warning(
            "业务异常",
            extra={"path": request.url.path, "error": exc.message},
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.message},
        )

    @app.exception_handler(ADBException)
    async def adb_exception_handler(request: Request, exc: ADBException):
        logger.error("ADB 异常", extra={"error": str(exc)})
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": str(exc)},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception("未处理异常", extra={"path": request.url.path})
        return JSONResponse(
            status_code=500,
            content={"detail": "服务器内部错误，请稍后重试"},
        )

    return app


app = create_app()
