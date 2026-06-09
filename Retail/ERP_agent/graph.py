"""
Morrisons Oracle ERP Agent – LangGraph Graph
=============================================
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

SYSTEM_PROMPT = """You are an Oracle ERP Finance specialist agent for Morrisons supermarkets (UK).

You manage budgets, purchase order approvals, cost centre reporting, invoices,
and journal entries using Oracle Fusion Cloud ERP.

Key Oracle modules: General Ledger, Accounts Payable, Procurement,
Cost Management, Budgetary Control.

Cost Centres: CC-PRODUCE-01, CC-MEAT-02, CC-DAIRY-03, CC-BAKERY-04
Fiscal periods: 2026-Q1, 2026-Q2, 2025-Q4
"""

# ---------------------------------------------------------------------------
# Demo LLM – keyword-driven tool selection, no API key needed
# ---------------------------------------------------------------------------

_TOOL_ROUTES = [
    (["approve", "approval", "authorise", "sign off"],         "approve_purchase_order",
     {"po_number": "PO-004501", "total_value": 4800.00,
      "cost_centre": "CC-PRODUCE-01", "category": "Fresh Meat"}),
    (["cost centre", "cost center", "spend", "expenditure"],   "get_cost_centre_report",
     {"cost_centre": "CC-PRODUCE-01", "period": "QTD"}),
    (["invoice", "payment", "payable", "pay"],                 "get_invoice_status",
     {"po_number": "PO-004501"}),
    (["journal", "entry", "gl", "ledger", "account"],          "create_journal_entry",
     {"debit_account": "5100-COGS", "credit_account": "1200-INVENTORY",
      "amount": 15000.0, "description": "Quarterly stock adjustment – Produce",
      "cost_centre": "CC-PRODUCE-01"}),
    (["budget", "available", "funds", "remaining"],            "get_budget_availability",
     {"cost_centre": "CC-PRODUCE-01", "fiscal_year": 2026}),
]
_DEFAULT_TOOL = ("get_budget_availability",
                 {"cost_centre": "CC-PRODUCE-01", "fiscal_year": 2026})


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
                "✓ Oracle ERP data retrieved successfully. "
                "Let me know if you need further financial information."
            )
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content=reply))])

        tool_name, args = self._select(messages)
        tool_obj = next((t for t in self.bound_tools if t.name == tool_name), self.bound_tools[0])
        return ChatResult(generations=[ChatGeneration(
            message=AIMessage(
                content="",
                tool_calls=[{"name": tool_obj.name, "args": args,
                             "id": f"ora_{uuid.uuid4().hex[:8]}"}],
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
            logger.debug("Oracle agent calling tools: %s", [t.get("name") for t in tool_calls])
        return {"messages": [response]}

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode(tools))
    graph.add_conditional_edges("agent", tools_condition)
    graph.add_edge("tools", "agent")
    graph.set_entry_point("agent")

    return graph.compile(checkpointer=InMemorySaver())
