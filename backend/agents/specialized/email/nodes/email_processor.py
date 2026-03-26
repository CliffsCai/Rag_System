# -*- coding: utf-8 -*-
"""
Email Processor Node
Main email processing logic
"""

from langchain_core.messages import AIMessage
from ..state import EmailAgentState
from ..services.email_service import get_email_tools


def call_email_model(state: EmailAgentState, model):
    """
    Call email model with email tools
    
    Args:
        state: Current email agent state
        model: LLM model instance
        
    Returns:
        State update with new messages
    """
    # Get email tools
    email_tools = get_email_tools()
    
    # Bind tools to model
    model_with_tools = model.bind_tools(email_tools)
    
    # Invoke model
    response = model_with_tools.invoke(state["messages"])
    
    return {"messages": [response]}


def should_continue(state: EmailAgentState):
    """
    Decide whether to continue to tools or end
    
    Args:
        state: Current email agent state
        
    Returns:
        Next node name
    """
    last_message = state["messages"][-1]
    
    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        return "tools"
    
    return "__end__"