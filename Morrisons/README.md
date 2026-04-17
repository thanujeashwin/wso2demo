# Morrisons AI Agent Demo — WSO2 Agent Manager

A suite of ten AI agents built for **WSO2 Agent Manager**, demonstrating a multi-agent architecture for Morrisons supermarkets (UK). The agents simulate a real enterprise AI platform spanning SAP ERP, Oracle Finance, Salesforce CRM, AWS, GCP, and a customer-facing shopping assistant — emitting full observability traces via Traceloop on every request.

When a customer places an order the **Customer Agent** fires asynchronous notifications to the **Inventory Agent** and **Warehouse Agent** (fire-and-forget — the customer never waits). The Inventory Agent in turn notifies the **Supplier Agent** if a product drops below its reorder threshold. All three inter-agent calls are visible as OTel spans in the traces view.

---

## Architecture

```
  Customer (Browser)                    Staff / Integrations
        │                                        │
        ▼                                        ▼
┌─────────────────────┐           ┌──────────────────────────┐
│  Customer Agent     │           │       Orchestrator        │
│  POST /chat  :8000  │           │  POST /chat  :8000        │
│  Custom ReAct + LLM │           │  LangGraph ReAct          │
└──────────┬──────────┘           └──┬────┬────┬────┬──┬─────┘
           │ (fire & forget)          │    │    │    │  │
     ┌─────┴──────┐                  │    │    │    │  │
     ▼            ▼           ┌──────┘    │    │    │  └────────────┐
┌─────────┐ ┌──────────┐      │   ┌───────┘    └──────────┐        │
│Inventory│ │Warehouse │      ▼   ▼                       ▼        ▼
│  Agent  │ │  Agent   │ ┌────────────┐ ┌────────────┐ ┌──────┐ ┌──────┐
│  :8000  │ │  :8000   │ │  SAP ERP   │ │ Oracle ERP │ │ AWS  │ │ GCP  │
└────┬────┘ └──────────┘ │  :8001     │ │  :8002     │ │:8004 │ │:8005 │
     │ (fire & forget)   └────────────┘ └────────────┘ └──────┘ └──────┘
     ▼                              ┌────────────┐
┌──────────┐                        │ Salesforce │
│ Supplier │                        │   :8003    │
│  Agent   │                        └────────────┘
│  :8000   │
└──────────┘
                    ▼
     ┌──────────────────────────────────┐
     │       WSO2 Agent Manager         │
     │  Traceloop / OTLP tracing for    │
     │  all agents — LangGraph + custom │
     │  ReAct spans unified in one UI   │
     └──────────────────────────────────┘
```

Each agent exposes a **FastAPI `/chat` endpoint**. The five back-office agents use a **LangGraph ReAct graph**. The customer, inventory, warehouse and supplier agents use a **custom ReAct loop** (no LangGraph) — demonstrating that WSO2 Agent Manager is framework-agnostic.

---

## Inter-Agent Order Flow

When a customer places an order the following sequence runs automatically:

```
Customer Agent  ──[place_order]──► order confirmed ──► notify_agents_of_order()
                                                              │
                              ┌───────────────────────────────┤
                              │  fire-and-forget threads       │
                              ▼                               ▼
                     Inventory Agent               Warehouse Agent
                     reserve_stock()              create_fulfilment_task()
                     check_inventory_levels()     assign_picker()
                              │
                     (if stock < reorder level)
                              ▼
                     Supplier Agent
                     get_supplier_info()
                     raise_purchase_order()
```

The customer agent returns its response immediately without waiting for the downstream agents. OTel spans are emitted synchronously before each thread is launched so the dispatch intent is always visible in traces.

**Environment variables required on the Customer Agent:**

| Variable | Default |
|---|---|
| `INVENTORY_AGENT_URL` | `http://inventory-agent:8000` |
| `WAREHOUSE_AGENT_URL` | `http://warehouse-agent:8000` |

**Environment variable required on the Inventory Agent:**

| Variable | Default |
|---|---|
| `SUPPLIER_AGENT_URL` | `http://supplier-agent:8000` |

---

## Agents

### Orchestrator (`orchestrator/`) — Port 8000

The master agent. Routes incoming requests to the right specialist sub-agent using keyword matching and synthesises the responses.

**Routing logic:**
| Keywords in message | Delegates to |
|---|---|
| sap, stock, inventory, purchase order, goods, reorder | `ask_sap_erp_agent` |
| oracle, budget, finance, invoice, approval, cost centre | `ask_oracle_erp_agent` |
| salesforce, customer, loyalty, crm, offer, case | `ask_salesforce_agent` |
| aws, lambda, s3, dynamodb, sns | `ask_aws_agent` |
| gcp, bigquery, vertex, pubsub, iot, forecast | `ask_gcp_agent` |

---

### SAP ERP Agent (`sap_agent/`) — Port 8001

Simulates SAP S/4HANA integration covering Materials Management (MM), Integrated Business Planning (IBP), and Vendor Master (BP).

**Tools:**
| Tool | Description |
|---|---|
| `check_stock_level` | Stock quantity and reorder status for a SKU |
| `raise_purchase_order` | Creates a SAP PO document against an approved supplier |
| `get_supplier_info` | Vendor master data: lead times, payment terms, contract ref |
| `get_goods_movement` | SAP MIGO goods receipts and issues over N days |
| `run_demand_forecast` | SAP IBP rolling 90-day demand forecast |

**Demo SKUs:** `SKU-BEEF-001`, `SKU-MILK-003`, `SKU-BREA-007`, `SKU-CHIC-002`, `SKU-SALM-004`
**Demo Suppliers:** `SUP-001` – `SUP-004`

---

### Oracle ERP Agent (`oracle_agent/`) — Port 8002

Simulates Oracle Fusion Cloud ERP covering General Ledger, Accounts Payable, Procurement, and Budgetary Control.

**Tools:**
| Tool | Description |
|---|---|
| `get_budget_availability` | Available budget for a cost centre and fiscal period |
| `approve_purchase_order` | Oracle AME approval workflow for a PO |
| `get_cost_centre_report` | Actual vs budget spend for a cost centre |
| `get_invoice_status` | Accounts payable invoice status and payment details |
| `create_journal_entry` | Posts a GL journal entry (debit/credit) |

**Demo cost centres:** `CC-PRODUCE-01`, `CC-MEAT-02`, `CC-DAIRY-03`, `CC-BAKERY-04`

---

### Salesforce Agent (`salesforce_agent/`) — Port 8003

Simulates Salesforce Sales & Service Cloud for customer loyalty, personalised marketing, supplier account management, and service case handling.

**Tools:**
| Tool | Description |
|---|---|
| `get_customer_profile` | Customer contact, loyalty tier, and purchase history |
| `generate_personalised_offer` | AI-generated promotional offer for a customer |
| `update_customer_segment` | Updates customer loyalty tier in Salesforce |
| `get_supplier_account` | Supplier account health and relationship data |
| `log_service_case` | Creates a Salesforce Service Cloud case |

**Loyalty tiers:** Bronze (0–499 pts), Silver (500–1999 pts), Gold (2000+ pts), Platinum (8000+ pts)

**Demo customers:** `CUST-100142` (Sarah Thompson – Gold), `CUST-100256` (James Patel – Silver), `CUST-100389` (Emma Clarke – Platinum), `CUST-100471` (David O'Brien – Bronze)

---

### AWS Agent (`aws_agent/`) — Port 8004

Simulates AWS cloud services used for analytics, serverless workflows, notifications, and session management.

**Tools:**
| Tool | Description |
|---|---|
| `analyse_sales_trends` | Sales performance analytics via Amazon Redshift/Athena |
| `trigger_lambda_workflow` | Invokes a serverless reorder or pricing Lambda |
| `get_s3_report` | Fetches a named report from the S3 data lake |
| `send_sns_notification` | Publishes an operational alert to an SNS topic |
| `query_dynamodb_session` | Retrieves a customer session record from DynamoDB |

---

### GCP Agent (`gcp_agent/`) — Port 8005

Simulates Google Cloud Platform services for analytics, ML predictions, event streaming, IoT monitoring, and document processing.

**Tools:**
| Tool | Description |
|---|---|
| `run_bigquery_analytics` | Executes a named analytics query against BigQuery |
| `call_vertex_ai_prediction` | Calls a Vertex AI model (demand forecast, recommender) |
| `publish_pubsub_event` | Publishes a reorder or pricing event to Pub/Sub |
| `get_store_iot_data` | Reads refrigeration/temperature sensor data via IoT Core |
| `run_document_ai` | Processes a supplier invoice via Google Document AI |

**Vertex AI models:** `demand-forecast-v2`, `product-recommender-v1`, `price-optimiser-v3`

---

### Customer Agent (`customer_agent/`) — Port 8000

Customer-facing shopping assistant powered by **Gemini 2.5 Flash** via the WSO2 AI Gateway. Uses a custom ReAct loop (no LangGraph). On a successful order placement it fires asynchronous notifications to the Inventory Agent and Warehouse Agent.

**Tools:**
| Tool | Description |
|---|---|
| `browse_products` | List products, optionally filtered by category |
| `check_stock` | Real-time stock level for a product |
| `place_order` | Place an order and trigger downstream notifications |
| `track_order` | Current status and ETA for an existing order |
| `get_customer_profile` | Loyalty tier and order history for a customer |

**Demo customers:** `CUST-5001` – `CUST-5004`
**Demo products:** `PROD-001` – `PROD-007` across 7 categories

**Example `/chat` request:**
```json
{
  "message": "I want to order 2 pints of milk and check when my last order arrives",
  "session_id": "demo-session-1",
  "context": { "customer_id": "CUST-5001" }
}
```

**Example response:**
```json
{
  "response": "Order placed successfully!\n\nOrder ID: ORD-9004\nCustomer: Emma Johnson\n\nItems:\n  • Morrisons British Whole Milk 4pt × 2  =  £3.30\n\nTotal: £3.30\nEstimated delivery: Within 2–4 hours",
  "session_id": "demo-session-1",
  "agent": "customer_agent"
}
```

---

### Inventory Agent (`inventory_agent/`) — Port 8000

Triggered by the Customer Agent when an order is placed. Reserves stock against the order, checks current inventory levels, and fires a notification to the Supplier Agent if any product falls below its reorder threshold.

**Tools:**
| Tool | Description |
|---|---|
| `reserve_stock` | Reserve stock units against an order ID |
| `check_inventory_levels` | Current stock vs reorder threshold for a product |
| `release_reservation` | Release a reservation (e.g. on order cancellation) |

**Demo products:** `PROD-001` – `PROD-007`

**Example `/chat` request:**
```json
{
  "message": "Reserve stock for order ORD-9004. Items: [{\"product_id\": \"PROD-001\", \"quantity\": 2}]",
  "session_id": "notify-ORD-9004",
  "context": {}
}
```

---

### Warehouse Agent (`warehouse_agent/`) — Port 8000

Triggered by the Customer Agent when an order is placed. Creates a fulfilment task and assigns it to an available picker.

**Tools:**
| Tool | Description |
|---|---|
| `create_fulfilment_task` | Create a picking task for an order |
| `assign_picker` | Assign an available warehouse picker to a task |
| `update_dispatch_status` | Update the dispatch status of a fulfilment task |

**Demo pickers:** `PICKER-01` – `PICKER-04`

**Example `/chat` request:**
```json
{
  "message": "Create fulfilment task for order ORD-9004. Customer: Emma Johnson.",
  "session_id": "notify-ORD-9004",
  "context": {}
}
```

---

### Supplier Agent (`supplier_agent/`) — Port 8000

Triggered by the Inventory Agent when a product drops below its reorder threshold. Looks up the preferred supplier and raises a purchase order.

**Tools:**
| Tool | Description |
|---|---|
| `get_supplier_info` | Supplier contact, lead time, and MOQ details |
| `raise_purchase_order` | Raise a purchase order with a supplier |

**Demo suppliers:** `SUP-101` – `SUP-104`

**Example `/chat` request:**
```json
{
  "message": "Stock low for PROD-001. Raise a purchase order with the preferred supplier.",
  "session_id": "reorder-PROD-001",
  "context": {}
}
```

---

## WSO2 Agent Manager Configuration

Each agent is created via **Create a Platform-Hosted Agent** in Agent Manager.

> **Deploy order:** deploy the four downstream agents first (inventory, warehouse, supplier, then the five back-office agents), then the Customer Agent and Orchestrator last. This ensures all agent URLs are available when the orchestrating agents start.

> **Port:** add `PORT` = `8000` as an environment variable for every agent. This tells the agent which port to bind inside its container.

---

### Agent 1 — SAP ERP Agent

**Agent Details**

| Field | Value |
|---|---|
| Name | `Morrisons SAP ERP Agent` |
| Description | `SAP S/4HANA agent for Morrisons — stock levels, purchase orders, supplier data, and demand forecasting` |

**Repository Details**

| Field | Value |
|---|---|
| GitHub Repository | `https://github.com/thanujeashwin/wso2demo` |
| Branch | `main` |
| Project Path | `Morrisons/sap_agent` |

**Build Details**

| Field | Value |
|---|---|
| Language | `Python` |
| Start Command | `python main.py` |
| Language Version | `3.11` |
| Enable auto instrumentation | ✅ checked |

**Agent Type:** `Chat Agent`

**Environment Variables:**

| Key | Value | Secret |
|---|---|---|
| `PORT` | `8000` | ☐ |

---

### Agent 2 — Oracle ERP Agent

**Agent Details**

| Field | Value |
|---|---|
| Name | `Morrisons Oracle ERP Agent` |
| Description | `Oracle Fusion Cloud ERP agent for Morrisons — budgets, PO approvals, invoices, cost centres, and journal entries` |

**Repository Details**

| Field | Value |
|---|---|
| GitHub Repository | `https://github.com/thanujeashwin/wso2demo` |
| Branch | `main` |
| Project Path | `Morrisons/oracle_agent` |

**Build Details**

| Field | Value |
|---|---|
| Language | `Python` |
| Start Command | `python main.py` |
| Language Version | `3.11` |
| Enable auto instrumentation | ✅ checked |

**Agent Type:** `Chat Agent`

**Environment Variables:**

| Key | Value | Secret |
|---|---|---|
| `PORT` | `8000` | ☐ |

---

### Agent 3 — Salesforce CRM Agent

**Agent Details**

| Field | Value |
|---|---|
| Name | `Morrisons Salesforce CRM Agent` |
| Description | `Salesforce Sales & Service Cloud agent for Morrisons — customer loyalty, personalised offers, supplier accounts, and service cases` |

**Repository Details**

| Field | Value |
|---|---|
| GitHub Repository | `https://github.com/thanujeashwin/wso2demo` |
| Branch | `main` |
| Project Path | `Morrisons/salesforce_agent` |

**Build Details**

| Field | Value |
|---|---|
| Language | `Python` |
| Start Command | `python main.py` |
| Language Version | `3.11` |
| Enable auto instrumentation | ✅ checked |

**Agent Type:** `Chat Agent`

**Environment Variables:**

| Key | Value | Secret |
|---|---|---|
| `PORT` | `8000` | ☐ |

---

### Agent 4 — AWS Cloud Agent

**Agent Details**

| Field | Value |
|---|---|
| Name | `Morrisons AWS Cloud Agent` |
| Description | `AWS agent for Morrisons — sales analytics, Lambda workflows, S3 reports, SNS notifications, and DynamoDB session data` |

**Repository Details**

| Field | Value |
|---|---|
| GitHub Repository | `https://github.com/thanujeashwin/wso2demo` |
| Branch | `main` |
| Project Path | `Morrisons/aws_agent` |

**Build Details**

| Field | Value |
|---|---|
| Language | `Python` |
| Start Command | `python main.py` |
| Language Version | `3.11` |
| Enable auto instrumentation | ✅ checked |

**Agent Type:** `Chat Agent`

**Environment Variables:**

| Key | Value | Secret |
|---|---|---|
| `PORT` | `8000` | ☐ |

---

### Agent 5 — GCP Cloud Agent

**Agent Details**

| Field | Value |
|---|---|
| Name | `Morrisons GCP Cloud Agent` |
| Description | `GCP agent for Morrisons — BigQuery analytics, Vertex AI predictions, Pub/Sub events, IoT sensor data, and Document AI` |

**Repository Details**

| Field | Value |
|---|---|
| GitHub Repository | `https://github.com/thanujeashwin/wso2demo` |
| Branch | `main` |
| Project Path | `Morrisons/gcp_agent` |

**Build Details**

| Field | Value |
|---|---|
| Language | `Python` |
| Start Command | `python main.py` |
| Language Version | `3.11` |
| Enable auto instrumentation | ✅ checked |

**Agent Type:** `Chat Agent`

**Environment Variables:**

| Key | Value | Secret |
|---|---|---|
| `PORT` | `8000` | ☐ |

---

### Agent 6 — Inventory Agent

**Agent Details**

| Field | Value |
|---|---|
| Name | `Morrisons Inventory Agent` |
| Description | `Inventory management agent — reserves stock on order placement, monitors levels, and triggers supplier reorders` |

**Repository Details**

| Field | Value |
|---|---|
| GitHub Repository | `https://github.com/thanujeashwin/wso2demo` |
| Branch | `main` |
| Project Path | `Morrisons/inventory_agent` |

**Build Details**

| Field | Value |
|---|---|
| Language | `Python` |
| Start Command | `python main.py` |
| Language Version | `3.11` |
| Enable auto instrumentation | ✅ checked |

**Agent Type:** `Chat Agent`

**Environment Variables:**

| Key | Value | Secret |
|---|---|---|
| `PORT` | `8000` | ☐ |
| `SUPPLIER_AGENT_URL` | `http://<supplier-agent-host>:<port>` | ☐ |

---

### Agent 7 — Warehouse Agent

**Agent Details**

| Field | Value |
|---|---|
| Name | `Morrisons Warehouse Agent` |
| Description | `Warehouse fulfilment agent — creates picking tasks and assigns pickers when an order is placed` |

**Repository Details**

| Field | Value |
|---|---|
| GitHub Repository | `https://github.com/thanujeashwin/wso2demo` |
| Branch | `main` |
| Project Path | `Morrisons/warehouse_agent` |

**Build Details**

| Field | Value |
|---|---|
| Language | `Python` |
| Start Command | `python main.py` |
| Language Version | `3.11` |
| Enable auto instrumentation | ✅ checked |

**Agent Type:** `Chat Agent`

**Environment Variables:**

| Key | Value | Secret |
|---|---|---|
| `PORT` | `8000` | ☐ |

---

### Agent 8 — Supplier Agent

**Agent Details**

| Field | Value |
|---|---|
| Name | `Morrisons Supplier Agent` |
| Description | `Supplier management agent — looks up preferred suppliers and raises purchase orders when stock falls below reorder threshold` |

**Repository Details**

| Field | Value |
|---|---|
| GitHub Repository | `https://github.com/thanujeashwin/wso2demo` |
| Branch | `main` |
| Project Path | `Morrisons/supplier_agent` |

**Build Details**

| Field | Value |
|---|---|
| Language | `Python` |
| Start Command | `python main.py` |
| Language Version | `3.11` |
| Enable auto instrumentation | ✅ checked |

**Agent Type:** `Chat Agent`

**Environment Variables:**

| Key | Value | Secret |
|---|---|---|
| `PORT` | `8000` | ☐ |

---

### Agent 9 — Orchestrator

> Deploy this **after** all sub-agents are running. Set the sub-agent URLs in environment variables so the orchestrator can reach them.

**Agent Details**

| Field | Value |
|---|---|
| Name | `Morrisons Orchestrator` |
| Description | `Master orchestrator for Morrisons — routes requests to SAP, Oracle, Salesforce, AWS, and GCP specialist agents` |

**Repository Details**

| Field | Value |
|---|---|
| GitHub Repository | `https://github.com/thanujeashwin/wso2demo` |
| Branch | `main` |
| Project Path | `Morrisons/orchestrator` |

**Build Details**

| Field | Value |
|---|---|
| Language | `Python` |
| Start Command | `python main.py` |
| Language Version | `3.11` |
| Enable auto instrumentation | ✅ checked |

**Agent Type:** `Chat Agent`

**Environment Variables:**

| Key | Value | Secret |
|---|---|---|
| `PORT` | `8000` | ☐ |
| `SAP_AGENT_URL` | `http://<sap-agent-host>:<port>` | ☐ |
| `ORACLE_AGENT_URL` | `http://<oracle-agent-host>:<port>` | ☐ |
| `SALESFORCE_AGENT_URL` | `http://<salesforce-agent-host>:<port>` | ☐ |
| `AWS_AGENT_URL` | `http://<aws-agent-host>:<port>` | ☐ |
| `GCP_AGENT_URL` | `http://<gcp-agent-host>:<port>` | ☐ |

---

### Agent 10 — Customer Agent

> Deploy this **after** the Inventory Agent and Warehouse Agent are running.

**Agent Details**

| Field | Value |
|---|---|
| Name | `Morrisons Customer Agent` |
| Description | `Customer-facing agent for browsing products, checking stock, placing orders and tracking deliveries` |

**Repository Details**

| Field | Value |
|---|---|
| GitHub Repository | `https://github.com/thanujeashwin/wso2demo` |
| Branch | `main` |
| Project Path | `Morrisons/customer_agent` |

**Build Details**

| Field | Value |
|---|---|
| Language | `Python` |
| Start Command | `python main.py` |
| Language Version | `3.11` |
| Enable auto instrumentation | ✅ checked |

**Agent Type:** `Chat Agent`

**Environment Variables:**

| Key | Value | Secret |
|---|---|---|
| `PORT` | `8000` | ☐ |
| `PRODUCTION_GEMINI_LLM_URL` | `http://ai-gateway.amp.localhost:8084/llm/gemini` | ☐ |
| `PRODUCTION_GEMINI_LLM_API_KEY` | `<your-gateway-api-key>` | ✅ |
| `GEMINI_MODEL` | `gemini-2.5-flash` | ☐ |
| `INVENTORY_AGENT_URL` | `http://<inventory-agent-host>:<port>` | ☐ |
| `WAREHOUSE_AGENT_URL` | `http://<warehouse-agent-host>:<port>` | ☐ |

---

### Request / Response schema (all agents)

All ten agents use the same Chat Agent interface:

```
POST /chat
Request:  { "message": string, "session_id": string, "context": object }
Response: { "response": string }

GET /health
Response: { "status": "ok", "agent": "<agent-name>" }

GET /tools
Response: { "tools": [...] }
```

---

## How It Works

### Customer Agent (custom ReAct + Gemini)

```
Incoming /chat request
        │
        ▼
  Custom ReAct loop (agent.py)
  GatewayLLM.select_tool()       ← Gemini 2.5 Flash via WSO2 AI Gateway
  ├── Returns JSON {"tool": "...", "args": {...}}
  │
  ▼
  Tool execution (tools.py)
  ├── place_order → notify.py
  │                 ├── OTel span: agent.notify.inventory-agent  (sync)
  │                 ├── OTel span: agent.notify.warehouse-agent  (sync)
  │                 ├── Thread → POST inventory-agent/chat       (async)
  │                 └── Thread → POST warehouse-agent/chat       (async)
  │
  ▼
  GatewayLLM.generate_response()
  └── Final natural-language reply to customer
        │
        ▼
  FastAPI returns {"response": "..."}
```

### Back-Office Agents (LangGraph ReAct)

```
Incoming /chat request
        │
        ▼
  LangGraph agent node
  DemoLLM._generate()
  ├── No ToolMessage yet → returns AIMessage with tool_call (keyword-selected tool)
  │
  ▼
  LangGraph tools node
  ToolNode executes the mock tool → returns realistic mock data
  │
  ▼
  LangGraph agent node (second pass)
  DemoLLM._generate()
  └── ToolMessage present → returns final AIMessage with business response
        │
        ▼
  FastAPI returns {"response": "..."}
```

---

## Observability

WSO2 Agent Manager injects **Traceloop** via `sitecustomize.py` at startup. No OTEL initialisation code is needed in the agents.

Every request generates spans for:
- LangGraph graph execution (entry, transitions, exit) — back-office agents
- `DemoLLM.invoke()` or `GatewayLLM` call (LLM span)
- Tool execution (tool span)
- Inter-agent dispatch (`agent.notify.*` spans) — customer order flow
- FastAPI request/response

Traces are visible in the **Runtime Logs** and **Traces** views in Agent Manager.

---

## Repository Structure

```
wso2demo/
└── Morrisons/
    ├── README.md
    ├── customer_agent/         # Customer shopping agent — Gemini via WSO2 AI Gateway
    │   ├── agent.py            # Custom ReAct loop + GatewayLLM (google-genai SDK)
    │   ├── app.py              # FastAPI app + /chat endpoint
    │   ├── notify.py           # Fire-and-forget inter-agent notifications + OTel spans
    │   ├── tools.py            # browse_products, check_stock, place_order, track_order
    │   ├── demo_data.py        # Mock product catalogue, stock, customers, orders
    │   ├── traces.py           # OTel span helpers
    │   ├── main.py             # uvicorn entry point
    │   ├── requirements.txt
    │   └── static/index.html   # WSO2-themed chat UI
    ├── inventory_agent/        # Stock reservation + reorder monitoring
    │   ├── agent.py            # Custom ReAct loop
    │   ├── app.py
    │   ├── tools.py            # reserve_stock, check_inventory_levels, release_reservation
    │   ├── demo_data.py
    │   ├── traces.py
    │   ├── main.py
    │   └── requirements.txt
    ├── warehouse_agent/        # Fulfilment task creation + picker assignment
    │   ├── agent.py
    │   ├── app.py
    │   ├── tools.py            # create_fulfilment_task, assign_picker, update_dispatch_status
    │   ├── demo_data.py
    │   ├── traces.py
    │   ├── main.py
    │   └── requirements.txt
    ├── supplier_agent/         # Purchase order management
    │   ├── agent.py
    │   ├── app.py
    │   ├── tools.py            # get_supplier_info, raise_purchase_order
    │   ├── demo_data.py
    │   ├── traces.py
    │   ├── main.py
    │   └── requirements.txt
    ├── orchestrator/           # Master orchestrator — LangGraph ReAct
    │   ├── app.py
    │   ├── config.py
    │   ├── graph.py
    │   ├── tools.py
    │   ├── main.py
    │   ├── openapi.yaml
    │   └── requirements.txt
    ├── sap_agent/              # SAP S/4HANA agent — LangGraph ReAct
    ├── oracle_agent/           # Oracle Fusion ERP agent — LangGraph ReAct
    ├── salesforce_agent/       # Salesforce CRM agent — LangGraph ReAct
    ├── aws_agent/              # AWS Cloud agent — LangGraph ReAct
    └── gcp_agent/              # GCP agent — LangGraph ReAct
```
