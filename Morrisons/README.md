# Morrisons AI Agent Demo — WSO2 Agent Manager

A suite of six AI agents built for **WSO2 Agent Manager**, demonstrating a multi-agent architecture for Morrisons supermarkets (UK). The agents simulate a real enterprise AI platform spanning SAP ERP, Oracle Finance, Salesforce CRM, AWS, and GCP — emitting full observability traces via Traceloop on every request.

> **Demo mode:** All agents use a `DemoLLM` (no API key required). The full LangGraph ReAct pipeline runs on every request so WSO2 Agent Manager emits traces exactly as it would with a production LLM.

---

## Architecture

```
                        ┌──────────────────────────────────────┐
                        │         WSO2 Agent Manager           │
                        │   (Traceloop auto-instrumentation)   │
                        └────────────────┬─────────────────────┘
                                         │
                             ┌───────────▼───────────┐
                             │     Orchestrator       │
                             │   POST /chat  :8000    │
                             │  LangGraph ReAct       │
                             └──┬────┬────┬────┬──┬──┘
                                │    │    │    │  │
               ┌────────────────┘    │    │    │  └──────────────────┐
               │         ┌───────────┘    └────────────┐             │
               ▼         ▼                             ▼             ▼
     ┌──────────────┐ ┌──────────────┐     ┌──────────────┐ ┌──────────────┐
     │  SAP ERP     │ │ Oracle ERP   │     │    AWS       │ │    GCP       │
     │  :8001       │ │  :8002       │     │    :8004     │ │    :8005     │
     └──────────────┘ └──────────────┘     └──────────────┘ └──────────────┘
                             ┌──────────────┐
                             │  Salesforce  │
                             │    :8003     │
                             └──────────────┘
```

Each agent exposes a **FastAPI `/chat` endpoint** and runs a **LangGraph ReAct graph** (`agent node ↔ tools node`). The orchestrator delegates to sub-agents via HTTP.

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

**Loyalty tiers:** Bronze (0–499 pts), Silver (500–1999 pts), Gold (2000+ pts)

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

## How It Works (Demo Mode)

Each agent uses a `DemoLLM` defined in `graph.py`. It implements LangChain's `BaseChatModel` interface so Traceloop auto-instrumentation treats it identically to a real LLM.

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

Every step emits Traceloop spans: LLM call, tool execution, graph transitions.

---

## WSO2 Agent Manager Configuration

> **Deploy order:** always deploy the 5 sub-agents first, then the orchestrator last.

---

### Agent 1 — SAP ERP Agent

| Field | Value |
|---|---|
| **Name** | `Morrisons SAP ERP Agent` |
| **Description** | SAP S/4HANA agent for stock levels, purchase orders, supplier data, and demand forecasting |
| **Repository URL** | `https://github.com/thanujeashwin/wso2demo` |
| **Branch** | `main` |
| **Sub-directory** | `Morrisons/sap_agent` |
| **Entry point** | `main.py` |
| **Port** | `8001` |
| **Health endpoint** | `GET /health` |
| **Chat endpoint** | `POST /chat` |

**Environment variables:**
```env
# No keys required in demo mode
# Optional – only if switching to a real LLM:
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
```

**Example request:**
```json
POST http://<host>:8001/chat
{
  "message": "What is the current stock level for SKU-BEEF-001?",
  "session_id": "demo-session-1",
  "context": { "store_id": "STORE-001", "user_id": "buyer-001" }
}
```

**Example response:**
```json
{
  "response": "SAP MM Stock Check\nSKU: SKU-BEEF-001 | Store: STORE-001 | Plant: GBR1\nProduct: Morrisons Best Beef Mince 500g\nCurrent Stock: 45 units\nReorder Level: 120 units\nStatus: ⚠ BELOW REORDER LEVEL – replenishment required\n..."
}
```

---

### Agent 2 — Oracle ERP Agent

| Field | Value |
|---|---|
| **Name** | `Morrisons Oracle ERP Agent` |
| **Description** | Oracle Fusion Cloud ERP agent for budgets, PO approvals, invoices, cost centres, and journal entries |
| **Repository URL** | `https://github.com/thanujeashwin/wso2demo` |
| **Branch** | `main` |
| **Sub-directory** | `Morrisons/oracle_agent` |
| **Entry point** | `main.py` |
| **Port** | `8002` |
| **Health endpoint** | `GET /health` |
| **Chat endpoint** | `POST /chat` |

**Environment variables:**
```env
# No keys required in demo mode
# Optional – only if switching to a real LLM:
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
```

**Example request:**
```json
POST http://<host>:8002/chat
{
  "message": "What is the available budget for cost centre CC-PRODUCE-01 in Q1 2026?",
  "session_id": "demo-session-1",
  "context": { "user_id": "finance-manager-001" }
}
```

**Example response:**
```json
{
  "response": "Oracle Fusion Budget Availability\nCost Centre: CC-PRODUCE-01 | Period: 2026-Q1\nApproved Budget: £850,000\nActual Spend: £512,340\nCommitted: £87,200\nAvailable: £250,460 (29.5%)\nStatus: ✓ Within budget\n..."
}
```

---

### Agent 3 — Salesforce CRM Agent

| Field | Value |
|---|---|
| **Name** | `Morrisons Salesforce CRM Agent` |
| **Description** | Salesforce Sales & Service Cloud agent for customer loyalty, personalised offers, supplier accounts, and service cases |
| **Repository URL** | `https://github.com/thanujeashwin/wso2demo` |
| **Branch** | `main` |
| **Sub-directory** | `Morrisons/salesforce_agent` |
| **Entry point** | `main.py` |
| **Port** | `8003` |
| **Health endpoint** | `GET /health` |
| **Chat endpoint** | `POST /chat` |

**Environment variables:**
```env
# No keys required in demo mode
# Optional – only if switching to a real LLM:
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
```

**Example request:**
```json
POST http://<host>:8003/chat
{
  "message": "Get the loyalty profile for customer CUST-100142",
  "session_id": "demo-session-1",
  "context": { "user_id": "crm-agent-001" }
}
```

**Example response:**
```json
{
  "response": "Salesforce Customer Profile\nID: CUST-100142 | Name: Sarah Thompson\nLoyalty Tier: Gold | Points: 4,820\nLifetime Spend: £12,340 | Member Since: 2019-03-14\nPreferred Categories: Fresh Produce, Dairy\n..."
}
```

---

### Agent 4 — AWS Cloud Agent

| Field | Value |
|---|---|
| **Name** | `Morrisons AWS Cloud Agent` |
| **Description** | AWS agent for sales analytics, Lambda workflows, S3 reports, SNS notifications, and DynamoDB session data |
| **Repository URL** | `https://github.com/thanujeashwin/wso2demo` |
| **Branch** | `main` |
| **Sub-directory** | `Morrisons/aws_agent` |
| **Entry point** | `main.py` |
| **Port** | `8004` |
| **Health endpoint** | `GET /health` |
| **Chat endpoint** | `POST /chat` |

**Environment variables:**
```env
# No keys required in demo mode
# Optional – only if switching to a real LLM:
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
```

**Example request:**
```json
POST http://<host>:8004/chat
{
  "message": "Analyse sales trends for STORE-001 over the last 30 days",
  "session_id": "demo-session-1",
  "context": { "store_id": "STORE-001" }
}
```

**Example response:**
```json
{
  "response": "AWS Sales Trend Analysis | Store: STORE-001 | Period: 30 days\nTotal Revenue: £1,842,500\nTop Category: Fresh Meat (£412,000, +8.3% WoW)\nBasket Size: £34.20 avg | Transactions: 53,870\nPeak Day: Saturday | Peak Hour: 12:00–13:00\n..."
}
```

---

### Agent 5 — GCP Cloud Agent

| Field | Value |
|---|---|
| **Name** | `Morrisons GCP Cloud Agent` |
| **Description** | GCP agent for BigQuery analytics, Vertex AI predictions, Pub/Sub events, IoT sensor data, and Document AI |
| **Repository URL** | `https://github.com/thanujeashwin/wso2demo` |
| **Branch** | `main` |
| **Sub-directory** | `Morrisons/gcp_agent` |
| **Entry point** | `main.py` |
| **Port** | `8005` |
| **Health endpoint** | `GET /health` |
| **Chat endpoint** | `POST /chat` |

**Environment variables:**
```env
# No keys required in demo mode
# Optional – only if switching to a real LLM:
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
```

**Example request:**
```json
POST http://<host>:8005/chat
{
  "message": "Run a BigQuery sales summary for STORE-001",
  "session_id": "demo-session-1",
  "context": { "store_id": "STORE-001" }
}
```

**Example response:**
```json
{
  "response": "BigQuery Analytics | Query: sales_summary | Store: STORE-001\nRows Processed: 2,847,392 | Bytes Billed: 48 MB\nRevenue (7d): £428,750 | Units Sold: 187,430\nTop SKU: SKU-MILK-003 (12,840 units)\nQuery Duration: 1.24s | Job ID: bq-job-20260409-001\n..."
}
```

---

### Agent 6 — Orchestrator

| Field | Value |
|---|---|
| **Name** | `Morrisons Orchestrator` |
| **Description** | Master orchestrator that routes requests to SAP, Oracle, Salesforce, AWS, and GCP specialist agents |
| **Repository URL** | `https://github.com/thanujeashwin/wso2demo` |
| **Branch** | `main` |
| **Sub-directory** | `Morrisons/orchestrator` |
| **Entry point** | `main.py` |
| **Port** | `8000` |
| **Health endpoint** | `GET /health` |
| **Chat endpoint** | `POST /chat` |

**Environment variables:**
```env
# Sub-agent URLs — update if agents are deployed on different hosts
SAP_AGENT_URL=http://localhost:8001
ORACLE_AGENT_URL=http://localhost:8002
SALESFORCE_AGENT_URL=http://localhost:8003
AWS_AGENT_URL=http://localhost:8004
GCP_AGENT_URL=http://localhost:8005

# Optional – only if switching to a real LLM:
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
```

**Example request:**
```json
POST http://<host>:8000/chat
{
  "message": "Check stock for beef mince, raise a PO if needed, and notify the ops team",
  "session_id": "demo-session-1",
  "context": { "user_id": "store-manager-001", "store_id": "STORE-001" }
}
```

**Example response:**
```json
{
  "response": "Here is the consolidated response from the Morrisons specialist agents:\n\nSAP MM Stock Check — SKU-BEEF-001 is BELOW REORDER LEVEL (45 units, reorder at 120).\nSAP Purchase Order PO-004502 raised for 240 units from British Meat Supplies Ltd.\nAWS SNS notification sent to ops-alerts topic.\n\n✓ Orchestration complete."
}
```

---

### Request schema (all agents)

All six agents share the same `/chat` request and response schema:

```yaml
ChatRequest:
  message:    string  # required — user's question or instruction
  session_id: string  # required — unique conversation identifier
  context:    object  # optional — key/value pairs (store_id, user_id, etc.)

ChatResponse:
  response:   string  # agent's text response
```

---

### Verify all agents are healthy

```bash
curl http://localhost:8001/health   # → {"status":"ok","agent":"morrisons-sap-erp-agent"}
curl http://localhost:8002/health   # → {"status":"ok","agent":"morrisons-oracle-erp-agent"}
curl http://localhost:8003/health   # → {"status":"ok","agent":"morrisons-salesforce-agent"}
curl http://localhost:8004/health   # → {"status":"ok","agent":"morrisons-aws-cloud-agent"}
curl http://localhost:8005/health   # → {"status":"ok","agent":"morrisons-gcp-cloud-agent"}
curl http://localhost:8000/health   # → {"status":"ok","agent":"morrisons-orchestrator"}
```

---

## Running Locally (without Agent Manager)

```bash
# Install dependencies (per agent)
cd sap_agent && pip install -r requirements.txt

# Start all agents
python sap_agent/main.py &        # port 8001
python oracle_agent/main.py &     # port 8002
python salesforce_agent/main.py & # port 8003
python aws_agent/main.py &        # port 8004
python gcp_agent/main.py &        # port 8005
python orchestrator/main.py       # port 8000 (foreground)
```

---

## Switching to a Real LLM

To replace `DemoLLM` with a real model, update `graph.py` in the relevant agent:

```python
# Replace this:
llm = DemoLLM().bind_tools(tools)

# With this (Anthropic):
from config import settings
llm = settings.build_llm().bind_tools(tools)
```

Then set `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` in the agent's environment. The `build_llm()` method in `config.py` tries Anthropic first, then falls back to OpenAI.

---

## Repository Structure

```
wso2demo/
└── Morrisons/
    ├── README.md
    ├── orchestrator/           # Master orchestrator (port 8000)
    │   ├── app.py              # FastAPI app + /chat endpoint
    │   ├── config.py           # Pydantic settings (LLM config, sub-agent URLs)
    │   ├── graph.py            # LangGraph ReAct graph + DemoLLM
    │   ├── tools.py            # ask_* tools (HTTP delegation to sub-agents)
    │   ├── main.py             # uvicorn entry point
    │   ├── openapi.yaml        # OpenAPI 3.1 spec
    │   └── requirements.txt
    ├── sap_agent/              # SAP S/4HANA agent (port 8001)
    ├── oracle_agent/           # Oracle Fusion ERP agent (port 8002)
    ├── salesforce_agent/       # Salesforce CRM agent (port 8003)
    ├── aws_agent/              # AWS Cloud agent (port 8004)
    └── gcp_agent/              # GCP agent (port 8005)
```

Each agent directory has the same 7-file structure as `orchestrator/`.

---

## Observability

WSO2 Agent Manager injects **Traceloop** via `sitecustomize.py` at startup. No OTEL initialisation code is needed in the agents — adding any would conflict with the platform's tracer.

Every request generates spans for:
- LangGraph graph execution (entry, transitions, exit)
- `DemoLLM.invoke()` (LLM span)
- `ToolNode` tool execution (tool span)
- FastAPI request/response

Traces are visible in the **Runtime Logs** and **Traces** views in Agent Manager.
