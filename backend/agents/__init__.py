# -*- coding: utf-8 -*-
"""
Agents Package
Multi-agent system with supervisor and specialized agents
"""

from .supervisor import get_supervisor_agent
from .knowledge import get_knowledge_agent

__all__ = ["get_supervisor_agent", "get_knowledge_agent"]
