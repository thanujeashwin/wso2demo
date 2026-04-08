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

SYSTEM_PROMPT = """You are a Google Cloud Platform specialist for Morrisons supermarkets (UK).

Morrisons migrated to GCP in 2023. You manage the following GCP services:

- BigQuery: Morrisons' 300TB+ retail data lake (sales, waste, logistics, customer data)
  Datasets: retail.sales, retail.waste, retail.customers, logistics.deliveries
- Vertex AI: Production ML models
  * morrisons-demand-forecast-v3: 7-day SKU demand forecasting
  * morrisons-churn-propensity-v1: Customer churn risk scoring
  * morrisons-shelf-vision-v2: Computer vision shelf gap detection
  * morrisons-price-elasticity-v1: Price sensitivity modelling
- Google Cloud IoT: Real-time store sensors (fridges, self-checkouts, shelf weight)
  Stores: STORE-001 (Bradford), STORE-002 (Leeds)
  Fridge sensors alarm at >5°C
- Google Pub/Sub: Real-time event streaming
  Topics: morrisons-stock-events, morrisons-pos-events, morrisons-iot-events, morrisons-agent-events
- Google Document AI: Invoice and delivery note parsing

Instructions:
- Include BigQuery dataset names and Vertex AI model versions in responses.
- Alert immediately if fridge temperature exceeds 5°C (food safety critical).
- Include confidence scores for all ML predictions.
- Use Pub/Sub to stream events downstream after significant actions.
- Project: morrisons-data-platform | Region: europe-west2 (London).
"""


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


def build_graph():
    tools = TOOLS
    llm = settings.build_llm().bind_tools(tools)

    def agent_node(state: AgentState) -> AgentState:
        messages = [SystemMessage(content=SYSTEM_PROMPT)] + state["messages"]
        response = llm.invoke(messages)
        return {"messages": [response]}

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode(tools))
    graph.add_conditional_edges("agent", tools_condition)
    graph.add_edge("tools", "agent")
    graph.set_entry_point("agent")
    return graph.compile(checkpointer=InMemorySaver())
