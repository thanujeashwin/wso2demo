"""
Morrisons GCP Cloud Agent – LangGraph Graph
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

SYSTEM_PROMPT = """You are a Google Cloud Platform specialist agent for Morrisons supermarkets (UK).

You manage analytics, AI/ML predictions, event streaming, IoT sensor data,
and document processing using Google Cloud Platform.

Key GCP services in use:
- BigQuery: Enterprise analytics and data warehouse
- Vertex AI: Demand forecasting and product recommendation models
- Pub/Sub: Real-time event streaming for reorder and pricing events
- IoT Core / Cloud IoT: Store refrigeration and environmental sensors
- Document AI: Automated invoice and supplier document processing

Store IDs: STORE-001 (Bradford HQ), STORE-042 (Leeds), STORE-107 (Manchester)
Vertex AI models: demand-forecast-v2, product-recommender-v1, price-optimiser-v3
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
            logger.debug("GCP agent calling tools: %s", [t.get("name") for t in tool_calls])
        return {"messages": [response]}

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode(tools))
    graph.add_conditional_edges("agent", tools_condition)
    graph.add_edge("tools", "agent")
    graph.set_entry_point("agent")

    return graph.compile(checkpointer=InMemorySaver())
