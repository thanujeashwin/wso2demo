"""
Morrisons SAP ERP Agent – LangGraph Graph
==========================================
LangGraph ReAct agent: agent node ↔ tools node.
Follows the exact pattern of WSO2 Agent Manager sample agents.
"""
from __future__ import annotations

import logging
from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage, SystemMessage
from langgraph.graph import StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.memory import InMemorySaver

from config import settings
from tools import TOOLS

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a SAP ERP specialist agent for Morrisons supermarkets (UK).

You help manage inventory, purchase orders, supplier data, and demand forecasting \
using SAP S/4HANA, which Morrisons runs on Google Cloud Platform.

Key SAP modules available:
- MM (Materials Management): stock levels, goods movements, purchase orders
- IBP (Integrated Business Planning): 90-day demand forecasting
- BP (Business Partner): vendor master data

Available SKUs for this demo:
- SKU-BEEF-001: Morrisons Best Beef Mince 500g (supplier SUP-001)
- SKU-MILK-003: Morrisons Whole Milk 4 Pints (supplier SUP-002)
- SKU-BREA-007: Morrisons White Thick Bread (supplier SUP-003)
- SKU-CHIC-002: Morrisons Chicken Breast 500g (supplier SUP-001)
- SKU-SALM-004: Morrisons Scottish Salmon 240g (supplier SUP-004)

Instructions:
- Always check stock before raising a purchase order.
- Include SAP document numbers and supplier details in your responses.
- Flag any SKUs below reorder level proactively.
- Use demand forecast data to recommend appropriate order quantities.
- Be concise and professional in your responses.
"""


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
