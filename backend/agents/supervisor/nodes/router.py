# -*- coding: utf-8 -*-
"""
Supervisor Router Node
Conditional routing logic for supervisor agent
"""

from typing import Literal
from langchain_core.messages import AIMessage
from ..state import SupervisorState


def should_continue(state: SupervisorState) -> Literal["tools", "__end__"]:
    """
    Conditional edge function: decide whether to continue to tools or end
    
    Args:
        state: Current supervisor state
        
    Returns:
        Next node name: "tools" or "__end__"
    """
    messages = state["messages"]
    last_message = messages[-1]
    
    # If last message has tool calls, continue to tool node
    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        return "tools"
    
    # Otherwise end
    return "__end__"