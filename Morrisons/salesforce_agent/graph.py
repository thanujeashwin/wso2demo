"""
Morrisons Salesforce CRM Agent – LangGraph Graph
=================================================
LangGraph ReAct agent: agent node ↔ tools node.
Uses DemoLLM – no API key required. Full LangGraph pipeline
preserved so Traceloop emits spans on every invocation.
"""
from __future__ import annotations

import logging
import uuid
from typing import Annotated, Any, List, TypedDict

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from pydantic import ConfigDict, Field

from tools import TOOLS

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
# Demo LLM – keyword-driven tool selection, no API key needed
# ---------------------------------------------------------------------------

_TOOL_ROUTES = [
    (["offer", "promotion", "deal", "discount", "personalise"], "generate_personalised_offer",
     {"customer_id": "CUST-100142", "channel": "app", "category": "Fresh Produce"}),
    (["segment", "tier", "upgrade", "classify"],                "update_customer_segment",
     {"customer_id": "CUST-100142", "segment": "HIGH_VALUE",
      "reason": "High YTD spend and loyalty points"}),
    (["supplier account", "vendor account", "b2b", "account"],  "get_supplier_account",
     {"supplier_id": "SUP-001"}),
    (["case", "complaint", "issue", "service", "problem"],      "log_service_case",
     {"customer_id": "CUST-100142", "subject": "Product Quality Concern",
      "description": "Customer reported quality concern with fresh produce delivery",
      "priority": "Medium"}),
    (["customer", "profile", "loyalty", "contact", "member"],   "get_customer_profile",
     {"customer_id": "CUST-100142"}),
]
_DEFAULT_TOOL = ("get_customer_profile", {"customer_id": "CUST-100142"})


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
            tool_output = next(
                (m.content for m in reversed(messages) if isinstance(m, ToolMessage)), ""
            )
            reply = (
                f"{tool_output}\n\n"
                "✓ Salesforce CRM data retrieved successfully. "
                "Let me know if you need further customer or account information."
            )
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content=reply))])

        tool_name, args = self._select(messages)
        tool_obj = next((t for t in self.bound_tools if t.name == tool_name), self.bound_tools[0])
        return ChatResult(generations=[ChatGeneration(
            message=AIMessage(
                content="",
                tool_calls=[{"name": tool_obj.name, "args": args,
                             "id": f"sf_{uuid.uuid4().hex[:8]}"}],
            )
        )])

    def _select(self, messages):
        text = " ".join(
            m.content.lower() for m in messages
            if isinstance(m, BaseMessage) and not isinstance(m, ToolMessage)
        )
        for keywords, name, args in _TOOL_ROUTES:
            if any(k in text for k in keywords):
                return name, args
        return _DEFAULT_TOOL


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
            logger.debug("Salesforce agent calling tools: %s", [t.get("name") for t in tool_calls])
        return {"messages": [response]}

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode(tools))
    graph.add_conditional_edges("agent", tools_condition)
    graph.add_edge("tools", "agent")
    graph.set_entry_point("agent")

    return graph.compile(checkpointer=InMemorySaver())
