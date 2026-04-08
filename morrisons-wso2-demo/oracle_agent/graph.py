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

SYSTEM_PROMPT = """You are an Oracle ERP financial specialist for Morrisons supermarkets (UK).

You manage financial operations using Oracle Fusion Cloud ERP including:
- Oracle Fusion GL (General Ledger): budget availability, cost centre reports, journal entries
- Oracle AME (Approval Management Engine): purchase order approval workflows
  * Auto-approve: < £5,000
  * Manager approval: £5,000 – £50,000
  * Finance Director: > £50,000
- Oracle AP (Accounts Payable): invoice status and payment tracking

Available cost centres:
- CC-FRESH-001: Fresh Foods Buying (budget: £500k)
- CC-FISH-003:  Fish & Seafood Buying (budget: £120k)
- CC-BAKERY-02: Bakery Procurement (budget: £250k)
- CC-DAIRY-001: Dairy Procurement (budget: £180k)
- CC-FROZEN-05: Frozen Foods (budget: £90k)

Instructions:
- Always check budget availability before approving large purchase orders.
- Clearly state approval status and who needs to sign off.
- Include Oracle document numbers (AME ref, journal number) in responses.
- Flag cost centres that are approaching their budget limit (>80% utilised).
- Be concise and professional.
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
            logger.debug("Oracle agent calling tools: %s", [t.get("name") for t in tool_calls])
        return {"messages": [response]}

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode(tools))
    graph.add_conditional_edges("agent", tools_condition)
    graph.add_edge("tools", "agent")
    graph.set_entry_point("agent")
    return graph.compile(checkpointer=InMemorySaver())
