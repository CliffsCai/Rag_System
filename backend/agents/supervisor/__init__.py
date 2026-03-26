# -*- coding: utf-8 -*-
from .graph import create_supervisor_agent

_agent = None


def get_supervisor_agent():
    """获取 Supervisor Agent 实例（延迟初始化，模块级缓存）"""
    global _agent
    if _agent is None:
        _agent = create_supervisor_agent()
    return _agent


__all__ = ["get_supervisor_agent", "create_supervisor_agent"]
