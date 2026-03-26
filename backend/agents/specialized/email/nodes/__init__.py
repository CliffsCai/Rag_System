# -*- coding: utf-8 -*-
"""
Email Agent Nodes Package
Processing nodes for email agent workflow
"""

from .email_processor import call_email_model, should_continue

__all__ = [
    "call_email_model",
    "should_continue"
]