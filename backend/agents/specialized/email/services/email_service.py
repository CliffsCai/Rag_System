# -*- coding: utf-8 -*-
"""
Email Service
Email operations and tools
"""

from langchain_core.tools import tool


@tool
def send_email(to: str, subject: str, body: str) -> str:
    """
    Send an email
    
    Args:
        to: Recipient email address
        subject: Email subject
        body: Email body content
        
    Returns:
        Confirmation message
    """
    print(f"[Email Agent] Sending email to: {to}")
    print(f"[Email Agent] Subject: {subject}")
    
    return f"Email sent successfully to {to}"


@tool
def check_inbox(folder: str = "inbox", limit: int = 10) -> str:
    """
    Check email inbox
    
    Args:
        folder: Email folder to check (inbox, sent, drafts)
        limit: Maximum number of emails to retrieve
        
    Returns:
        List of emails
    """
    print(f"[Email Agent] Checking {folder}, limit: {limit}")
    
    return f"Found 3 emails in {folder}:\n1. Email 1...\n2. Email 2...\n3. Email 3..."


@tool
def search_emails(query: str, limit: int = 10) -> str:
    """
    Search emails by keyword
    
    Args:
        query: Search query
        limit: Maximum number of results
        
    Returns:
        Search results
    """
    print(f"[Email Agent] Searching emails for: {query}")
    
    return f"Found 2 emails matching '{query}':\n1. Email 1...\n2. Email 2..."


def get_email_tools():
    """
    Get list of email tools
    
    Returns:
        List of email tool functions
    """
    return [send_email, check_inbox, search_emails]


# Agent metadata for supervisor
EMAIL_AGENT_INFO = {
    "name": "email_agent",
    "display_name": "邮件智能体",
    "description": "专门处理邮件发送、查收、搜索等邮件相关任务",
    "capabilities": [
        "发送邮件",
        "查收邮件",
        "搜索邮件",
        "管理邮箱"
    ],
    "keywords": ["邮件", "email", "发送", "查收", "inbox", "send"]
}