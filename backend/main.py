#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Knowledge Agent System - Main Entry Point

This is the main entry point for the Knowledge Agent API server.
Run this file to start the entire system.

Usage:
    python main.py

The server will start at http://localhost:8000
API documentation available at http://localhost:8000/docs
"""

import sys
import os

# Add backend to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.main import app
from app.core.config import settings, SUPPORTED_MODELS


def main():
    """
    Main entry point for the Knowledge Agent API server
    """
    import uvicorn
    
    # Print startup banner
    print("\n" + "=" * 70)
    print("  Knowledge Agent System - Starting")
    print("=" * 70)
    print(f"  Architecture: Refactored Multi-Agent System")
    print(f"  Chat Mode: Supervisor → Email/Search Agents")
    print(f"  Knowledge Mode: Complete RAG Workflow")
    print("=" * 70)
    print(f"  API Server: http://{settings.api_host}:{settings.api_port}")
    print(f"  API Docs:   http://{settings.api_host}:{settings.api_port}/docs")
    print(f"  Health:     http://{settings.api_host}:{settings.api_port}/api/v1/health")
    print("=" * 70)
    print(f"  Default Model: {settings.default_model}")
    print(f"  Available Models:")
    for model_name, model_info in SUPPORTED_MODELS.items():
        print(f"    - {model_name}: {model_info['description']}")
    print("=" * 70)
    print(f"  Specialized Agents: email_agent, search_agent")
    print(f"  Knowledge Base: MOCK mode (ready for integration)")
    print("=" * 70)
    print(f"  API Key Configured: {'✅ Yes' if settings.dashscope_api_key else '❌ No'}")
    print(f"  SSL Verify: {'✅ Enabled' if settings.ssl_verify else '⚠️  Disabled (dev mode)'}")
    print("=" * 70)
    print("\n  Press CTRL+C to stop the server\n")
    
    # Start the server
    try:
        uvicorn.run(
            "app.main:app",  # Use string reference for auto-reload
            host=settings.api_host,
            port=settings.api_port,
            reload=settings.api_reload,
            log_level="info"
        )
    except KeyboardInterrupt:
        print("\n\n" + "=" * 70)
        print("  Server stopped by user")
        print("=" * 70 + "\n")
    except Exception as e:
        print("\n\n" + "=" * 70)
        print(f"  ❌ Server failed to start: {str(e)}")
        print("=" * 70 + "\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
