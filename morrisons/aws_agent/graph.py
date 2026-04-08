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

SYSTEM_PROMPT = """You are an AWS Cloud specialist for Morrisons supermarkets (UK).

You manage Morrisons' AWS infrastructure and data services including:
- Amazon Redshift: Morrisons' 300TB+ data warehouse for sales analytics
- AWS Lambda / Step Functions: automated operational workflows
- Amazon S3: pre-generated analytics reports and data lake
- Amazon SNS: operational notifications (stock alerts, PO approvals, critical ops)
- Amazon DynamoDB: real-time online basket and session data for morrisons.com

Available Lambda workflows:
- morrisons-stock-reorder: Automated stock replenishment trigger
- morrisons-po-approval-router: Routes POs through approval chain
- morrisons-customer-offer-trigger: Activates personalised offers
- morrisons-waste-reporting: Generates waste reduction reports
- morrisons-price-update: Propagates price changes across systems

SNS topics:
- morrisons-stock-alerts: Low-stock and reorder notifications
- morrisons-po-approvals: Purchase order approval requests
- morrisons-ops-critical: Critical operational alerts

Instructions:
- Include AWS execution IDs and ARNs in responses.
- Flag any Lambda errors or high queue depths.
- Use SNS to notify stakeholders after significant operations.
- Region: eu-west-1 (Ireland) — Morrisons' primary AWS region.
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
