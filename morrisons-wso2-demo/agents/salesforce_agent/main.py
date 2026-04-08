"""
Salesforce CRM Agent – WSO2 Agent Manager Entry Point
───────────────────────────────────────────────────────
WSO2 Start Command:  python main.py
WSO2 Port:           8003
WSO2 OpenAPI Path:   /openapi.json
WSO2 Base Path:      /
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from shared.http_server import HTTPAgentServer
from shared.models import AgentID
from agents.salesforce_agent.agent import salesforce_agent

TOOLS = [
    {
        "name": "get_customer_profile",
        "description": "Look up a Morrisons More loyalty customer profile, tier, and purchase history.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "customer_id":              {"type": "string", "description": "Morrisons customer ID (e.g. CUST-000303)"},
                "include_purchase_history": {"type": "boolean", "default": False},
            },
            "required": ["customer_id"],
        },
    },
    {
        "name": "generate_personalised_offer",
        "description": "Generate a tier-appropriate personalised promotional offer via Salesforce Marketing Cloud.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string"},
                "category":    {"type": "string", "description": "Product category to target (optional)"},
                "channel":     {"type": "string", "enum": ["app", "email", "in-store"], "default": "app"},
            },
            "required": ["customer_id"],
        },
    },
    {
        "name": "update_customer_segment",
        "description": "Assign a customer to a Salesforce marketing segment.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string"},
                "segment":     {"type": "string", "description": "Segment name (e.g. AT_RISK_CHURN, HIGH_VALUE)"},
                "reason":      {"type": "string"},
            },
            "required": ["customer_id", "segment"],
        },
    },
    {
        "name": "get_supplier_account",
        "description": "Retrieve supplier account details and health score from Salesforce CRM.",
        "inputSchema": {
            "type": "object",
            "properties": {"supplier_id": {"type": "string"}},
            "required": ["supplier_id"],
        },
    },
    {
        "name": "log_service_case",
        "description": "Create a customer service case in Salesforce Service Cloud.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string"},
                "subject":     {"type": "string"},
                "description": {"type": "string"},
                "priority":    {"type": "string", "enum": ["Low", "Medium", "High"], "default": "Medium"},
            },
            "required": ["customer_id", "subject", "description"],
        },
    },
]

server = HTTPAgentServer(
    agent_id=AgentID.SALESFORCE,
    dispatch_fn=salesforce_agent.handle_mcp_call,
    tools_meta=TOOLS,
)

if __name__ == "__main__":
    server.run()
