"""
Morrisons AWS Cloud Agent – LangGraph Graph
============================================
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

SYSTEM_PROMPT = """You are an AWS Cloud specialist agent for Morrisons supermarkets (UK).

You manage cloud analytics, serverless workflows, data storage, notifications,
and session data using Amazon Web Services.

Key AWS services in use:
- S3: Report storage and data lake
- Lambda: Serverless reorder and pricing workflows
- DynamoDB: Customer session data
- SNS: Operational alerts and notifications
- Redshift/Athena: Sales trend analytics

Store IDs: STORE-001 (Bradford HQ), STORE-042 (Leeds), STORE-107 (Manchester)
"""

# ---------------------------------------------------------------------------
# Demo LLM – keyword-driven tool selection, no API key needed
# ---------------------------------------------------------------------------

_TOOL_ROUTES = [
    (["lambda", "workflow", "trigger", "function", "serverless"], "trigger_lambda_workflow",
     {"workflow_name": "low-stock-reorder",
      "payload": '{"store": "STORE-001", "sku": "SKU-BEEF-001", "threshold": 50}'}),
    (["s3", "report", "file", "download", "bucket"],             "get_s3_report",
     {"report_name": "daily-sales-summary"}),
    (["notification", "alert", "sns", "message", "notify"],      "send_sns_notification",
     {"topic": "ops-alerts", "subject": "Low Stock Alert",
      "message": "SKU-BEEF-001 is below reorder level at STORE-001"}),
    (["session", "dynamo", "dynamodb", "cart", "basket"],        "query_dynamodb_session",
     {"session_id": "SESSION-DEMO-001"}),
    (["sales", "trend", "analytics", "performance", "revenue"],  "analyse_sales_trends",
     {"sku": "SKU-BEEF-001", "weeks": 4}),
]
_DEFAULT_TOOL = ("analyse_sales_trends", {"sku": "SKU-BEEF-001", "weeks": 4})


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
                "✓ AWS Cloud data retrieved successfully. "
                "Let me know if you need further cloud infrastructure information."
            )
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content=reply))])

        tool_name, args = self._select(messages)
        tool_obj = next((t for t in self.bound_tools if t.name == tool_name), self.bound_tools[0])
        return ChatResult(generations=[ChatGeneration(
            message=AIMessage(
                content="",
                tool_calls=[{"name": tool_obj.name, "args": args,
                             "id": f"aws_{uuid.uuid4().hex[:8]}"}],
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
            logger.debug("AWS agent calling tools: %s", [t.get("name") for t in tool_calls])
        return {"messages": [response]}

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode(tools))
    graph.add_conditional_edges("agent", tools_condition)
    graph.add_edge("tools", "agent")
    graph.set_entry_point("agent")

    return graph.compile(checkpointer=InMemorySaver())
