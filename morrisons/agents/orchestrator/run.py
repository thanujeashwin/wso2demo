"""
Orchestrator Agent – Continuous Server Entry Point

The orchestrator exposes high-level workflow methods as MCP tools.
Each workflow internally calls the sub-agents over their TCP connections.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import json
from typing import Any, Dict, Optional

from shared.agent_server import AgentServer
from shared.models import AgentID
from agents.orchestrator.agent import orchestrator

TOOLS = [
    {"name": "supply_chain_reorder",       "description": "Stock alert → SAP PO → Oracle approval → notify"},
    {"name": "store_ops_query",            "description": "Fan-out IoT + stock + analytics for a store"},
    {"name": "customer_personalisation",   "description": "Real-time loyalty offer via Salesforce + Vertex AI"},
    {"name": "finance_procurement",        "description": "End-to-end Purchase-to-Pay workflow (8 agents)"},
    {"name": "switch_model",               "description": "Switch active LLM model (claude/gemini/gpt4o/nova/mistral)"},
    {"name": "list_agents",               "description": "Return agent catalogue and status"},
]


async def orchestrator_dispatch(
    tool_name: str, arguments: Dict[str, Any], trace_id: Optional[str] = None
) -> Dict[str, Any]:
    """Route orchestrator tool calls to the right workflow method."""
    if tool_name == "supply_chain_reorder":
        return await orchestrator.run_supply_chain_workflow(
            sku=arguments.get("sku", "SKU-BEEF-001"),
            store_id=arguments.get("store_id", "STORE-001"),
            notify=arguments.get("notify", True),
        )
    elif tool_name == "store_ops_query":
        return await orchestrator.run_store_ops_query(
            store_id=arguments.get("store_id", "STORE-001"),
            query=arguments.get("query", "What is the store status?"),
        )
    elif tool_name == "customer_personalisation":
        return await orchestrator.run_customer_personalisation(
            customer_id=arguments.get("customer_id", "CUST-000303"),
            channel=arguments.get("channel", "app"),
        )
    elif tool_name == "finance_procurement":
        return await orchestrator.run_finance_procurement(
            sku=arguments.get("sku", "SKU-SALM-004"),
            quantity=arguments.get("quantity", 100),
            supplier_id=arguments.get("supplier_id", "SUP-004"),
            cost_centre=arguments.get("cost_centre", "CC-FISH-003"),
            requestor=arguments.get("requestor", "SYSTEM"),
        )
    elif tool_name == "switch_model":
        msg = orchestrator.switch_model(arguments.get("model", "claude-sonnet-4-6"))
        return {"message": msg, "active_model": orchestrator.active_model}
    elif tool_name == "list_agents":
        return orchestrator.list_agents()
    else:
        return {"error": f"Unknown orchestrator tool: {tool_name}"}


class OrchestratorServer(AgentServer):
    def _tool_list(self): return TOOLS


server = OrchestratorServer(AgentID.ORCHESTRATOR, orchestrator_dispatch)

if __name__ == "__main__":
    server.run()
