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

from shared.http_server import HTTPAgentServer
from shared.models import AgentID
from agents.sap_agent.agent import sap_agent

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

server = HTTPAgentServer(
    agent_id=AgentID.SAP_ERP,
    dispatch_fn=sap_agent.handle_mcp_call,
    tools_meta=TOOLS,
)

if __name__ == "__main__":
    server.run()
