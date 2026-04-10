# -*- coding: utf-8 -*-
"""
FastAPI Application
"""
import ssl
import urllib3
import requests

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

setup_logging(level="DEBUG" if settings.api_reload else "INFO")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("应用启动中，初始化数据库表...")
    from app.db.init_db import init_db
    init_db()
    logger.info("初始化 LangGraph checkpointer...")
    from app.core.checkpointer import init_checkpointer
    await init_checkpointer()
    logger.info("应用启动完成")
    yield
    from app.core.checkpointer import close_checkpointer
    await close_checkpointer()
    logger.info("应用已关闭")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.api_title,
        version=settings.api_version,
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

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        logger.warning("业务异常", extra={"path": request.url.path, "error": exc.message})
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception("未处理异常", extra={"path": exc.message})
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})

    return app


app = create_app()
