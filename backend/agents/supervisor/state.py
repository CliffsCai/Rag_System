# -*- coding: utf-8 -*-
"""
Supervisor Agent State Definition
State management for multi-agent coordination with conversation memory
"""

from typing_extensions import TypedDict
from typing import Annotated
from langgraph.graph import add_messages
from langchain_core.messages import BaseMessage


class SupervisorState(TypedDict):
    """
    Supervisor Agent State
    
    Manages conversation history and coordinates specialized sub-agents:
    - Email Agent: Handles email operations
    - Search Agent: Handles web search and information retrieval
    
    Attributes:
        messages: Conversation message list, automatically merged using add_messages reducer
    """
    messages: Annotated[list[BaseMessage], add_messages]