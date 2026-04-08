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

import random
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from shared.http_server import HTTPAgentServer
from shared.models import AgentID
from shared.observability import log_event, increment
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


# ── Demo budget state (simulates Oracle Fusion GL) ───────────────────────────
_BUDGET_STATE = {
    "CC-FRESH-001": {"allocated": 500_000, "spent": 412_000},
    "CC-FISH-003":  {"allocated": 120_000, "spent":  98_500},
    "CC-BAKERY-02": {"allocated": 250_000, "spent": 231_000},
}


# ── Periodic: Oracle budget utilisation monitor ───────────────────────────────
async def oracle_periodic_budget_monitor() -> None:
    """
    Periodically report budget utilisation across cost centres.
    In production this would poll Oracle Fusion GL REST API.
    WSO2 Choreo will show these as background traces.
    """
    tracer = trace.get_tracer(AgentID.ORACLE_ERP.value)

    with tracer.start_as_current_span(
        f"{AgentID.ORACLE_ERP.value}/budget_monitor",
        kind=trace.SpanKind.INTERNAL,
        attributes={
            "agent.id":          AgentID.ORACLE_ERP.value,
            "agent.operation":   "budget_monitor",
            "oracle.ledger":     "Morrisons_UK_Primary",
            "oracle.cost_centres": len(_BUDGET_STATE),
        },
    ) as span:
        near_limit = []
        for cc, b in _BUDGET_STATE.items():
            utilisation = b["spent"] / b["allocated"] if b["allocated"] else 0
            span.add_event(
                "budget_utilisation",
                attributes={
                    "cost_centre":  cc,
                    "utilisation":  f"{utilisation:.1%}",
                    "remaining_gbp": str(b["allocated"] - b["spent"]),
                },
            )
            if utilisation >= 0.90:
                near_limit.append(cc)
            # Simulate incremental spend
            _BUDGET_STATE[cc]["spent"] = min(
                b["allocated"],
                b["spent"] + random.randint(0, 2000)
            )

        if near_limit:
            log_event(AgentID.ORACLE_ERP, "Oracle budget monitor: near-limit alert",
                      {"cost_centres": near_limit})
            increment("oracle.budget_alerts", len(near_limit))
        else:
            log_event(AgentID.ORACLE_ERP, "Oracle budget monitor: all cost centres within limits",
                      {"cost_centres_checked": len(_BUDGET_STATE)})
        span.set_status(Status(StatusCode.OK))


server = HTTPAgentServer(
    agent_id=AgentID.ORACLE_ERP,
    dispatch_fn=oracle_agent.handle_mcp_call,
    tools_meta=TOOLS,
    periodic_callbacks=[oracle_periodic_budget_monitor],
    heartbeat_interval=30,
)

if __name__ == "__main__":
    server.run()
