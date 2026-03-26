# -*- coding: utf-8 -*-
"""
System API Routes
Health checks, model information, and system status
"""

from fastapi import APIRouter
from app.core.config import settings, SUPPORTED_MODELS, SuccessMessages
from app.models.responses import ModelsResponse, ModelInfo, HealthResponse

router = APIRouter()


@router.get("/", summary="Root endpoint")
async def root():
    """Root endpoint with system information"""
    return {
        "status": "ok",
        "message": SuccessMessages.API_READY,
        "version": settings.api_version,
        "architecture": "Solution 3: Complete Knowledge Agent with Full Workflow",
        "workflow": "query_analysis → retrieve → filter → rerank → generate → quality_check → metrics",
        "models": list(SUPPORTED_MODELS.keys()),
        "default_model": settings.default_model,
        "mcp_tools": ["send_email", "web_search", "query_database"],
        "note": "Using MOCK retrieval - ready for real KB integration"
    }


@router.get("/models", response_model=ModelsResponse, summary="Get available models")
async def get_models():
    """Get list of available LLM models"""
    models = [
        ModelInfo(
            name=name,
            description=info["description"],
            provider=info["provider"],
            max_tokens=info["max_tokens"]
        )
        for name, info in SUPPORTED_MODELS.items()
    ]
    
    return ModelsResponse(
        models=models,
        default_model=settings.default_model
    )


@router.get("/health", response_model=HealthResponse, summary="Health check")
async def health():
    """Health check endpoint"""
    return HealthResponse(
        status="healthy",
        api_key_configured=bool(settings.dashscope_api_key),
        default_model=settings.default_model,
        ssl_verify=settings.ssl_verify
    )