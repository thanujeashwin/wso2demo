"""
Morrisons Orchestrator Agent – LangGraph Graph
===============================================
Master orchestrator that fans out to 5 specialist sub-agents.
Uses the same LangGraph ReAct pattern as WSO2 Agent Manager samples.
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

SYSTEM_PROMPT = """You are the Morrisons AI Orchestrator — the master agent for Morrisons supermarkets (UK).

You coordinate five specialist sub-agents to handle complex, multi-system workflows:

SPECIALIST AGENTS (use the ask_* tools to delegate):
┌─────────────────────────┬──────────────────────────────────────────────────┐
│ ask_sap_erp_agent       │ Stock levels, purchase orders, demand forecasts  │
│ ask_oracle_erp_agent    │ Budget checks, PO approvals, invoices, journals  │
│ ask_salesforce_agent    │ Customer loyalty, personalised offers, CRM       │
│ ask_aws_agent           │ Sales analytics, Lambda workflows, SNS alerts    │
│ ask_gcp_agent           │ BigQuery, Vertex AI ML, IoT sensors, Pub/Sub     │
└─────────────────────────┴──────────────────────────────────────────────────┘

COMMON WORKFLOWS you handle:
1. Supply Chain Reorder: SAP stock check → GCP demand forecast → SAP PO → Oracle approval → AWS SNS notification
2. Store Health Check: GCP IoT sensors + SAP stock levels + AWS/GCP analytics (run these in parallel where possible)
3. Customer Personalisation: Salesforce profile → GCP churn prediction → Salesforce offer → GCP Pub/Sub
4. Purchase-to-Pay (P2P): Oracle budget check → Salesforce supplier health → SAP PO → Oracle AME approval → GCP invoice parse → Oracle GL journal → AWS SNS

ORCHESTRATION PRINCIPLES:
- Break complex requests into sub-tasks and call the right specialist.
- When tasks are independent, mention you are calling multiple agents.
- Always synthesise results from sub-agents into a clear, actionable summary.
- Include document numbers (PO, AME ref, case numbers) from sub-agent responses.
- If a sub-agent returns an error, explain it and suggest alternatives.
- Be concise but comprehensive in your final response.

You represent Morrisons' commitment to AI-driven retail operations.
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
            logger.info("Orchestrator delegating to: %s", [t.get("name") for t in tool_calls])
        return {"messages": [response]}

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode(tools))
    graph.add_conditional_edges("agent", tools_condition)
    graph.add_edge("tools", "agent")
    graph.set_entry_point("agent")
    return graph.compile(checkpointer=InMemorySaver())
