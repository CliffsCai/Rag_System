# -*- coding: utf-8 -*-
"""
Search Service
Web search and information retrieval tools
"""

from langchain_core.tools import tool


@tool
def search_web(query: str, max_results: int = 5) -> str:
    """
    Search the web for information
    
    Args:
        query: Search query string
        max_results: Maximum number of results to return
        
    Returns:
        Search results
    """
    print(f"[Search Agent] Searching for: {query}")
    
    return f"Found {max_results} results for: {query}\n1. Result 1...\n2. Result 2..."


@tool
def get_weather(city: str, unit: str = "celsius") -> str:
    """
    Get weather information for a city
    
    Args:
        city: City name
        unit: Temperature unit (celsius or fahrenheit)
        
    Returns:
        Weather information
    """
    print(f"[Search Agent] Getting weather for: {city}")
    
    return f"Weather in {city}: 25°{unit[0].upper()}, Sunny, Humidity: 60%"


@tool
def get_news(topic: str, limit: int = 5) -> str:
    """
    Get latest news about a topic
    
    Args:
        topic: News topic
        limit: Number of news items
        
    Returns:
        News results
    """
    print(f"[Search Agent] Getting news about: {topic}")
    
    return f"Latest {limit} news about {topic}:\n1. News 1...\n2. News 2..."


def get_search_tools():
    """
    Get list of search tools
    
    Returns:
        List of search tool functions
    """
    return [search_web, get_weather, get_news]


# Agent metadata for supervisor
SEARCH_AGENT_INFO = {
    "name": "search_agent",
    "display_name": "搜索智能体",
    "description": "专门处理网络搜索、天气查询、新闻获取等信息检索任务",
    "capabilities": [
        "网络搜索",
        "天气查询",
        "新闻获取",
        "实时信息检索"
    ],
    "keywords": ["搜索", "search", "查询", "天气", "新闻", "信息", "weather", "news"]
}