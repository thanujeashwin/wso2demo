"""
SAP ERP Agent – WSO2 Agent Manager Entry Point
───────────────────────────────────────────────
WSO2 Start Command:  python main.py
WSO2 Port:           8001
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
from agents.sap_agent.agent import sap_agent, MOCK_STOCK

TOOLS = [
    {
        "name": "check_stock_level",
        "description": "Query SAP MM for real-time stock level at a given Morrisons store.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "sku":      {"type": "string",  "description": "SAP Material Number (e.g. SKU-BEEF-001)"},
                "store_id": {"type": "string",  "description": "Morrisons store ID (e.g. STORE-001)", "default": "STORE-001"},
            },
            "required": ["sku"],
        },
    },
    {
        "name": "raise_purchase_order",
        "description": "Create a Purchase Order in SAP MM against an approved supplier.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "sku":           {"type": "string"},
                "quantity":      {"type": "integer", "minimum": 1},
                "supplier_id":   {"type": "string", "description": "SAP Vendor ID (e.g. SUP-001)"},
                "delivery_date": {"type": "string", "format": "date"},
            },
            "required": ["sku", "quantity", "supplier_id"],
        },
    },
    {
        "name": "get_supplier_info",
        "description": "Retrieve vendor master data (name, lead times, payment terms) from SAP BP.",
        "inputSchema": {
            "type": "object",
            "properties": {"supplier_id": {"type": "string"}},
            "required": ["supplier_id"],
        },
    },
    {
        "name": "get_goods_movement",
        "description": "Retrieve recent goods receipts and goods issues from SAP MIGO.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "sku":  {"type": "string"},
                "days": {"type": "integer", "default": 7, "maximum": 90},
            },
            "required": ["sku"],
        },
    },
    {
        "name": "run_demand_forecast",
        "description": "Pull rolling demand forecast from SAP IBP (Integrated Business Planning).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "sku":          {"type": "string"},
                "horizon_days": {"type": "integer", "default": 90, "maximum": 365},
            },
            "required": ["sku"],
        },
    },
]


# ── Periodic: SAP stock-level monitor ────────────────────────────────────────
async def sap_periodic_stock_scan() -> None:
    """
    Periodically scan MOCK_STOCK for low-stock SKUs and emit a span per alert.
    In production this would poll SAP OData /A_MaterialDocumentItem.
    WSO2 Choreo will show these as background traces between tool calls.
    """
    tracer = trace.get_tracer(AgentID.SAP_ERP.value)
    low_stock_skus = [
        (sku, item) for sku, item in MOCK_STOCK.items()
        if item["stock"] < item["reorder"]
    ]

    with tracer.start_as_current_span(
        f"{AgentID.SAP_ERP.value}/stock_monitor",
        kind=trace.SpanKind.INTERNAL,
        attributes={
            "agent.id":         AgentID.SAP_ERP.value,
            "agent.operation":  "stock_monitor",
            "monitor.sku_count": len(MOCK_STOCK),
            "monitor.alerts":   len(low_stock_skus),
            "sap.plant":        "GBR1",
        },
    ) as span:
        if low_stock_skus:
            span.add_event(
                "low_stock_detected",
                attributes={
                    "skus":   str([s for s, _ in low_stock_skus]),
                    "count":  str(len(low_stock_skus)),
                },
            )
            log_event(AgentID.SAP_ERP, "SAP stock monitor: low-stock alert",
                      {"low_skus": len(low_stock_skus),
                       "skus": [s for s, _ in low_stock_skus]})
            increment("sap.stock_alerts", len(low_stock_skus))
        else:
            span.add_event("all_stock_levels_ok")
            log_event(AgentID.SAP_ERP, "SAP stock monitor: all levels OK",
                      {"skus_checked": len(MOCK_STOCK)})
        span.set_status(Status(StatusCode.OK))

        # Simulate a small drift in stock levels for demo realism
        for sku in MOCK_STOCK:
            MOCK_STOCK[sku]["stock"] = max(0, MOCK_STOCK[sku]["stock"] + random.randint(-3, 5))


server = HTTPAgentServer(
    agent_id=AgentID.SAP_ERP,
    dispatch_fn=sap_agent.handle_mcp_call,
    tools_meta=TOOLS,
    periodic_callbacks=[sap_periodic_stock_scan],
    heartbeat_interval=30,
)

if __name__ == "__main__":
    server.run()
