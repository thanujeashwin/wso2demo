"""
GCP Cloud Agent – WSO2 Agent Manager Entry Point
─────────────────────────────────────────────────
WSO2 Start Command:  python main.py
WSO2 Port:           8005
WSO2 OpenAPI Path:   /openapi.json
WSO2 Base Path:      /
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from shared.http_server import HTTPAgentServer
from shared.models import AgentID
from agents.gcp_agent.agent import gcp_agent

TOOLS = [
    {
        "name": "run_bigquery_analytics",
        "description": "Execute a named analytics query on Google BigQuery (Morrisons data platform, 300TB+ retail data lake).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query_name": {"type": "string",
                               "enum": ["top_selling_skus", "waste_by_category"],
                               "description": "Pre-defined query name"},
                "filters":    {"type": "object", "description": "Optional filter parameters"},
            },
            "required": ["query_name"],
        },
    },
    {
        "name": "call_vertex_ai_prediction",
        "description": "Run ML inference via Google Vertex AI. Models: demand-forecast-v3, churn-propensity-v1, shelf-vision-v2, price-elasticity-v1.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "model_name": {"type": "string",
                               "enum": ["morrisons-demand-forecast-v3",
                                        "morrisons-churn-propensity-v1",
                                        "morrisons-shelf-vision-v2",
                                        "morrisons-price-elasticity-v1"]},
                "instances":  {"type": "array", "items": {"type": "object"},
                               "description": "List of prediction input objects"},
            },
            "required": ["model_name", "instances"],
        },
    },
    {
        "name": "publish_pubsub_event",
        "description": "Publish a real-time event to a Google Pub/Sub topic for downstream processing.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "topic":      {"type": "string",
                               "enum": ["morrisons-stock-events", "morrisons-pos-events",
                                        "morrisons-iot-events", "morrisons-agent-events"]},
                "event_type": {"type": "string"},
                "data":       {"type": "object"},
            },
            "required": ["topic", "event_type", "data"],
        },
    },
    {
        "name": "get_store_iot_data",
        "description": "Retrieve real-time IoT sensor readings from Morrisons stores (fridges, self-checkouts, shelf weight sensors).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "sensor_id": {"type": "string",
                              "description": "Sensor ID (e.g. STORE-001-FRIDGE-12, STORE-001-SCO-03)"},
            },
            "required": ["sensor_id"],
        },
    },
    {
        "name": "run_document_ai",
        "description": "Parse a supplier invoice or delivery note using Google Document AI.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "document_type":        {"type": "string",
                                         "enum": ["supplier_invoice", "delivery_note", "grn"]},
                "document_content_b64": {"type": "string",
                                         "description": "Base64-encoded document content"},
            },
            "required": ["document_type"],
        },
    },
]

server = HTTPAgentServer(
    agent_id=AgentID.GCP_CLOUD,
    dispatch_fn=gcp_agent.handle_mcp_call,
    tools_meta=TOOLS,
)

if __name__ == "__main__":
    server.run()
