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

import random
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from shared.http_server import HTTPAgentServer
from shared.models import AgentID
from shared.observability import log_event, increment
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


# ── Demo IoT sensor state ─────────────────────────────────────────────────────
_IOT_SENSORS = {
    "STORE-001-FRIDGE-12": {"type": "fridge", "temp_c": 3.2,  "ok": True},
    "STORE-001-FRIDGE-07": {"type": "fridge", "temp_c": 4.1,  "ok": True},
    "STORE-001-SCO-03":    {"type": "sco",    "queue": 2,      "ok": True},
    "STORE-002-FRIDGE-05": {"type": "fridge", "temp_c": 6.8,  "ok": False},  # warm
    "STORE-002-SCO-01":    {"type": "sco",    "queue": 7,      "ok": True},
}
_BIGQUERY_SLOTS = {"active": 42}


# ── Periodic: GCP IoT sensor + BigQuery health poll ───────────────────────────
async def gcp_periodic_platform_poll() -> None:
    """
    Periodically poll IoT sensor readings and BigQuery slot utilisation.
    Emits a span per sensor anomaly to WSO2 Choreo Observability.
    In production this polls GCP IoT Core MQTT bridge and BigQuery Admin API.
    """
    tracer = trace.get_tracer(AgentID.GCP_CLOUD.value)

    with tracer.start_as_current_span(
        f"{AgentID.GCP_CLOUD.value}/platform_poll",
        kind=trace.SpanKind.INTERNAL,
        attributes={
            "agent.id":         AgentID.GCP_CLOUD.value,
            "agent.operation":  "platform_poll",
            "gcp.project":      os.environ.get("GCP_PROJECT", "morrisons-data-platform"),
            "gcp.region":       os.environ.get("GCP_REGION", "europe-west2"),
            "iot.sensor_count": len(_IOT_SENSORS),
        },
    ) as span:
        alerts = []

        for sensor_id, sensor in _IOT_SENSORS.items():
            # Simulate small random drift in readings
            if sensor["type"] == "fridge":
                sensor["temp_c"] = round(sensor["temp_c"] + random.uniform(-0.3, 0.4), 1)
                sensor["ok"] = sensor["temp_c"] <= 5.0
                span.add_event(
                    "iot_fridge_reading",
                    attributes={
                        "sensor_id": sensor_id,
                        "temp_c":    str(sensor["temp_c"]),
                        "status":    "OK" if sensor["ok"] else "ALERT",
                    },
                )
                if not sensor["ok"]:
                    alerts.append({"sensor": sensor_id, "temp": sensor["temp_c"]})
            else:
                sensor["queue"] = random.randint(0, 10)
                span.add_event(
                    "iot_sco_queue",
                    attributes={
                        "sensor_id":    sensor_id,
                        "queue_depth":  str(sensor["queue"]),
                    },
                )

        # BigQuery slot utilisation
        _BIGQUERY_SLOTS["active"] = random.randint(20, 80)
        span.add_event(
            "bigquery_slots",
            attributes={"active_slots": str(_BIGQUERY_SLOTS["active"])},
        )

        if alerts:
            span.add_event(
                "fridge_temperature_alerts",
                attributes={"alert_count": str(len(alerts)),
                            "sensors": str([a["sensor"] for a in alerts])},
            )
            log_event(AgentID.GCP_CLOUD, "GCP IoT poll: fridge temperature alerts",
                      {"alerts": alerts})
            increment("gcp.iot_alerts", len(alerts))
        else:
            log_event(AgentID.GCP_CLOUD, "GCP platform poll: all sensors OK",
                      {"sensors": len(_IOT_SENSORS),
                       "bq_slots": _BIGQUERY_SLOTS["active"]})

        span.set_attribute("gcp.iot_alerts", len(alerts))
        span.set_attribute("gcp.bq_active_slots", _BIGQUERY_SLOTS["active"])
        span.set_status(Status(StatusCode.OK))


server = HTTPAgentServer(
    agent_id=AgentID.GCP_CLOUD,
    dispatch_fn=gcp_agent.handle_mcp_call,
    tools_meta=TOOLS,
    periodic_callbacks=[gcp_periodic_platform_poll],
    heartbeat_interval=30,
)

if __name__ == "__main__":
    server.run()
