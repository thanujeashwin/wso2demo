"""
Orchestrator Agent – WSO2 Agent Manager Entry Point
─────────────────────────────────────────────────────
WSO2 Start Command:  python main.py
WSO2 Port:           8000
WSO2 OpenAPI Path:   /openapi.json
WSO2 Base Path:      /

The orchestrator is the primary agent exposed to end-users in the
WSO2 Agent Manager portal. It accepts high-level workflow requests
and fans out to the 5 sub-agents internally.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from typing import Any, Dict, Optional
from shared.http_server import HTTPAgentServer
from shared.models import AgentID
from agents.orchestrator.agent import orchestrator

TOOLS = [
    {
        "name": "supply_chain_reorder",
        "description": "End-to-end supply chain workflow: checks SAP stock, runs Vertex AI demand forecast, raises SAP purchase order, gets Oracle finance approval, notifies via AWS SNS and GCP Pub/Sub.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "sku":      {"type": "string", "description": "Product SKU to reorder (e.g. SKU-BEEF-001)"},
                "store_id": {"type": "string", "default": "STORE-001"},
                "notify":   {"type": "boolean", "default": True,
                             "description": "Send SNS + Pub/Sub notifications on completion"},
            },
            "required": ["sku"],
        },
    },
    {
        "name": "store_ops_query",
        "description": "Real-time store health check: fans out in parallel to GCP IoT sensors, SAP stock levels, and BigQuery analytics to give a complete store status view.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "store_id": {"type": "string", "description": "Morrisons store ID (e.g. STORE-001)"},
                "query":    {"type": "string", "description": "Natural-language query about the store"},
            },
            "required": ["store_id"],
        },
    },
    {
        "name": "customer_personalisation",
        "description": "Real-time loyalty offer pipeline: fetches Salesforce customer profile and Vertex AI churn prediction in parallel, generates a personalised offer, and triggers delivery via Pub/Sub.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string", "description": "Morrisons More customer ID (e.g. CUST-000303)"},
                "channel":     {"type": "string", "enum": ["app", "email", "in-store"], "default": "app"},
            },
            "required": ["customer_id"],
        },
    },
    {
        "name": "finance_procurement",
        "description": "Full Purchase-to-Pay (P2P) workflow across 8 steps: Oracle budget check, Salesforce supplier health, SAP PO creation, Oracle AME approval, GCP Document AI invoice parsing, Oracle GL journal, AWS SNS alert.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "sku":         {"type": "string"},
                "quantity":    {"type": "integer", "minimum": 1},
                "supplier_id": {"type": "string"},
                "cost_centre": {"type": "string", "description": "Oracle cost centre (e.g. CC-FISH-003)"},
                "requestor":   {"type": "string", "default": "SYSTEM"},
            },
            "required": ["sku", "quantity", "supplier_id", "cost_centre"],
        },
    },
    {
        "name": "switch_model",
        "description": "Switch the active LLM model used by the orchestrator. Models available: claude-sonnet-4-6, gemini-2.0-pro, gpt-4o, amazon-nova-pro, mistral-large.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "model": {"type": "string",
                          "enum": ["claude-sonnet-4-6", "gemini-2.0-pro",
                                   "gpt-4o", "amazon-nova-pro", "mistral-large"]},
            },
            "required": ["model"],
        },
    },
    {
        "name": "list_agents",
        "description": "Return the full agent catalogue with status for all registered sub-agents.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


async def orchestrator_dispatch(
    tool_name: str, arguments: Dict[str, Any], trace_id: Optional[str] = None
) -> Dict[str, Any]:
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
    return {"error": f"Unknown tool: {tool_name}"}


server = HTTPAgentServer(
    agent_id=AgentID.ORCHESTRATOR,
    dispatch_fn=orchestrator_dispatch,
    tools_meta=TOOLS,
)

if __name__ == "__main__":
    server.run()
