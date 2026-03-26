# -*- coding: utf-8 -*-
"""
Email Agent State Definition
State management for email operations
"""

from typing_extensions import TypedDict
from typing import Annotated, List
from langgraph.graph import add_messages
from langchain_core.messages import BaseMessage


class EmailAgentState(TypedDict):
    """
    Email Agent State
    
    Manages conversation and email operation context
    
    Attributes:
        messages: Conversation message list, automatically merged using add_messages reducer
    """
    messages: Annotated[List[BaseMessage], add_messages]