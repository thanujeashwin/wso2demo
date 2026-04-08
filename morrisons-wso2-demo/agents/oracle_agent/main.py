"""
Oracle ERP Agent – WSO2 Agent Manager Entry Point
──────────────────────────────────────────────────
WSO2 Start Command:  python main.py
WSO2 Port:           8002
WSO2 OpenAPI Path:   /openapi.json
WSO2 Base Path:      /
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from shared.http_server import HTTPAgentServer
from shared.models import AgentID
from agents.oracle_agent.agent import oracle_agent

TOOLS = [
    {
        "name": "get_budget_availability",
        "description": "Query Oracle Fusion GL for remaining budget on a cost centre.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cost_centre": {"type": "string", "description": "Cost centre code (e.g. CC-FRESH-001)"},
                "fiscal_year": {"type": "integer", "description": "Fiscal year (defaults to current)"},
            },
            "required": ["cost_centre"],
        },
    },
    {
        "name": "approve_purchase_order",
        "description": "Submit a PO to Oracle Approval Management Engine (AME). Auto-approves <£5k, routes to manager £5k-£50k, requires Finance Director above £50k.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "po_number":   {"type": "string"},
                "total_value": {"type": "number", "description": "Total PO value in GBP"},
                "cost_centre": {"type": "string"},
                "category":    {"type": "string"},
                "requester":   {"type": "string", "default": "SYSTEM"},
            },
            "required": ["po_number", "total_value", "cost_centre", "category"],
        },
    },
    {
        "name": "get_cost_centre_report",
        "description": "Retrieve spend report for a cost centre (MTD, QTD, or YTD).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cost_centre": {"type": "string"},
                "period":      {"type": "string", "enum": ["MTD", "QTD", "YTD"], "default": "MTD"},
            },
            "required": ["cost_centre"],
        },
    },
    {
        "name": "get_invoice_status",
        "description": "Check Oracle AP invoice payment status for a given purchase order.",
        "inputSchema": {
            "type": "object",
            "properties": {"po_number": {"type": "string"}},
            "required": ["po_number"],
        },
    },
    {
        "name": "create_journal_entry",
        "description": "Post a journal entry to Oracle General Ledger.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "description":    {"type": "string"},
                "debit_account":  {"type": "string"},
                "credit_account": {"type": "string"},
                "amount":         {"type": "number"},
                "cost_centre":    {"type": "string"},
            },
            "required": ["description", "debit_account", "credit_account", "amount", "cost_centre"],
        },
    },
]

server = HTTPAgentServer(
    agent_id=AgentID.ORACLE_ERP,
    dispatch_fn=oracle_agent.handle_mcp_call,
    tools_meta=TOOLS,
)

if __name__ == "__main__":
    server.run()
