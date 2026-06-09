"""
Morrisons SAP ERP Agent – LangGraph Graph
==========================================
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

SYSTEM_PROMPT = """You are a SAP ERP specialist agent for Morrisons supermarkets (UK).

You help manage inventory, purchase orders, supplier data, and demand forecasting
using SAP S/4HANA running on Google Cloud Platform.

Key SAP modules: MM (Materials Management), IBP (Integrated Business Planning),
BP (Business Partner / Vendor Master).

Available SKUs: SKU-BEEF-001, SKU-MILK-003, SKU-BREA-007, SKU-CHIC-002, SKU-SALM-004
Available Suppliers: SUP-001 (British Meat Supplies), SUP-002 (Northern Dairy Co-op),
                     SUP-003 (Allied Bakery UK), SUP-004 (Scottish Seafood Partners)
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
            logger.debug("SAP agent calling tools: %s", [t.get("name") for t in tool_calls])
        return {"messages": [response]}

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode(tools))
    graph.add_conditional_edges("agent", tools_condition)
    graph.add_edge("tools", "agent")
    graph.set_entry_point("agent")

    return graph.compile(checkpointer=InMemorySaver())
