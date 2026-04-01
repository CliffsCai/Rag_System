# -*- coding: utf-8 -*-
from fastapi import APIRouter
from .chat import router as chat_router
from .knowledge import router as knowledge_router
from .system import router as system_router
from .documents import router as documents_router
from .admin import admin_router
from .jobs import router as jobs_router
from .categories import router as categories_router
from .chunks import router as chunks_router
from .files import router as files_router
from .conversations import router as conversations_router

router = APIRouter(prefix="/v1")

router.include_router(chat_router)
router.include_router(knowledge_router)
router.include_router(documents_router)
router.include_router(jobs_router)
router.include_router(categories_router)
router.include_router(chunks_router)
router.include_router(files_router)
router.include_router(conversations_router)
router.include_router(admin_router)
router.include_router(system_router)
