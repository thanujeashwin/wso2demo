"""
Morrisons Oracle ERP Agent – LangGraph Graph
=============================================
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

SYSTEM_PROMPT = """You are an Oracle ERP Finance specialist agent for Morrisons supermarkets (UK).

You manage budgets, purchase order approvals, cost centre reporting, invoices,
and journal entries using Oracle Fusion Cloud ERP.

Key Oracle modules: General Ledger, Accounts Payable, Procurement,
Cost Management, Budgetary Control.

Cost Centres: CC-PRODUCE-01, CC-MEAT-02, CC-DAIRY-03, CC-BAKERY-04
Fiscal periods: 2026-Q1, 2026-Q2, 2025-Q4
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
            logger.debug("Oracle agent calling tools: %s", [t.get("name") for t in tool_calls])
        return {"messages": [response]}

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode(tools))
    graph.add_conditional_edges("agent", tools_condition)
    graph.add_edge("tools", "agent")
    graph.set_entry_point("agent")

    return graph.compile(checkpointer=InMemorySaver())
