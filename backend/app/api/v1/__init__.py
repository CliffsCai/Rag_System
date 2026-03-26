# -*- coding: utf-8 -*-
"""
API v1 Package
Version 1 API endpoints
"""

from fastapi import APIRouter
from .chat import router as chat_router
from .knowledge import router as knowledge_router
from .system import router as system_router
from .documents import router as documents_router
from .admin import router as admin_router
from .jobs import router as jobs_router
from .categories import router as categories_router
from .chunks import router as chunks_router
from .files import router as files_router

# Create main v1 router
router = APIRouter(prefix="/v1")

# Include sub-routers
router.include_router(chat_router, prefix="/chat", tags=["chat"])
router.include_router(knowledge_router, prefix="/knowledge", tags=["knowledge"])
router.include_router(documents_router, tags=["documents"])
router.include_router(jobs_router, tags=["jobs"])
router.include_router(categories_router, tags=["categories"])
router.include_router(chunks_router, tags=["chunks"])
router.include_router(files_router, tags=["files"])
router.include_router(admin_router, tags=["admin"])
router.include_router(system_router, tags=["system"])