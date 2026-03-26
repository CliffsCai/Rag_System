# -*- coding: utf-8 -*-
"""
Search Agent State Definition
"""

from typing_extensions import TypedDict
from typing import Annotated, List
from langgraph.graph import add_messages
from langchain_core.messages import BaseMessage


class SearchAgentState(TypedDict):
    """Search agent state"""
    messages: Annotated[List[BaseMessage], add_messages]
