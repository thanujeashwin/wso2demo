# Retail AI Agent Demo — WSO2 Agent Manager

A suite of **ten AI agents** built for **WSO2 Agent Manager**, demonstrating a multi-agent architecture for a Retail supermarket chain. The agents cover customer shopping, inventory management, warehouse fulfilment, supplier procurement, SAP ERP, Oracle ERP, Salesforce CRM, AWS, GCP, and an orchestrator — all emitting full observability traces via Traceloop on every request.

**LLM:** All agents use **Google Gemini** via the **WSO2 AI Gateway** (`GatewayLLM`). A deterministic `DemoLLM` keyword-router is used automatically as a local fallback when `GEMINILLM_URL` / `GEMINILLM_API_KEY` are not set, so the full ReAct pipeline runs and WSO2 Agent Manager emits traces exactly as it would in production.

---

## Architecture

```
  Customer (Browser)
        │
        ▼
┌──────────────────┐
│  Customer Agent  │  POST /chat
│  Custom ReAct    │
│  Gemini / Demo   │
└──────┬───────────┘
       │  on successful order placement (async, fire-and-forget)
       ├──────────────────────────────────────┐
       ▼                                      ▼
┌─────────────────────┐            ┌──────────────────────┐
│  Inventory Agent    │            │  Warehouse Agent     │
│  reserve_stock      │            │  create_fulfilment   │
│  check_levels       │            │  assign_picker       │
│  Gemini / Demo      │            │  Gemini / Demo       │
└──────┬──────────────┘            └──────────────────────┘
       │  if stock < reorder point (async, fire-and-forget)
       ▼
┌─────────────────────┐
│  Supplier Agent     │
│  get_supplier_info  │
│  raise_purchase_order│
│  Gemini / Demo      │
└─────────────────────┘

  Staff / Internal Integrations
        │
        ▼
┌──────────────────────────────┐
│        Orchestrator          │  POST /chat
│  LangGraph ReAct             │
│  Gemini / Demo               │
└──┬────┬────┬────┬────────────┘
   │    │    │    │
   ▼    ▼    ▼    ▼
┌────────┐ ┌────────┐ ┌────────────┐ ┌────────┐ ┌────────┐
│SAP ERP │ │ERP     │ │Salesforce  │ │  AWS   │ │  GCP   │
│LangGraph│ │LangGraph│ │LangGraph  │ │LangGraph│ │LangGraph│
└────────┘ └────────┘ └────────────┘ └────────┘ └────────┘
```

**Async notification flow:** When a customer places an order, `customer_agent` immediately returns a confirmation to the user, then fires background HTTP POSTs to `inventory_agent` and `warehouse_agent` in parallel. If `inventory_agent` finds any product below its reorder point after reserving stock, it fires a further background POST to `supplier_agent` to raise a purchase order — without blocking any of the upstream responses.

All agents expose `POST /chat` on port 8000 inside their container. The five back-office agents and orchestrator use a **LangGraph ReAct graph**. The customer, inventory, warehouse, and supplier agents use a **custom ReAct loop** (no LangGraph), demonstrating that WSO2 Agent Manager is framework-agnostic.

---

## Agents

### Orchestrator (`orchestrator/`)

The master agent for internal/staff use. Routes incoming requests to the right specialist sub-agent and synthesises the responses.

**Routing logic:**
| Keywords in message | Delegates to |
|---|---|
| sap, stock, inventory, purchase order, goods, reorder | `ask_sap_erp_agent` |
| erp, oracle, budget, finance, invoice, approval, cost centre | `ask_erp_agent` |
| salesforce, customer, loyalty, crm, offer, case | `ask_salesforce_agent` |
| aws, lambda, s3, dynamodb, sns | `ask_aws_agent` |
| gcp, bigquery, vertex, pubsub, iot, forecast | `ask_gcp_agent` |

---

### SAP ERP Agent (`sap_agent/`)

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

### ERP Agent (`ERP_agent/`)

Simulates ERP integration covering General Ledger, Accounts Payable, Procurement, and Budgetary Control.

**Tools:**
| Tool | Description |
|---|---|
| `get_budget_availability` | Available budget for a cost centre and fiscal period |
| `approve_purchase_order` | Approval workflow for a PO |
| `get_cost_centre_report` | Actual vs budget spend for a cost centre |
| `get_invoice_status` | Accounts payable invoice status and payment details |
| `create_journal_entry` | Posts a GL journal entry (debit/credit) |

**Demo cost centres:** `CC-PRODUCE-01`, `CC-MEAT-02`, `CC-DAIRY-03`, `CC-BAKERY-04`

---

### Salesforce Agent (`salesforce_agent/`)

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

---

### AWS Agent (`aws_agent/`)

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

### GCP Agent (`gcp_agent/`)

Simulates Google Cloud Platform services for analytics, ML predictions, event streaming, IoT monitoring, and document processing.

**Tools:**
| Tool | Description |
|---|---|
| `run_bigquery_analytics` | Executes a named analytics query against BigQuery |
| `call_vertex_ai_prediction` | Calls a Vertex AI model (demand forecast, recommender) |
| `publish_pubsub_event` | Publishes a reorder or pricing event to Pub/Sub |
| `get_store_iot_data` | Reads refrigeration/temperature sensor data via IoT Core |
| `run_document_ai` | Processes a supplier invoice via Google Document AI |

---

### Customer Agent (`customer_agent/`)

Customer-facing shopping assistant. Handles product browsing, stock checks, order placement, and order tracking. On a successful order, **asynchronously notifies** `inventory_agent` and `warehouse_agent` in background threads — the customer receives their confirmation immediately.

**Tools:**
| Tool | Description |
|---|---|
| `browse_products` | List products, optionally filtered by category |
| `check_stock` | Current stock level for a product |
| `place_order` | Place an order; triggers async inventory + warehouse notifications |
| `track_order` | Status and tracking info for an existing order |
| `get_customer_profile` | Customer profile, loyalty tier, and recent orders |

---

### Inventory Agent (`inventory_agent/`)

Triggered asynchronously by `customer_agent` on order placement. Reserves warehouse stock for the order, then checks inventory levels for each item. If any product falls below its reorder point, **asynchronously notifies** `supplier_agent` to raise a purchase order.

**Tools:**
| Tool | Description |
|---|---|
| `reserve_stock` | Reserve warehouse stock for a confirmed order |
| `check_inventory_levels` | Check current stock level and reorder status for a product |
| `release_reservation` | Release a stock reservation for a cancelled order |

---

### Warehouse Agent (`warehouse_agent/`)

Triggered asynchronously by `customer_agent` on order placement. Creates a pick-and-pack fulfilment task, assigns an available picker, and tracks dispatch status.

**Tools:**
| Tool | Description |
|---|---|
| `create_fulfilment_task` | Create a pick-and-pack task for an order |
| `assign_picker` | Assign an available picker to a fulfilment task |
| `update_dispatch_status` | Update the dispatch status of a fulfilment task |

---

### Supplier Agent (`supplier_agent/`)

Triggered asynchronously by `inventory_agent` when stock falls below the reorder threshold. Retrieves supplier information and raises a purchase order for restocking.

**Tools:**
| Tool | Description |
|---|---|
| `get_supplier_info` | Supplier details and lead time for a product |
| `raise_purchase_order` | Raise a purchase order with the supplier for restocking |

---

## How It Works

Each agent uses a **custom ReAct loop** (`customer_agent`, `inventory_agent`, `warehouse_agent`, `supplier_agent`) or a **LangGraph ReAct graph** (all others). The LLM is selected at startup:

```
GEMINILLM_URL + GEMINILLM_API_KEY set?
  ├── Yes → GatewayLLM (Gemini via WSO2 AI Gateway)
  └── No  → DemoLLM (deterministic keyword-router, no API key needed)
```

```
Incoming /chat request
        │
        ▼
  ReAct loop / LangGraph node
  LLM.select_tool()  ← Gemini or DemoLLM
  ├── Selects tool from available tools
  │
  ▼
  Tool execution → returns mock/real data
  │
  ▼
  LLM.synthesise()   ← Gemini or DemoLLM
  └── Produces natural-language response
        │
        ▼
  FastAPI returns { "response": "..." }
```

Every step emits Traceloop spans: LLM call, tool execution, graph transitions.

---

## WSO2 Agent Manager Configuration

Each agent is deployed via **Create a Platform-Hosted Agent** in Agent Manager. The form has four sections: Agent Details, Repository Details, Build Details, and Agent Type.

> **Deploy order:** Deploy the five back-office sub-agents (SAP, ERP, Salesforce, AWS, GCP) first. Then deploy `supplier_agent`, `inventory_agent`, `warehouse_agent`. Then `customer_agent`. Deploy `orchestrator` last.

> **Port:** Set `PORT` = `8000` as an environment variable for every agent so the agent binds to the correct port inside its container.

---

### Agent 1 — SAP ERP Agent

**Agent Details**

| Field | Value |
|---|---|
| Name | `Retail SAP ERP Agent` |
| Description | `SAP S/4HANA agent for Retail — stock levels, purchase orders, supplier data, and demand forecasting` |

**Repository Details**

| Field | Value |
|---|---|
| GitHub Repository | `https://github.com/thanujeashwin/wso2demo` |
| Branch | `main` |
| Project Path | `Retail/sap_agent` |

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
| `GEMINILLM_URL` | `https://<wso2-ai-gateway>/gemini` | ☐ |
| `GEMINILLM_API_KEY` | `<api-key>` | ✅ |
| `GEMINI_MODEL` | `gemini-3.5-flash` | ☐ |

**Example `/chat` request:**
```json
{
  "message": "What is the current stock level for SKU-BEEF-001?",
  "session_id": "demo-session-1",
  "context": { "store_id": "STORE-001", "user_id": "buyer-001" }
}
```

**Example response:**
```json
{
  "response": "SAP MM Stock Check\nSKU: SKU-BEEF-001 | Store: STORE-001\nProduct: Retail Best Beef Mince 500g\nCurrent Stock: 45 units | Reorder Level: 120 units\nStatus: ⚠ BELOW REORDER LEVEL — replenishment required"
}
```

---

### Agent 2 — ERP Agent

**Agent Details**

| Field | Value |
|---|---|
| Name | `Retail ERP Agent` |
| Description | `ERP agent for Retail — budgets, PO approvals, invoices, cost centres, and journal entries` |

**Repository Details**

| Field | Value |
|---|---|
| GitHub Repository | `https://github.com/thanujeashwin/wso2demo` |
| Branch | `main` |
| Project Path | `Retail/ERP_agent` |

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
| `GEMINILLM_URL` | `https://<wso2-ai-gateway>/gemini` | ☐ |
| `GEMINILLM_API_KEY` | `<api-key>` | ✅ |
| `GEMINI_MODEL` | `gemini-3.5-flash` | ☐ |

**Example `/chat` request:**
```json
{
  "message": "What is the available budget for cost centre CC-PRODUCE-01 in Q1 2026?",
  "session_id": "demo-session-1",
  "context": { "user_id": "finance-manager-001" }
}
```

**Example response:**
```json
{
  "response": "ERP Budget Availability\nCost Centre: CC-PRODUCE-01 | Period: 2026-Q1\nApproved Budget: £850,000 | Actual Spend: £512,340\nAvailable: £250,460 (29.5%) | Status: ✓ Within budget"
}
```

---

### Agent 3 — Salesforce CRM Agent

**Agent Details**

| Field | Value |
|---|---|
| Name | `Retail Salesforce CRM Agent` |
| Description | `Salesforce Sales & Service Cloud agent for Retail — customer loyalty, personalised offers, supplier accounts, and service cases` |

**Repository Details**

| Field | Value |
|---|---|
| GitHub Repository | `https://github.com/thanujeashwin/wso2demo` |
| Branch | `main` |
| Project Path | `Retail/salesforce_agent` |

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
| `GEMINILLM_URL` | `https://<wso2-ai-gateway>/gemini` | ☐ |
| `GEMINILLM_API_KEY` | `<api-key>` | ✅ |
| `GEMINI_MODEL` | `gemini-3.5-flash` | ☐ |

**Example `/chat` request:**
```json
{
  "message": "Get the loyalty profile for customer CUST-100142",
  "session_id": "demo-session-1",
  "context": { "user_id": "crm-agent-001" }
}
```

**Example response:**
```json
{
  "response": "Salesforce Customer Profile\nID: CUST-100142 | Name: Sarah Thompson\nLoyalty Tier: Gold | Points: 4,820\nLifetime Spend: £12,340 | Member Since: 2019-03-14"
}
```

---

### Agent 4 — AWS Cloud Agent

**Agent Details**

| Field | Value |
|---|---|
| Name | `Retail AWS Cloud Agent` |
| Description | `AWS agent for Retail — sales analytics, Lambda workflows, S3 reports, SNS notifications, and DynamoDB session data` |

**Repository Details**

| Field | Value |
|---|---|
| GitHub Repository | `https://github.com/thanujeashwin/wso2demo` |
| Branch | `main` |
| Project Path | `Retail/aws_agent` |

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
| `GEMINILLM_URL` | `https://<wso2-ai-gateway>/gemini` | ☐ |
| `GEMINILLM_API_KEY` | `<api-key>` | ✅ |
| `GEMINI_MODEL` | `gemini-3.5-flash` | ☐ |

**Example `/chat` request:**
```json
{
  "message": "Analyse sales trends for STORE-001 over the last 30 days",
  "session_id": "demo-session-1",
  "context": { "store_id": "STORE-001" }
}
```

**Example response:**
```json
{
  "response": "AWS Sales Trend Analysis | Store: STORE-001 | Period: 30 days\nTotal Revenue: £1,842,500 | Top Category: Fresh Meat (+8.3% WoW)\nBasket Size: £34.20 avg | Transactions: 53,870"
}
```

---

### Agent 5 — GCP Cloud Agent

**Agent Details**

| Field | Value |
|---|---|
| Name | `Retail GCP Cloud Agent` |
| Description | `GCP agent for Retail — BigQuery analytics, Vertex AI predictions, Pub/Sub events, IoT sensor data, and Document AI` |

**Repository Details**

| Field | Value |
|---|---|
| GitHub Repository | `https://github.com/thanujeashwin/wso2demo` |
| Branch | `main` |
| Project Path | `Retail/gcp_agent` |

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
| `GEMINILLM_URL` | `https://<wso2-ai-gateway>/gemini` | ☐ |
| `GEMINILLM_API_KEY` | `<api-key>` | ✅ |
| `GEMINI_MODEL` | `gemini-3.5-flash` | ☐ |

**Example `/chat` request:**
```json
{
  "message": "Run a BigQuery sales summary for STORE-001",
  "session_id": "demo-session-1",
  "context": { "store_id": "STORE-001" }
}
```

**Example response:**
```json
{
  "response": "BigQuery Analytics | Query: sales_summary | Store: STORE-001\nRevenue (7d): £428,750 | Units Sold: 187,430 | Top SKU: SKU-MILK-003"
}
```

---

### Agent 6 — Orchestrator

> Deploy this **last**, after all back-office sub-agents are running. Set the sub-agent URLs in environment variables so the orchestrator can reach them.

**Agent Details**

| Field | Value |
|---|---|
| Name | `Retail Orchestrator` |
| Description | `Master orchestrator for Retail — routes requests to SAP, ERP, Salesforce, AWS, and GCP specialist agents` |

**Repository Details**

| Field | Value |
|---|---|
| GitHub Repository | `https://github.com/thanujeashwin/wso2demo` |
| Branch | `main` |
| Project Path | `Retail/orchestrator` |

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
| `GEMINILLM_URL` | `https://<wso2-ai-gateway>/gemini` | ☐ |
| `GEMINILLM_API_KEY` | `<api-key>` | ✅ |
| `GEMINI_MODEL` | `gemini-3.5-flash` | ☐ |
| `SAP_AGENT_URL` | `http://<sap-agent-service>:8000` | ☐ |
| `ERP_AGENT_URL` | `http://<erp-agent-service>:8000` | ☐ |
| `SALESFORCE_AGENT_URL` | `http://<salesforce-agent-service>:8000` | ☐ |
| `AWS_AGENT_URL` | `http://<aws-agent-service>:8000` | ☐ |
| `GCP_AGENT_URL` | `http://<gcp-agent-service>:8000` | ☐ |

**Example `/chat` request:**
```json
{
  "message": "Check stock for beef mince, raise a PO if needed, and notify the ops team",
  "session_id": "demo-session-1",
  "context": { "user_id": "store-manager-001", "store_id": "STORE-001" }
}
```

**Example response:**
```json
{
  "response": "SAP MM: SKU-BEEF-001 is BELOW REORDER LEVEL (45 units, reorder at 120). PO-004502 raised for 240 units from British Meat Supplies Ltd. SNS notification sent to ops-alerts topic.\n\n✓ Orchestration complete."
}
```

---

### Agent 7 — Customer Agent

Customer-facing shopping assistant. Returns a response immediately; fires async notifications to inventory and warehouse agents in the background on every successful order.

**Agent Details**

| Field | Value |
|---|---|
| Name | `Retail Customer Agent` |
| Description | `Customer-facing agent for browsing products, checking stock, placing orders and tracking deliveries` |

**Repository Details**

| Field | Value |
|---|---|
| GitHub Repository | `https://github.com/thanujeashwin/wso2demo` |
| Branch | `main` |
| Project Path | `Retail/customer_agent` |

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
| `GEMINILLM_URL` | `https://<wso2-ai-gateway>/gemini` | ☐ |
| `GEMINILLM_API_KEY` | `<api-key>` | ✅ |
| `GEMINI_MODEL` | `gemini-3.5-flash` | ☐ |
| `INVENTORY_AGENT_URL` | `http://<inventory-agent-service>:8000` | ☐ |
| `WAREHOUSE_AGENT_URL` | `http://<warehouse-agent-service>:8000` | ☐ |

**Example `/chat` request:**
```json
{
  "message": "I want to order 2 of PROD-001",
  "session_id": "demo-session-1",
  "context": { "customer_id": "CUST-5001" }
}
```

**Example response:**
```json
{
  "response": "Order ORD-9004 confirmed for Emma Johnson.\nItems: Retail British Whole Milk 4pt × 2 = £3.30\nTotal: £3.30 | Estimated delivery: Within 2–4 hours"
}
```

---

### Agent 8 — Inventory Agent

Receives async notifications from `customer_agent`. Reserves warehouse stock, then checks inventory levels for each ordered product. If any product is below its reorder point, notifies `supplier_agent` in the background.

> Deploy **before** `customer_agent` so its URL is available.

**Agent Details**

| Field | Value |
|---|---|
| Name | `Retail Inventory Agent` |
| Description | `Inventory management agent — reserves warehouse stock for orders and triggers supplier restocking when levels are low` |

**Repository Details**

| Field | Value |
|---|---|
| GitHub Repository | `https://github.com/thanujeashwin/wso2demo` |
| Branch | `main` |
| Project Path | `Retail/inventory_agent` |

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
| `GEMINILLM_URL` | `https://<wso2-ai-gateway>/gemini` | ☐ |
| `GEMINILLM_API_KEY` | `<api-key>` | ✅ |
| `GEMINI_MODEL` | `gemini-3.5-flash` | ☐ |
| `SUPPLIER_AGENT_URL` | `http://<supplier-agent-service>:8000` | ☐ |

**Example `/chat` request** (sent by customer_agent):
```json
{
  "message": "Order ORD-9004 confirmed for customer CUST-5001. Items: [{\"product_id\": \"PROD-001\", \"quantity\": 2}]. Please process this order.",
  "session_id": "ORD-9004",
  "context": { "order_id": "ORD-9004", "customer_id": "CUST-5001", "items": [{"product_id": "PROD-001", "quantity": 2}] }
}
```

**Example response:**
```json
{
  "response": "Reserved 2 units of PROD-001 for order ORD-9004. Current available stock: 18 units (above reorder point of 10)."
}
```

---

### Agent 9 — Warehouse Agent

Receives async notifications from `customer_agent`. Creates a pick-and-pack fulfilment task for the order and assigns an available picker.

> Deploy **before** `customer_agent` so its URL is available.

**Agent Details**

| Field | Value |
|---|---|
| Name | `Retail Warehouse Agent` |
| Description | `Warehouse fulfilment agent — creates pick-and-pack tasks, assigns pickers, and updates dispatch status` |

**Repository Details**

| Field | Value |
|---|---|
| GitHub Repository | `https://github.com/thanujeashwin/wso2demo` |
| Branch | `main` |
| Project Path | `Retail/warehouse_agent` |

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
| `GEMINILLM_URL` | `https://<wso2-ai-gateway>/gemini` | ☐ |
| `GEMINILLM_API_KEY` | `<api-key>` | ✅ |
| `GEMINI_MODEL` | `gemini-3.5-flash` | ☐ |

**Example `/chat` request** (sent by customer_agent):
```json
{
  "message": "Order ORD-9004 confirmed for customer CUST-5001. Items: [{\"product_id\": \"PROD-001\", \"quantity\": 2}]. Please process this order.",
  "session_id": "ORD-9004",
  "context": { "order_id": "ORD-9004", "customer_id": "CUST-5001", "items": [{"product_id": "PROD-001", "quantity": 2}] }
}
```

**Example response:**
```json
{
  "response": "Fulfilment task TASK-0042 created for order ORD-9004. Picker P-07 (James) assigned. Status: picking."
}
```

---

### Agent 10 — Supplier Agent

Receives async notifications from `inventory_agent` when products fall below the reorder threshold. Retrieves supplier information and raises a purchase order.

> Deploy **before** `inventory_agent` so its URL is available.

**Agent Details**

| Field | Value |
|---|---|
| Name | `Retail Supplier Agent` |
| Description | `Supplier and procurement agent — retrieves supplier info and raises purchase orders when stock falls below reorder threshold` |

**Repository Details**

| Field | Value |
|---|---|
| GitHub Repository | `https://github.com/thanujeashwin/wso2demo` |
| Branch | `main` |
| Project Path | `Retail/supplier_agent` |

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
| `GEMINILLM_URL` | `https://<wso2-ai-gateway>/gemini` | ☐ |
| `GEMINILLM_API_KEY` | `<api-key>` | ✅ |
| `GEMINI_MODEL` | `gemini-3.5-flash` | ☐ |

**Example `/chat` request** (sent by inventory_agent):
```json
{
  "message": "Low stock alert. The following products need immediate restocking: [{\"product_id\": \"PROD-001\", \"available\": 8, \"reorder_point\": 10}]. Please raise purchase orders.",
  "session_id": "ORD-9004",
  "context": { "reorder_items": [{"product_id": "PROD-001", "available": 8, "reorder_point": 10}] }
}
```

**Example response:**
```json
{
  "response": "Purchase order PO-20240609-001 raised with supplier SUP-003 for 500 units of PROD-001 (Retail British Whole Milk 4pt). Expected lead time: 2 business days."
}
```

---

### Request / Response schema (all agents)

All ten agents use the same Chat Agent interface:

```
POST /chat
Request:  { "message": string, "session_id": string, "context": object }
Response: { "response": string }

GET /health
Response: { "status": "ok", "agent": "<agent-name>" }
```

---

## Recommended Deploy Order

```
1. supplier_agent        (no upstream dependencies)
2. inventory_agent       (needs SUPPLIER_AGENT_URL)
3. warehouse_agent       (no upstream dependencies)
4. customer_agent        (needs INVENTORY_AGENT_URL + WAREHOUSE_AGENT_URL)
5. sap_agent             (no upstream dependencies)
6. ERP_agent             (no upstream dependencies)
7. salesforce_agent      (no upstream dependencies)
8. aws_agent             (no upstream dependencies)
9. gcp_agent             (no upstream dependencies)
10. orchestrator         (needs all back-office agent URLs)
```

---

## Running Locally (without Agent Manager)

```bash
# Install dependencies (per agent)
cd supplier_agent && pip install -r requirements.txt && cd ..

# Start agents (each agent binds to port 8000 inside its container;
# override PORT when running multiple locally)
PORT=8006 python supplier_agent/main.py &
PORT=8007 SUPPLIER_AGENT_URL=http://localhost:8006 python inventory_agent/main.py &
PORT=8008 python warehouse_agent/main.py &
PORT=8000 INVENTORY_AGENT_URL=http://localhost:8007 WAREHOUSE_AGENT_URL=http://localhost:8008 python customer_agent/main.py &
PORT=8001 python sap_agent/main.py &
PORT=8002 python ERP_agent/main.py &
PORT=8003 python salesforce_agent/main.py &
PORT=8004 python aws_agent/main.py &
PORT=8005 python gcp_agent/main.py &
PORT=8009 SAP_AGENT_URL=http://localhost:8001 ERP_AGENT_URL=http://localhost:8002 \
    SALESFORCE_AGENT_URL=http://localhost:8003 AWS_AGENT_URL=http://localhost:8004 \
    GCP_AGENT_URL=http://localhost:8005 python orchestrator/main.py &
```

Set `GEMINILLM_URL` and `GEMINILLM_API_KEY` on each agent to use Gemini; omit them to fall back to `DemoLLM`.

---

## Repository Structure

```
wso2demo/
└── Retail/
    ├── README.md
    ├── customer_agent/         # Customer shopping agent — async triggers inventory + warehouse
    │   ├── app.py              # FastAPI app + /chat endpoint
    │   ├── agent.py            # Custom ReAct loop + GatewayLLM/DemoLLM
    │   ├── tools.py            # browse_products, check_stock, place_order, track_order
    │   ├── demo_data.py        # Mock product catalogue, stock, customers, orders
    │   ├── traces.py           # Mock OTLP span emitter
    │   ├── main.py             # uvicorn entry point
    │   ├── requirements.txt
    │   └── static/index.html   # WSO2-themed chat UI
    ├── inventory_agent/        # Inventory agent — reserves stock, triggers supplier
    │   ├── app.py
    │   ├── agent.py            # Custom ReAct loop + GatewayLLM/DemoLLM + supplier notification
    │   ├── tools.py            # reserve_stock, check_inventory_levels, release_reservation
    │   ├── demo_data.py
    │   ├── traces.py
    │   ├── main.py
    │   └── requirements.txt
    ├── warehouse_agent/        # Warehouse fulfilment agent
    │   ├── app.py
    │   ├── agent.py            # Custom ReAct loop + GatewayLLM/DemoLLM
    │   ├── tools.py            # create_fulfilment_task, assign_picker, update_dispatch_status
    │   ├── demo_data.py
    │   ├── traces.py
    │   ├── main.py
    │   └── requirements.txt
    ├── supplier_agent/         # Supplier/procurement agent
    │   ├── app.py
    │   ├── agent.py            # Custom ReAct loop + GatewayLLM/DemoLLM
    │   ├── tools.py            # get_supplier_info, raise_purchase_order
    │   ├── demo_data.py
    │   ├── traces.py
    │   ├── main.py
    │   └── requirements.txt
    ├── orchestrator/           # Master orchestrator (back-office)
    │   ├── app.py
    │   ├── config.py           # Pydantic settings (LLM config, sub-agent URLs)
    │   ├── graph.py            # LangGraph ReAct graph + GatewayLLM/DemoLLM
    │   ├── tools.py            # ask_* tools (HTTP delegation to sub-agents)
    │   ├── main.py
    │   └── requirements.txt
    ├── sap_agent/              # SAP S/4HANA agent
    ├── ERP_agent/              # ERP agent (General Ledger, AP, Procurement)
    ├── salesforce_agent/       # Salesforce CRM agent
    ├── aws_agent/              # AWS Cloud agent
    └── gcp_agent/              # GCP agent
```

---

## Observability

WSO2 Agent Manager injects **Traceloop** via `sitecustomize.py` at startup. No OTEL initialisation code is needed in the agents.

Every request generates spans for:
- LLM call (`GatewayLLM` or `DemoLLM`)
- Tool execution (per tool)
- LangGraph graph transitions (back-office agents)
- FastAPI request/response

Traces are visible in the **Runtime Logs** and **Traces** views in Agent Manager. The async background notifications to downstream agents each produce their own independent trace trees.
