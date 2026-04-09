"""Morrisons GCP Cloud Agent – LangChain Tools"""
import random
from datetime import date
from langchain_core.tools import tool

IOT_SENSORS = {
    "STORE-001-FRIDGE-12": {"type": "fridge",  "temp_c": 3.2,  "store": "STORE-001"},
    "STORE-001-FRIDGE-07": {"type": "fridge",  "temp_c": 4.1,  "store": "STORE-001"},
    "STORE-001-SCO-03":    {"type": "sco",     "queue":  2,    "store": "STORE-001"},
    "STORE-002-FRIDGE-05": {"type": "fridge",  "temp_c": 6.8,  "store": "STORE-002"},
    "STORE-002-SCO-01":    {"type": "sco",     "queue":  7,    "store": "STORE-002"},
}

VERTEX_MODELS = [
    "morrisons-demand-forecast-v3",
    "morrisons-churn-propensity-v1",
    "morrisons-shelf-vision-v2",
    "morrisons-price-elasticity-v1",
]

PUBSUB_TOPICS = [
    "morrisons-stock-events",
    "morrisons-pos-events",
    "morrisons-iot-events",
    "morrisons-agent-events",
]


@tool
def run_bigquery_analytics(query_name: str, filters: str = "{}") -> str:
    """
    Execute a named analytics query on Morrisons' Google BigQuery data lake (300TB+).
    Returns aggregated results from the Morrisons retail data platform.

    Args:
        query_name: Pre-defined query – top_selling_skus or waste_by_category
        filters: Optional JSON string of filter parameters, e.g. '{"store_id": "STORE-001", "days": 7}'
    """
    if query_name == "top_selling_skus":
        skus = [
            ("SKU-MILK-003", "Morrisons Whole Milk 4 Pints",     random.randint(800, 1200)),
            ("SKU-BREA-007", "Morrisons White Thick Bread",       random.randint(600, 950)),
            ("SKU-BEEF-001", "Morrisons Best Beef Mince 500g",    random.randint(400, 700)),
            ("SKU-CHIC-002", "Morrisons Chicken Breast 500g",     random.randint(350, 600)),
            ("SKU-SALM-004", "Morrisons Scottish Salmon 240g",    random.randint(200, 400)),
        ]
        rows = "\n".join(f"  {i+1}. {s[0]}: {s[1]} – {s[2]:,} units" for i, s in enumerate(skus))
        return (
            f"BigQuery – Top Selling SKUs (last 7 days)\n"
            f"Dataset: morrisons-data-platform.retail.sales\n"
            f"Rows Processed: {random.randint(2, 8)}M | Query Time: {random.randint(1,5)}s\n"
            f"{rows}"
        )
    elif query_name == "waste_by_category":
        cats = [("Fresh Meat", 3.2), ("Bakery", 5.1), ("Fish", 4.8), ("Dairy", 2.9), ("Produce", 6.3)]
        rows = "\n".join(f"  {c[0]}: {c[1]+random.uniform(-0.5,0.5):.1f}% waste rate" for c in cats)
        return (
            f"BigQuery – Waste by Category (MTD)\n"
            f"Dataset: morrisons-data-platform.retail.waste\n{rows}"
        )
    return f"Query '{query_name}' not found. Available: top_selling_skus, waste_by_category"


@tool
def call_vertex_ai_prediction(model_name: str, sku: str = "",
                               customer_id: str = "") -> str:
    """
    Run ML inference via Google Vertex AI on Morrisons' models.

    Args:
        model_name: Vertex AI model – morrisons-demand-forecast-v3, morrisons-churn-propensity-v1,
                    morrisons-shelf-vision-v2, morrisons-price-elasticity-v1
        sku: Product SKU for demand/price models (e.g. SKU-BEEF-001)
        customer_id: Customer ID for churn model (e.g. CUST-000303)
    """
    if model_name not in VERTEX_MODELS:
        return f"Model '{model_name}' not found. Available: {', '.join(VERTEX_MODELS)}"

    if "demand-forecast" in model_name:
        qty = random.randint(120, 300)
        conf = round(random.uniform(0.80, 0.97), 2)
        return (
            f"Vertex AI – Demand Forecast\n"
            f"Model: {model_name} | SKU: {sku or 'N/A'}\n"
            f"7-Day Forecast: {qty} units | Confidence: {conf:.0%}\n"
            f"Recommendation: {'Increase order' if qty > 200 else 'Standard order'}"
        )
    elif "churn-propensity" in model_name:
        prob = round(random.uniform(0.05, 0.65), 2)
        risk = "HIGH" if prob > 0.5 else ("MEDIUM" if prob > 0.25 else "LOW")
        return (
            f"Vertex AI – Churn Propensity\n"
            f"Model: {model_name} | Customer: {customer_id or 'N/A'}\n"
            f"Churn Probability: {prob:.0%} | Risk: {risk}\n"
            f"Recommended Action: {'Retention offer immediately' if risk=='HIGH' else 'Monitor'}"
        )
    elif "shelf-vision" in model_name:
        gaps = random.randint(0, 5)
        return (
            f"Vertex AI – Shelf Vision Analysis\n"
            f"Model: {model_name}\n"
            f"Shelf Gaps Detected: {gaps}\n"
            f"Planogram Compliance: {random.randint(88, 99)}%"
        )
    else:
        elasticity = round(random.uniform(-1.8, -0.3), 2)
        return (
            f"Vertex AI – Price Elasticity\n"
            f"Model: {model_name} | SKU: {sku or 'N/A'}\n"
            f"Price Elasticity: {elasticity}\n"
            f"Optimal Price Index: {round(random.uniform(0.95, 1.05), 3)}"
        )


@tool
def publish_pubsub_event(topic: str, event_type: str, data: str) -> str:
    """
    Publish a real-time event to a Morrisons Google Pub/Sub topic.

    Args:
        topic: Pub/Sub topic – morrisons-stock-events, morrisons-pos-events,
               morrisons-iot-events, morrisons-agent-events
        event_type: Event type string, e.g. LOW_STOCK_ALERT, PO_CREATED, SENSOR_ALARM
        data: JSON string of event data
    """
    if topic not in PUBSUB_TOPICS:
        return f"Topic '{topic}' not found. Available: {', '.join(PUBSUB_TOPICS)}"
    msg_id = f"msg-{random.randint(1000000000, 9999999999)}"
    return (
        f"Google Pub/Sub – Event Published ✓\n"
        f"Topic: {topic}\n"
        f"Event Type: {event_type}\n"
        f"Message ID: {msg_id}\n"
        f"Project: morrisons-data-platform | Region: europe-west2"
    )


@tool
def get_store_iot_data(sensor_id: str) -> str:
    """
    Retrieve real-time IoT sensor readings from Morrisons stores via Google Cloud IoT.
    Sensors include fridges, self-checkouts, and shelf weight sensors.

    Args:
        sensor_id: Sensor ID, e.g. STORE-001-FRIDGE-12, STORE-001-SCO-03,
                   STORE-002-FRIDGE-05, STORE-002-SCO-01
    """
    if sensor_id not in IOT_SENSORS:
        return (
            f"Sensor '{sensor_id}' not found. "
            f"Available: {', '.join(IOT_SENSORS)}"
        )
    s = IOT_SENSORS[sensor_id]
    if s["type"] == "fridge":
        temp = round(s["temp_c"] + random.uniform(-0.3, 0.3), 1)
        ok = temp <= 5.0
        return (
            f"GCP IoT – Fridge Sensor\n"
            f"Sensor: {sensor_id} | Store: {s['store']}\n"
            f"Temperature: {temp}°C | Status: {'✓ OK' if ok else '⚠ ALERT – exceeds 5°C limit'}\n"
            f"Last Reading: {random.randint(1, 5)} minutes ago"
        )
    else:
        queue = s["queue"] + random.randint(-1, 2)
        return (
            f"GCP IoT – Self-Checkout Sensor\n"
            f"Sensor: {sensor_id} | Store: {s['store']}\n"
            f"Queue Depth: {max(0, queue)} customers | Status: {'⚠ Busy' if queue > 5 else '✓ Normal'}\n"
            f"Avg Transaction Time: {random.randint(45, 120)}s"
        )


@tool
def run_document_ai(document_type: str, document_content_b64: str = "") -> str:
    """
    Parse a supplier invoice, delivery note, or GRN using Google Document AI.
    Extracts structured data from scanned documents.

    Args:
        document_type: Document type – supplier_invoice, delivery_note, or grn
        document_content_b64: Base64-encoded document content (optional for demo)
    """
    valid = ["supplier_invoice", "delivery_note", "grn"]
    if document_type not in valid:
        return f"Document type '{document_type}' not valid. Use: {', '.join(valid)}"
    proc_id = f"proc-{random.randint(100000, 999999)}"
    confidence = round(random.uniform(0.91, 0.99), 2)
    if document_type == "supplier_invoice":
        return (
            f"Google Document AI – Invoice Parsed ✓\n"
            f"Processor: {proc_id} | Confidence: {confidence:.0%}\n"
            f"Invoice Number: INV-{random.randint(100000,999999)}\n"
            f"Supplier: SUP-{random.randint(1,4):03d}\n"
            f"Amount: £{random.randint(500,15000):,}.00 | Date: {date.today().isoformat()}"
        )
    elif document_type == "delivery_note":
        return (
            f"Google Document AI – Delivery Note Parsed ✓\n"
            f"Processor: {proc_id} | Confidence: {confidence:.0%}\n"
            f"Delivery Note: DN-{random.randint(10000,99999)}\n"
            f"Items Detected: {random.randint(3,15)} line items"
        )
    else:
        return (
            f"Google Document AI – GRN Parsed ✓\n"
            f"Processor: {proc_id} | Confidence: {confidence:.0%}\n"
            f"GRN Number: GRN-{random.randint(10000,99999)}\n"
            f"Matched to PO: PO-{random.randint(4500,4600):06d}"
        )


TOOLS = [
    run_bigquery_analytics,
    call_vertex_ai_prediction,
    publish_pubsub_event,
    get_store_iot_data,
    run_document_ai,
]
