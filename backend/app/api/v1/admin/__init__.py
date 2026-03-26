# -*- coding: utf-8 -*-
from fastapi import APIRouter
from .namespace import router as namespace_router
from .collection import router as collection_router
from .config import router as config_router

router = APIRouter(prefix="/admin", tags=["admin"])
router.include_router(config_router)
router.include_router(namespace_router)
router.include_router(collection_router)
