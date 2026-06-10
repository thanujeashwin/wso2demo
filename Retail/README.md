# Retail AI Agent Demo — WSO2 Agent Manager

A suite of **four AI agents** built for **WSO2 Agent Manager**, demonstrating an async multi-agent architecture for a Retail supermarket chain. The agents cover the full order fulfilment pipeline — from customer-facing shopping through inventory reservation, warehouse pick-and-pack, and supplier restocking — emitting full observability traces via Traceloop on every request.

**LLM:** All agents use **Google Gemini** via the **WSO2 AI Gateway** (`GatewayLLM`). A deterministic `DemoLLM` keyword-router is used automatically as a local fallback when `GEMINILLM_URL` / `GEMINILLM_API_KEY` are not set, so the full ReAct pipeline runs and WSO2 Agent Manager emits traces exactly as it would in production.

---

## Architecture & Async Flow

```
  Customer (Browser)
        │
        ▼
┌──────────────────────────────────────────┐
│           Customer Agent                 │
│  browse_products · check_stock           │
│  place_order · track_order               │
│  GatewayLLM (Gemini) / DemoLLM fallback  │
└──────┬────────────────────────┬──────────┘
       │                        │
       │  on successful order placement
       │  (async, fire-and-forget)
       │                        │
       ▼                        ▼
┌──────────────────┐   ┌──────────────────────┐
│ Inventory Agent  │   │   Warehouse Agent    │
│ reserve_stock    │   │ create_fulfilment    │
│ check_levels     │   │ assign_picker        │
│ Gemini / Demo    │   │ Gemini / Demo        │
└──────┬───────────┘   └──────────────────────┘
       │
       │  if any product < reorder point
       │  (async, fire-and-forget)
       ▼
┌──────────────────────┐
│    Supplier Agent    │
│  get_supplier_info   │
│  raise_purchase_order│
│  Gemini / Demo       │
└──────────────────────┘
```

**How the async chain works:**
1. Customer places an order → `customer_agent` confirms immediately and fires background POSTs to `inventory_agent` and `warehouse_agent` in parallel.
2. `inventory_agent` reserves warehouse stock, then checks inventory levels for each ordered product. If any product is below its reorder point, it fires a background POST to `supplier_agent`.
3. `supplier_agent` retrieves supplier info and raises a purchase order.
4. `warehouse_agent` creates a pick-and-pack fulfilment task and assigns an available picker.

None of the background steps block the customer response. Each agent produces its own independent trace tree in WSO2 Agent Manager.

---

## Agents

### Customer Agent (`customer_agent/`)

Customer-facing shopping assistant. Handles product browsing, stock checks, order placement, and order tracking. On a successful order, fires async notifications to `inventory_agent` and `warehouse_agent` in background threads — the customer receives their confirmation immediately.

**Tools:**
| Tool | Description |
|---|---|
| `browse_products` | List products, optionally filtered by category |
| `check_stock` | Current stock level for a product |
| `place_order` | Place an order; triggers async inventory + warehouse notifications |
| `track_order` | Status and tracking info for an existing order |
| `get_customer_profile` | Customer profile, loyalty tier, and recent orders |

**Demo products:** `PROD-001` – `PROD-020` across dairy, meat, bakery, fruit, vegetables, eggs, canned, confectionery
**Demo customers:** `CUST-5001` – `CUST-5006`

---

### Inventory Agent (`inventory_agent/`)

Triggered asynchronously by `customer_agent` on order placement. Reserves warehouse stock for the order, then checks inventory levels for each item. If any product falls below its reorder point, fires a background notification to `supplier_agent`.

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

Each agent uses a custom ReAct loop. The LLM is selected at startup:

```
GEMINILLM_URL + GEMINILLM_API_KEY set?
  ├── Yes → GatewayLLM (Gemini via WSO2 AI Gateway)
  └── No  → DemoLLM (deterministic keyword-router, no API key needed)
```

```
Incoming /chat request
        │
        ▼
  LLM.select_tool()   ← Gemini or DemoLLM
  Selects tool + args from message
        │
        ▼
  Tool execution → returns mock data
        │
        ▼
  LLM.synthesise()    ← Gemini or DemoLLM
  Produces natural-language response
        │
        ▼
  FastAPI returns { "response": "..." }

  [customer_agent only — if place_order succeeded]
        │
        ├──→ background thread → POST inventory_agent/chat
        └──→ background thread → POST warehouse_agent/chat
                                        │
                              [if stock < reorder point]
                                        │
                                        └──→ background thread → POST supplier_agent/chat
```

Every step emits Traceloop spans: LLM call, tool execution, FastAPI request/response.

---

## WSO2 Agent Manager Configuration

Each agent is deployed via **Create a Platform-Hosted Agent** in Agent Manager (Agent Details → Repository Details → Build Details → Agent Type).

> **Deploy order:** `supplier_agent` first, then `inventory_agent` and `warehouse_agent`, then `customer_agent` last.

> **Port:** Set `PORT` = `8000` as an environment variable for every agent.

---

### Agent 1 — Supplier Agent

> Deploy first — no upstream dependencies.

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

### Agent 2 — Inventory Agent

> Deploy after `supplier_agent`.

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

### Agent 3 — Warehouse Agent

> Deploy alongside `inventory_agent` — no upstream dependencies.

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

### Agent 4 — Customer Agent

> Deploy last — needs `INVENTORY_AGENT_URL` and `WAREHOUSE_AGENT_URL`.

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

## Request / Response schema (all agents)

```
POST /chat
Request:  { "message": string, "session_id": string, "context": object }
Response: { "response": string }

GET /health
Response: { "status": "ok", "agent": "<agent-name>" }
```

---

## Local Demo Web App

A standalone retail-themed web app (`demo-webapp/`) lets you interact with the Customer Agent from your browser. It proxies requests to the WSO2 AI Gateway to work around CORS restrictions.

### Prerequisites

- WSO2 Agent Manager running locally (k3d) with the Customer Agent deployed
- Gateway URL available at `http://default-default.openchoreoapis.localhost:19080/`
- Python 3 installed

### Running the Demo

Open **two terminal windows** and run:

```bash
# Terminal 1 — CORS proxy (forwards browser requests to the AI Gateway)
cd Retail/demo-webapp
python3 proxy.py
# Listens on http://localhost:8010
# Proxies → http://default-default.openchoreoapis.localhost:19080/customer-agent-customer-agent-endpoint
```

```bash
# Terminal 2 — static file server for the web app
cd Retail/demo-webapp
python3 -m http.server 9999
```

Then open **http://localhost:9999** in Chrome.

> **Why a proxy?** The gateway only allows `Origin: http://localhost:3000`. The proxy strips and rewrites CORS headers so any local origin can reach it.

---

## Running Locally (without Agent Manager)

```bash
# Install dependencies (per agent)
cd supplier_agent && pip install -r requirements.txt && cd ..

# Start all four agents (each binds to :8000 in its own container;
# use different PORT values when running locally side-by-side)
PORT=8003 python supplier_agent/main.py &
PORT=8001 SUPPLIER_AGENT_URL=http://localhost:8003 python inventory_agent/main.py &
PORT=8002 python warehouse_agent/main.py &
PORT=8000 INVENTORY_AGENT_URL=http://localhost:8001 WAREHOUSE_AGENT_URL=http://localhost:8002 python customer_agent/main.py
```

Set `GEMINILLM_URL` and `GEMINILLM_API_KEY` on each agent to use Gemini; omit them to fall back to `DemoLLM`.

---

## Repository Structure

```
wso2demo/
└── Retail/
    ├── README.md
    ├── demo-webapp/                # Standalone local demo — run from here for presentations
    │   ├── index.html              # FreshMart retail web app (talks to Customer Agent)
    │   └── proxy.py                # CORS proxy — forwards localhost:8010 → AI Gateway:19080
    ├── demo-presentation/          # Slide deck for presenting the demo
    │   └── retail_agentic_demo.pptx
    ├── customer_agent/             # Customer shopping agent — triggers inventory + warehouse async
    │   ├── app.py                  # FastAPI app + /chat endpoint + CORS middleware
    │   ├── agent.py                # Custom ReAct loop + guardrail + GatewayLLM/DemoLLM
    │   ├── tools.py                # browse_products, check_stock, place_order, track_order, guardrail_check
    │   ├── demo_data.py            # Mock product catalogue, stock, customers, orders
    │   ├── traces.py               # OTLP span emitter + @trace_tool decorator
    │   ├── main.py                 # uvicorn entry point
    │   ├── requirements.txt
    │   └── static/index.html       # Embedded chat UI (served at GET /)
    ├── inventory_agent/            # Reserves stock, triggers supplier when stock is low
    │   ├── app.py
    │   ├── agent.py                # Custom ReAct loop + GatewayLLM/DemoLLM + supplier notification
    │   ├── tools.py                # reserve_stock, check_inventory_levels, release_reservation
    │   ├── demo_data.py
    │   ├── traces.py
    │   ├── main.py
    │   └── requirements.txt
    ├── warehouse_agent/            # Pick-and-pack fulfilment
    │   ├── app.py
    │   ├── agent.py                # Custom ReAct loop + GatewayLLM/DemoLLM
    │   ├── tools.py                # create_fulfilment_task, assign_picker, update_dispatch_status
    │   ├── demo_data.py
    │   ├── traces.py
    │   ├── main.py
    │   └── requirements.txt
    └── supplier_agent/             # Raises purchase orders on low-stock alerts
        ├── app.py
        ├── agent.py                # Custom ReAct loop + GatewayLLM/DemoLLM
        ├── tools.py                # get_supplier_info, raise_purchase_order
        ├── demo_data.py
        ├── traces.py
        ├── main.py
        └── requirements.txt
```

---

## Observability

WSO2 Agent Manager injects **Traceloop** via `sitecustomize.py` at startup. No OTEL initialisation code is needed in the agents.

Every request generates spans for:
- LLM call (`GatewayLLM` or `DemoLLM`)
- Tool execution (per tool)
- FastAPI request/response

Traces are visible in **Runtime Logs** and **Traces** in Agent Manager. The async background notifications to downstream agents each produce their own independent trace tree, so you can see the full order-to-restock chain across four agents in a single demo.
