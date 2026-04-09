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

### Step 1 — Add each agent

In Agent Manager, add **6 separate agents** using these settings:

| Agent | Repository path | Entry point | Port |
|---|---|---|---|
| Morrisons Orchestrator | `orchestrator/` | `main.py` | 8000 |
| Morrisons SAP ERP | `sap_agent/` | `main.py` | 8001 |
| Morrisons Oracle ERP | `oracle_agent/` | `main.py` | 8002 |
| Morrisons Salesforce CRM | `salesforce_agent/` | `main.py` | 8003 |
| Morrisons AWS Cloud | `aws_agent/` | `main.py` | 8004 |
| Morrisons GCP Cloud | `gcp_agent/` | `main.py` | 8005 |

> **Important:** Set the repository path to the subdirectory (e.g. `sap_agent/`), not the repo root. Each agent's `main.py` is the uvicorn entry point.

### Step 2 — Environment variables

No API keys are required in demo mode. The only optional variables are:

```env
# Optional – only needed if switching to a real LLM later
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...

# Sub-agent URLs (defaults shown – change if deploying to different hosts/ports)
SAP_AGENT_URL=http://localhost:8001
ORACLE_AGENT_URL=http://localhost:8002
SALESFORCE_AGENT_URL=http://localhost:8003
AWS_AGENT_URL=http://localhost:8004
GCP_AGENT_URL=http://localhost:8005
```

### Step 3 — Deploy order

Deploy sub-agents **before** the orchestrator:

```
1. sap_agent
2. oracle_agent
3. salesforce_agent
4. aws_agent
5. gcp_agent
6. orchestrator  ← deploy last
```

### Step 4 — Verify

Each agent exposes a health check endpoint:

```bash
curl http://localhost:8001/health   # SAP
curl http://localhost:8002/health   # Oracle
curl http://localhost:8003/health   # Salesforce
curl http://localhost:8004/health   # AWS
curl http://localhost:8005/health   # GCP
curl http://localhost:8000/health   # Orchestrator
```

Send a test message to the orchestrator:

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Check stock levels for beef", "session_id": "test-001"}'
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
├── orchestrator/           # Master orchestrator (port 8000)
│   ├── app.py              # FastAPI app + /chat endpoint
│   ├── config.py           # Pydantic settings
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
