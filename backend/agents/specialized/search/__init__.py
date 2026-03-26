# -*- coding: utf-8 -*-
"""
Search Agent Package
Specialized agent for web search and information retrieval
"""

from .graph import create_search_agent
from .services.search_service import SEARCH_AGENT_INFO

__all__ = ["create_search_agent", "SEARCH_AGENT_INFO"]