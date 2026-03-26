# -*- coding: utf-8 -*-
"""
Search Agent Graph Definition
Specialized agent for web search and information retrieval
"""

from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode
from langchain_core.messages import AIMessage

from .state import SearchAgentState
from .services.search_service import get_search_tools


def create_search_agent(model):
    """
    Create Search Agent
    
    Args:
        model: LLM model instance
        
    Returns:
        Compiled search agent graph
    """
    print("\n[Graph] Building Search Agent")
    
    # Get search tools
    search_tools = get_search_tools()
    
    # Bind tools to model
    model_with_tools = model.bind_tools(search_tools)
    
    # Define nodes
    def call_model(state: SearchAgentState):
        """Call model with search tools"""
        response = model_with_tools.invoke(state["messages"])
        return {"messages": [response]}
    
    def should_continue(state: SearchAgentState):
        """Decide whether to continue to tools or end"""
        last_message = state["messages"][-1]
        if isinstance(last_message, AIMessage) and last_message.tool_calls:
            return "tools"
        return "__end__"
    
    # Build graph
    builder = StateGraph(SearchAgentState)
    builder.add_node("agent", call_model)
    builder.add_node("tools", ToolNode(search_tools))
    
    builder.add_edge(START, "agent")
    builder.add_conditional_edges(
        "agent",
        should_continue,
        {"tools": "tools", "__end__": END}
    )
    builder.add_edge("tools", "agent")
    
    graph = builder.compile()
    
    print("[Graph] Search Agent created successfully")
    
    return graph