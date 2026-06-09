"""
Morrisons AWS Cloud Agent – LangGraph Graph
============================================
LangGraph ReAct agent: agent node ↔ tools node.
Uses Gemini via GEMINILLM_URL and GEMINILLM_API_KEY env vars.
"""
from __future__ import annotations

import logging
from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage, SystemMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from tools import TOOLS

from config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an AWS Cloud specialist agent for Morrisons supermarkets (UK).

You manage cloud analytics, serverless workflows, data storage, notifications,
and session data using Amazon Web Services.

Key AWS services in use:
- S3: Report storage and data lake
- Lambda: Serverless reorder and pricing workflows
- DynamoDB: Customer session data
- SNS: Operational alerts and notifications
- Redshift/Athena: Sales trend analytics

Store IDs: STORE-001 (Bradford HQ), STORE-042 (Leeds), STORE-107 (Manchester)
"""


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------

class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


def build_graph():
    tools = TOOLS
    llm = settings.build_llm().bind_tools(tools)

    def agent_node(state: AgentState) -> AgentState:
        messages = [SystemMessage(content=SYSTEM_PROMPT)] + state["messages"]
        response = llm.invoke(messages)
        tool_calls = getattr(response, "tool_calls", None) or []
        if tool_calls:
            logger.debug("AWS agent calling tools: %s", [t.get("name") for t in tool_calls])
        return {"messages": [response]}

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode(tools))
    graph.add_conditional_edges("agent", tools_condition)
    graph.add_edge("tools", "agent")
    graph.set_entry_point("agent")

    return graph.compile(checkpointer=InMemorySaver())
