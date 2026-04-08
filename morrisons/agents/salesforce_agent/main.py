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

import random
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from shared.http_server import HTTPAgentServer
from shared.models import AgentID
from shared.observability import log_event, increment
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


# ── Demo segment state ────────────────────────────────────────────────────────
_SEGMENT_COUNTS = {
    "HIGH_VALUE":      1_243,
    "AT_RISK_CHURN":     387,
    "FREQUENT_BUYER":  2_891,
    "LAPSED":            652,
    "NEW_CUSTOMER":      218,
}


# ── Periodic: Salesforce loyalty segment pulse ────────────────────────────────
async def salesforce_periodic_segment_pulse() -> None:
    """
    Periodically report active loyalty segment sizes and engagement metrics.
    In production this polls Salesforce REST /query endpoint.
    WSO2 Choreo shows these as background traces.
    """
    tracer = trace.get_tracer(AgentID.SALESFORCE.value)

    with tracer.start_as_current_span(
        f"{AgentID.SALESFORCE.value}/segment_pulse",
        kind=trace.SpanKind.INTERNAL,
        attributes={
            "agent.id":            AgentID.SALESFORCE.value,
            "agent.operation":     "segment_pulse",
            "sf.org":              "morrisons.my.salesforce.com",
            "sf.segments_tracked": len(_SEGMENT_COUNTS),
        },
    ) as span:
        total = 0
        for segment, count in _SEGMENT_COUNTS.items():
            span.add_event(
                "segment_size",
                attributes={"segment": segment, "customers": str(count)},
            )
            total += count
            # Simulate small daily fluctuation
            _SEGMENT_COUNTS[segment] = max(0, count + random.randint(-10, 15))

        # Flag if AT_RISK_CHURN segment is growing
        at_risk = _SEGMENT_COUNTS["AT_RISK_CHURN"]
        if at_risk > 400:
            span.add_event("churn_risk_elevated", attributes={"at_risk_count": str(at_risk)})
            log_event(AgentID.SALESFORCE, "Loyalty pulse: churn risk elevated",
                      {"at_risk_churn": at_risk})
            increment("salesforce.churn_alerts")
        else:
            log_event(AgentID.SALESFORCE, "Loyalty pulse: segment report",
                      {"total_active_customers": total,
                       "at_risk_churn": at_risk,
                       "high_value": _SEGMENT_COUNTS["HIGH_VALUE"]})

        span.set_attribute("sf.total_active_customers", total)
        span.set_status(Status(StatusCode.OK))


server = HTTPAgentServer(
    agent_id=AgentID.SALESFORCE,
    dispatch_fn=salesforce_agent.handle_mcp_call,
    tools_meta=TOOLS,
    periodic_callbacks=[salesforce_periodic_segment_pulse],
    heartbeat_interval=30,
)

if __name__ == "__main__":
    server.run()
