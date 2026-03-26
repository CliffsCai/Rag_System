# -*- coding: utf-8 -*-
"""
Email Agent Package
Specialized agent for email operations
"""

from .graph import create_email_agent
from .services.email_service import EMAIL_AGENT_INFO

__all__ = ["create_email_agent", "EMAIL_AGENT_INFO"]