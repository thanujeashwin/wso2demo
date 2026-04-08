"""
Morrisons GCP Cloud Agent
══════════════════════════
Registered in WSO2 Agent Manager as: morrisons-gcp-cloud-agent

Capabilities:
  • run_bigquery_analytics     – Execute analytics on BigQuery (Morrisons data platform)
  • call_vertex_ai_prediction  – Run ML inference via Vertex AI
  • publish_pubsub_event       – Publish a real-time event to Pub/Sub
  • get_store_iot_data         – Retrieve IoT sensor data (fridges, self-checkouts)
  • run_document_ai            – Parse a supplier invoice via Document AI

Integration note for Morrisons:
  GCP is Morrisons' primary data-platform cloud:
    - BigQuery: 300TB+ retail analytics data lake
    - Vertex AI: ML models for demand forecasting, shelf analytics
    - Pub/Sub: Real-time event streaming (POS, IoT, supply chain events)
    - Cloud Run: Microservices + AI agent hosting
    - SAP S/4HANA runs on GCP Compute Engine (Morrisons migration 2023)
  WSO2 connects to GCP via Workload Identity Federation (no long-lived keys).
"""
from __future__ import annotations

import asyncio
import random
import uuid
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from shared.models import AgentID, AgentMessage, AgentResponse, AgentStatus
from shared.observability import log_event, trace_span, increment

# ── Demo data ─────────────────────────────────────────────────────────────────
MOCK_BQ_RESULTS: Dict[str, Any] = {
    "top_selling_skus": [
        {"sku": "SKU-MILK-003", "product": "4-Pint Whole Milk",    "units_sold": 148_200, "revenue_gbp": 192_660},
        {"sku": "SKU-BREA-007", "product": "White Thick Bread",    "units_sold": 131_500, "revenue_gbp":  98_625},
        {"sku": "SKU-BEEF-001", "product": "Best Beef Mince 500g", "units_sold":  92_400, "revenue_gbp": 369_600},
    ],
    "waste_by_category": [
        {"category": "Fresh Meat", "waste_pct": 2.1, "cost_gbp": 14_200},
        {"category": "Bakery",     "waste_pct": 4.8, "cost_gbp":  9_600},
        {"category": "Dairy",      "waste_pct": 1.3, "cost_gbp":  7_800},
    ],
}

MOCK_IOT_SENSORS: Dict[str, Dict[str, Any]] = {
    "STORE-001-FRIDGE-12": {
        "type": "refrigeration", "store": "STORE-001", "aisle": "Dairy",
        "temperature_c": 3.2, "humidity_pct": 78, "door_opens_today": 412,
        "alert": None, "last_maintenance": "2026-01-15",
    },
    "STORE-001-FRIDGE-07": {
        "type": "refrigeration", "store": "STORE-001", "aisle": "Fresh Meat",
        "temperature_c": 5.8, "humidity_pct": 71, "door_opens_today": 289,
        "alert": "TEMPERATURE_HIGH",  # 5.8°C > 5°C threshold
        "last_maintenance": "2025-11-20",
    },
    "STORE-001-SCO-03": {
        "type": "self_checkout", "store": "STORE-001", "aisle": "SCO Bay 3",
        "status": "OPERATIONAL", "transactions_today": 184,
        "avg_transaction_sec": 98, "alert": None,
    },
}


class GCPCloudAgent:
    """
    WSO2 Agent Manager – GCP Cloud Agent
    Runs on Cloud Run, exposes tools via MCP over SSE.
    Workload Identity used for GCP API auth – no service account keys.
    """

    agent_id = AgentID.GCP_CLOUD

    # ── Tool: run_bigquery_analytics ──────────────────────────────────────────
    async def run_bigquery_analytics(
        self,
        query_name: str,
        filters: Optional[Dict[str, Any]] = None,
        trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        [MCP Tool] Run a named analytics query on Google BigQuery.

        GCP Project: morrisons-data-platform
        Dataset: retail_analytics
        Tables: fact_sales, dim_product, dim_store, fact_waste, fact_inventory

        BigQuery Job ID format: morrisons-data-platform:EU.bqjob_{id}
        """
        with trace_span(self.agent_id, "run_bigquery_analytics", trace_id=trace_id,
                        attributes={"query_name": query_name}):
            log_event(self.agent_id, f"BigQuery: {query_name}", filters or {})
            await asyncio.sleep(0.6)   # BQ cold-start latency

            results = MOCK_BQ_RESULTS.get(query_name, [
                {"row": i, "value": random.randint(100, 10000)} for i in range(5)
            ])
            bq_job_id = f"morrisons-data-platform:EU.bqjob_{uuid.uuid4().hex[:16]}"
            increment("gcp.bigquery_jobs")
            return {
                "query_name":       query_name,
                "filters_applied":  filters or {},
                "results":          results,
                "rows_returned":    len(results) if isinstance(results, list) else 1,
                "bytes_processed":  f"{random.randint(100, 2000)} MB",
                "bq_job_id":        bq_job_id,
                "slot_ms":          random.randint(500, 8000),
                "data_freshness":   "2h",   # BigQuery scheduled refresh
                "project":          "morrisons-data-platform",
                "dataset":          "retail_analytics",
            }

    # ── Tool: call_vertex_ai_prediction ──────────────────────────────────────
    async def call_vertex_ai_prediction(
        self,
        model_name: str,
        instances: List[Dict[str, Any]],
        trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        [MCP Tool] Run ML prediction via Google Vertex AI.

        Deployed models:
          - morrisons-demand-forecast-v3    (AutoML Tables)
          - morrisons-shelf-vision-v2       (Custom – Vision API)
          - morrisons-churn-propensity-v1   (XGBoost on Vertex)
          - morrisons-price-elasticity-v1   (AutoML Tables)

        Vertex AI endpoint:
          POST https://europe-west2-aiplatform.googleapis.com/v1/projects/...
               /locations/europe-west2/endpoints/{endpoint_id}:predict
        """
        with trace_span(self.agent_id, "call_vertex_ai_prediction", trace_id=trace_id,
                        attributes={"model": model_name, "instances": len(instances)}):
            log_event(self.agent_id, f"Vertex AI prediction: {model_name}",
                      {"instances": len(instances)})
            await asyncio.sleep(0.35)

            predictions = []
            for inst in instances:
                if model_name == "morrisons-demand-forecast-v3":
                    predictions.append({
                        "sku": inst.get("sku", "UNKNOWN"),
                        "predicted_units_next_week": random.randint(800, 2400),
                        "confidence": round(random.uniform(0.78, 0.96), 3),
                    })
                elif model_name == "morrisons-churn-propensity-v1":
                    predictions.append({
                        "customer_id": inst.get("customer_id"),
                        "churn_probability": round(random.uniform(0.05, 0.45), 3),
                        "recommended_action": random.choice(["send_offer", "loyalty_bonus", "no_action"]),
                    })
                else:
                    predictions.append({"score": round(random.uniform(0.1, 0.99), 3)})

            increment("gcp.vertex_predictions")
            return {
                "model_name":     model_name,
                "predictions":    predictions,
                "model_version":  "3.0.0",
                "deploy_time_ms": random.randint(80, 250),
                "endpoint_id":    f"{random.randint(1000000000, 9999999999)}",
                "region":         "europe-west2",
            }

    # ── Tool: publish_pubsub_event ────────────────────────────────────────────
    async def publish_pubsub_event(
        self,
        topic: str,
        event_type: str,
        data: Dict[str, Any],
        trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        [MCP Tool] Publish a real-time event to a Google Pub/Sub topic.

        Topics:
          morrisons-stock-events        – Stock alerts, reorder triggers
          morrisons-pos-events          – Point-of-sale transactions
          morrisons-iot-events          – IoT sensor readings
          morrisons-agent-events        – Inter-agent event bus
        """
        with trace_span(self.agent_id, "publish_pubsub_event", trace_id=trace_id,
                        attributes={"topic": topic, "event_type": event_type}):
            log_event(self.agent_id, f"Pub/Sub: {topic} / {event_type}", data)
            await asyncio.sleep(0.05)   # Pub/Sub is very low latency
            message_id = str(random.randint(100000000000, 999999999999))
            increment("gcp.pubsub_published")
            return {
                "topic":            f"projects/morrisons-data-platform/topics/{topic}",
                "event_type":       event_type,
                "message_id":       message_id,
                "publish_time":     datetime.utcnow().isoformat() + "Z",
                "data_size_bytes":  len(str(data)),
                "status":           "PUBLISHED",
            }

    # ── Tool: get_store_iot_data ──────────────────────────────────────────────
    async def get_store_iot_data(
        self,
        sensor_id: str,
        trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        [MCP Tool] Retrieve real-time IoT sensor data from Morrisons stores.

        Data pipeline: Store sensor → Pub/Sub → Dataflow → BigTable → this API
        Sensors: refrigeration units, self-checkout bays, shelf weight sensors
        """
        with trace_span(self.agent_id, "get_store_iot_data", trace_id=trace_id,
                        attributes={"sensor_id": sensor_id}):
            await asyncio.sleep(0.08)
            sensor = MOCK_IOT_SENSORS.get(sensor_id)
            if not sensor:
                return {"error": f"Sensor {sensor_id} not found",
                        "available": list(MOCK_IOT_SENSORS.keys())}
            increment("gcp.iot_reads")
            return {
                **sensor,
                "sensor_id": sensor_id,
                "reading_time": datetime.utcnow().isoformat() + "Z",
                "data_source": "GCP Bigtable (real-time IoT store)",
            }

    # ── Tool: run_document_ai ─────────────────────────────────────────────────
    async def run_document_ai(
        self,
        document_type: str,
        document_content_b64: str = "DEMO_CONTENT",
        trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        [MCP Tool] Parse a supplier document (invoice / delivery note) via Google Document AI.

        Processor: morrisons-invoice-parser (eu processor)
        POST https://eu-documentai.googleapis.com/v1/projects/.../processors/...:process
        """
        with trace_span(self.agent_id, "run_document_ai", trace_id=trace_id,
                        attributes={"doc_type": document_type}):
            await asyncio.sleep(0.55)
            increment("gcp.documentai_calls")
            return {
                "document_type":  document_type,
                "processor":      "morrisons-invoice-parser-v3",
                "confidence":     round(random.uniform(0.87, 0.99), 3),
                "extracted_fields": {
                    "invoice_number": f"INV-{random.randint(10000, 99999)}",
                    "supplier_name":  "British Meat Supplies Ltd",
                    "total_amount":   round(random.uniform(1000, 25000), 2),
                    "currency":       "GBP",
                    "invoice_date":   date.today().isoformat(),
                    "po_reference":   f"PO-{random.randint(450000, 460000):06d}",
                },
                "status": "SUCCESS",
            }

    # ── MCP dispatch ──────────────────────────────────────────────────────────
    async def handle_mcp_call(
        self, tool_name: str, arguments: Dict[str, Any], trace_id: Optional[str] = None
    ) -> Dict[str, Any]:
        tools = {
            "run_bigquery_analytics":    self.run_bigquery_analytics,
            "call_vertex_ai_prediction": self.call_vertex_ai_prediction,
            "publish_pubsub_event":      self.publish_pubsub_event,
            "get_store_iot_data":        self.get_store_iot_data,
            "run_document_ai":           self.run_document_ai,
        }
        if tool_name not in tools:
            return {"error": f"Unknown tool: {tool_name}"}
        return await tools[tool_name](**arguments, trace_id=trace_id)

    async def process_message(self, msg: AgentMessage) -> AgentResponse:
        tid = msg.trace_context.get("trace_id", str(uuid.uuid4()).replace("-", ""))
        log_event(self.agent_id, f"Received task from {msg.from_agent.value}", msg.payload)
        try:
            result = await self.handle_mcp_call(
                msg.payload.get("tool"), msg.payload.get("args", {}), trace_id=tid
            )
            return AgentResponse(
                message_id=str(uuid.uuid4()), correlation_id=msg.correlation_id,
                from_agent=self.agent_id, status=AgentStatus.COMPLETED, data=result,
            )
        except Exception as exc:
            return AgentResponse(
                message_id=str(uuid.uuid4()), correlation_id=msg.correlation_id,
                from_agent=self.agent_id, status=AgentStatus.FAILED, data={}, error=str(exc),
            )


gcp_agent = GCPCloudAgent()
