# -*- coding: utf-8 -*-
"""
Email Agent Graph Definition
Specialized agent for email operations
"""

from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode

from .state import EmailAgentState
from .nodes import call_email_model, should_continue
from .services.email_service import get_email_tools


def create_email_agent(model):
    """
    Create Email Agent
    
    Args:
        model: LLM model instance
        
    Returns:
        Compiled email agent graph
    """
    print("\n[Graph] Building Email Agent")
    
    # Get email tools
    email_tools = get_email_tools()
    
    # Define model caller
    def model_caller(state: EmailAgentState):
        return call_email_model(state, model)
    
    # Build graph
    builder = StateGraph(EmailAgentState)
    builder.add_node("agent", model_caller)
    builder.add_node("tools", ToolNode(email_tools))
    
    builder.add_edge(START, "agent")
    builder.add_conditional_edges(
        "agent",
        should_continue,
        {"tools": "tools", "__end__": END}
    )
    builder.add_edge("tools", "agent")
    
    graph = builder.compile()
    
    print("[Graph] Email Agent created successfully")
    
    return graph