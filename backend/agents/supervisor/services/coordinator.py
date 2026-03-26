# -*- coding: utf-8 -*-
"""
Supervisor Coordinator Service
Manages sub-agents and provides coordination logic
"""

from langchain_core.tools import tool
from langchain_core.messages import HumanMessage
from agents.specialized.email import create_email_agent, EMAIL_AGENT_INFO
from agents.specialized.search import create_search_agent, SEARCH_AGENT_INFO
from app.core.prompts import SUPERVISOR_SYSTEM_PROMPT


# Registry of available sub-agents
SUB_AGENTS_REGISTRY = {
    "email_agent": {
        "info": EMAIL_AGENT_INFO,
        "creator": create_email_agent
    },
    "search_agent": {
        "info": SEARCH_AGENT_INFO,
        "creator": create_search_agent
    }
}


def create_supervisor_tools(model):
    """
    Create tools that wrap sub-agents for the supervisor
    
    Args:
        model: LLM model instance to pass to sub-agents
        
    Returns:
        List of tool functions
    """
    tools = []
    
    # Create email agent tool
    email_agent = create_email_agent(model)
    
    @tool(
        EMAIL_AGENT_INFO["name"],
        description=EMAIL_AGENT_INFO["description"]
    )
    def call_email_agent(query: str) -> str:
        """
        Call the email agent to handle email-related tasks
        
        Args:
            query: The email-related task or question
            
        Returns:
            Result from email agent
        """
        print(f"\n[Supervisor] Delegating to Email Agent: {query}")
        
        result = email_agent.invoke({
            "messages": [HumanMessage(content=query)]
        })
        
        # Extract final response
        final_message = result["messages"][-1].content
        print(f"[Supervisor] Email Agent completed: {final_message[:100]}...")
        
        return final_message
    
    tools.append(call_email_agent)
    
    # Create search agent tool
    search_agent = create_search_agent(model)
    
    @tool(
        SEARCH_AGENT_INFO["name"],
        description=SEARCH_AGENT_INFO["description"]
    )
    def call_search_agent(query: str) -> str:
        """
        Call the search agent to handle search and information retrieval tasks
        
        Args:
            query: The search query or information request
            
        Returns:
            Result from search agent
        """
        print(f"\n[Supervisor] Delegating to Search Agent: {query}")
        
        result = search_agent.invoke({
            "messages": [HumanMessage(content=query)]
        })
        
        # Extract final response
        final_message = result["messages"][-1].content
        print(f"[Supervisor] Search Agent completed: {final_message[:100]}...")
        
        return final_message
    
    tools.append(call_search_agent)
    
    return tools


def format_agents_info() -> str:
    """
    Format sub-agents information for supervisor's system prompt
    
    Returns:
        Formatted string describing available agents
    """
    info = "Available Specialized Agents:\n\n"
    
    for agent_name, agent_data in SUB_AGENTS_REGISTRY.items():
        agent_info = agent_data["info"]
        info += f"**{agent_info['display_name']}** ({agent_info['name']})\n"
        info += f"  Description: {agent_info['description']}\n"
        info += f"  Capabilities:\n"
        for cap in agent_info['capabilities']:
            info += f"    - {cap}\n"
        info += f"  Keywords: {', '.join(agent_info['keywords'])}\n\n"
    
    return info


def get_supervisor_system_prompt() -> str:
    """
    Get system prompt for supervisor agent

    Returns:
        System prompt string
    """
    agents_info = format_agents_info()
    return SUPERVISOR_SYSTEM_PROMPT.format(agents_info=agents_info)