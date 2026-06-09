"""
Morrisons Salesforce CRM Agent – LangGraph Graph
=================================================
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

SYSTEM_PROMPT = """You are a Salesforce CRM specialist agent for Morrisons supermarkets (UK).

You manage customer profiles, loyalty programmes, personalised offers,
supplier accounts, and service cases using Salesforce Sales & Service Cloud.

Key Salesforce objects: Contact, Account, Opportunity, Case, Campaign.
Loyalty tiers: Bronze (0–499 pts), Silver (500–1999 pts), Gold (2000+ pts).

Demo customers: CUST-100142 (Gold), CUST-100256 (Silver), CUST-100389 (Bronze)
Demo supplier accounts: ACC-SUP-00234, ACC-SUP-00891
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
            logger.debug("Salesforce agent calling tools: %s", [t.get("name") for t in tool_calls])
        return {"messages": [response]}

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode(tools))
    graph.add_conditional_edges("agent", tools_condition)
    graph.add_edge("tools", "agent")
    graph.set_entry_point("agent")

    return graph.compile(checkpointer=InMemorySaver())
