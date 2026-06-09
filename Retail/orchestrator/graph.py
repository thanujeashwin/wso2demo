"""
Morrisons Orchestrator Agent – LangGraph Graph
===============================================
Master orchestrator that fans out to 5 specialist sub-agents.
Uses DemoLLM – no API key required. Full LangGraph pipeline
preserved so Traceloop emits spans on every invocation.
"""
from __future__ import annotations

import logging
import uuid
from typing import Annotated, Any, List, TypedDict

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from pydantic import ConfigDict, Field

from tools import TOOLS

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are the Morrisons AI Orchestrator — the master agent for Morrisons supermarkets (UK).

You coordinate five specialist sub-agents to handle complex, multi-system workflows:

SPECIALIST AGENTS (use the ask_* tools to delegate):
  ask_sap_erp_agent    – Stock levels, purchase orders, demand forecasts
  ask_oracle_erp_agent – Budget checks, PO approvals, invoices, journals
  ask_salesforce_agent – Customer loyalty, personalised offers, CRM
  ask_aws_agent        – Sales analytics, Lambda workflows, SNS alerts
  ask_gcp_agent        – BigQuery, Vertex AI ML, IoT sensors, Pub/Sub

COMMON WORKFLOWS you handle:
1. Supply Chain Reorder: SAP stock check → GCP demand forecast → SAP PO → Oracle approval → AWS alert
2. Store Health Check: GCP IoT + SAP stock + AWS/GCP analytics
3. Customer Personalisation: Salesforce profile → GCP prediction → Salesforce offer
4. Purchase-to-Pay: Oracle budget → Salesforce supplier health → SAP PO → Oracle approval → GCP invoice

Always synthesise results from sub-agents into a clear, actionable summary.
"""

# ---------------------------------------------------------------------------
# Demo LLM – keyword-driven sub-agent routing, no API key needed
# ---------------------------------------------------------------------------

_TOOL_ROUTES = [
    (["sap", "stock", "inventory", "purchase order", "goods", "reorder", "supplier", "mm ", "ibp"],
     "ask_sap_erp_agent"),
    (["oracle", "budget", "finance", "invoice", "approval", "cost centre", "journal", "gl "],
     "ask_oracle_erp_agent"),
    (["salesforce", "customer", "loyalty", "crm", "offer", "promotion", "case", "complaint"],
     "ask_salesforce_agent"),
    (["aws", "lambda", "s3 ", "dynamodb", "sns", "redshift", "athena"],
     "ask_aws_agent"),
    (["gcp", "bigquery", "vertex", "pubsub", "iot", "sensor", "document ai", "forecast"],
     "ask_gcp_agent"),
]
_DEFAULT_TOOL = "ask_sap_erp_agent"


class DemoLLM(BaseChatModel):
    """Mock LLM for WSO2 Agent Manager demo – no API key required."""
    model_config = ConfigDict(arbitrary_types_allowed=True)
    bound_tools: List[Any] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "demo-mock"

    def bind_tools(self, tools, **kwargs) -> "DemoLLM":
        return DemoLLM(bound_tools=list(tools))

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        has_tool_result = any(isinstance(m, ToolMessage) for m in messages)

        if has_tool_result or not self.bound_tools:
            # Synthesise all sub-agent responses
            tool_outputs = [m.content for m in messages if isinstance(m, ToolMessage)]
            combined = "\n\n---\n\n".join(tool_outputs) if tool_outputs else "Processing complete."
            reply = (
                f"Here is the consolidated response from the Morrisons specialist agents:\n\n"
                f"{combined}\n\n"
                "✓ Orchestration complete. All specialist systems have been queried successfully."
            )
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content=reply))])

        # Pick which sub-agent to call and extract the human question
        tool_name = self._select_agent(messages)
        question = self._extract_question(messages)
        tool_obj = next((t for t in self.bound_tools if t.name == tool_name), self.bound_tools[0])

        args = {"question": question, "session_id": "orchestrator-demo"}
        return ChatResult(generations=[ChatGeneration(
            message=AIMessage(
                content="",
                tool_calls=[{"name": tool_obj.name, "args": args,
                             "id": f"orch_{uuid.uuid4().hex[:8]}"}],
            )
        )])

    def _select_agent(self, messages) -> str:
        text = " ".join(
            m.content.lower() for m in messages
            if isinstance(m, BaseMessage) and not isinstance(m, ToolMessage)
        )
        for keywords, name in _TOOL_ROUTES:
            if any(k in text for k in keywords):
                return name
        return _DEFAULT_TOOL

    def _extract_question(self, messages) -> str:
        for m in reversed(messages):
            if isinstance(m, HumanMessage):
                # Strip the context wrapper added by app.py
                content = m.content
                if "User: " in content:
                    return content.split("User: ", 1)[-1].strip()
                return content
        return "What is the current status of our operations?"


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------

class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


def build_graph():
    tools = TOOLS
    llm = DemoLLM().bind_tools(tools)

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
