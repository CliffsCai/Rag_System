# -*- coding: utf-8 -*-
"""
Supervisor Agent Graph Definition
Multi-agent coordinator with conversation memory
"""

import ssl
import httpx
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import ToolNode
from langchain_openai import ChatOpenAI

from .state import SupervisorState
from .nodes import should_continue
from .services.coordinator import create_supervisor_tools, get_supervisor_system_prompt
from app.core.config import settings, SUPPORTED_MODELS


def create_supervisor_agent():
    """
    Create and compile Supervisor Agent with Multi-Agent System
    
    Architecture:
        Supervisor Agent (Main)
            ↓ calls as tools
        ├── Email Agent (Specialized)
        ├── Search Agent (Specialized)
        └── ... (More agents can be added)
    
    Workflow:
        START → supervisor → should_continue → tools or __end__
                                ↓               ↓
                            __end__         tools → supervisor
    
    Returns:
        Compiled LangGraph agent
    """
    print("\n[Graph] Building Supervisor Agent with multi-agent system")
    
    # Create a default model for tool creation (will be overridden at runtime)
    if not settings.ssl_verify:
        ssl._create_default_https_context = ssl._create_unverified_context
    
    http_client = httpx.Client(
        verify=settings.ssl_verify, 
        timeout=settings.timeout
    )
    
    default_model = ChatOpenAI(
        model=settings.default_model,
        temperature=settings.temperature,
        base_url=settings.dashscope_base_url,
        api_key=settings.dashscope_api_key,
        streaming=False,
        timeout=settings.timeout,
        max_retries=settings.max_retries,
        http_client=http_client
    )
    
    # Create supervisor tools
    supervisor_tools = create_supervisor_tools(default_model)
    tool_node = ToolNode(supervisor_tools)
    
    print(f"[Graph] Created {len(supervisor_tools)} supervisor tools")
    
    def call_supervisor_model(state: SupervisorState, config) -> dict:
        """
        Call Supervisor Agent with sub-agents as tools
        """
        from langchain_core.messages import SystemMessage
        
        # Get model from config
        model_name = config.get("configurable", {}).get("model", settings.default_model)
        
        # Validate model
        if model_name not in SUPPORTED_MODELS:
            raise ValueError(f"Model '{model_name}' not supported. Available models: {list(SUPPORTED_MODELS.keys())}")
        
        print(f"\n[Supervisor] Using model: {model_name}")
        
        try:
            # Create model for this request
            model = ChatOpenAI(
                model=model_name,
                temperature=config.get("configurable", {}).get("temperature", settings.temperature),
                base_url=settings.dashscope_base_url,
                api_key=settings.dashscope_api_key,
                streaming=False,
                timeout=settings.timeout,
                max_retries=settings.max_retries,
                http_client=http_client
            )
            
            # Bind tools to model
            model_with_tools = model.bind_tools(supervisor_tools)
            
            # Add system prompt if this is the first message
            messages = state["messages"]
            print(f"[Supervisor] Current conversation has {len(messages)} messages")
            for i, msg in enumerate(messages):
                print(f"[Supervisor] Message {i+1}: {msg.type} - {msg.content[:50]}...")
            
            if len(messages) == 1 or not any(isinstance(msg, SystemMessage) for msg in messages):
                system_prompt = get_supervisor_system_prompt()
                messages = [SystemMessage(content=system_prompt)] + messages
            
            print("[Supervisor] Analyzing user request...")
            
            # Invoke model
            response = model_with_tools.invoke(messages)
            
            print("[Supervisor] Decision made")
            
            return {"messages": [response]}
            
        except Exception as e:
            error_msg = str(e)
            print(f"[Supervisor] Error: {error_msg}")
            raise Exception(f"Supervisor agent failed: {error_msg}")
    
    # Create graph builder
    builder = StateGraph(SupervisorState)
    
    # Add nodes
    builder.add_node("supervisor", call_supervisor_model)
    builder.add_node("tools", tool_node)
    
    # Add edges
    builder.add_edge(START, "supervisor")
    builder.add_conditional_edges(
        "supervisor",
        should_continue,
        {
            "tools": "tools",
            "__end__": END
        }
    )
    builder.add_edge("tools", "supervisor")
    
    # Add memory checkpoint
    memory = MemorySaver()
    
    # Compile graph
    graph = builder.compile(checkpointer=memory)
    
    print("[Graph] Supervisor Agent created successfully")
    print("[Graph] Workflow: supervisor → should_continue → tools/end")
    
    return graph