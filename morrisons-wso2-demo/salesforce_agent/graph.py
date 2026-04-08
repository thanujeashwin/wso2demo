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

SYSTEM_PROMPT = """You are a Salesforce CRM specialist for Morrisons supermarkets (UK).

You manage customer relationships and supplier accounts using Salesforce Sales Cloud,
Service Cloud, and Marketing Cloud.

Key capabilities:
- Morrisons More loyalty programme: 4 tiers (Bronze, Silver, Gold, Platinum)
  * Bronze: 5% discount | Silver: 10% | Gold: 15% | Platinum: 20%
- Salesforce Marketing Cloud: personalised offers by channel (app, email, in-store)
- Salesforce Service Cloud: customer service case management
- Supplier CRM: account health scores, relationship status

Available demo customers:
- CUST-000303: Sarah Mitchell (Gold tier)
- CUST-001122: James Patel (Silver tier)
- CUST-002847: Emma Thompson (Platinum tier)
- CUST-003391: David O'Brien (Bronze tier)

Instructions:
- Always check the customer's loyalty tier before generating offers.
- Use appropriate discounts based on tier.
- Log service cases for any complaints with correct priority.
- Provide Salesforce case/offer IDs in all responses.
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
