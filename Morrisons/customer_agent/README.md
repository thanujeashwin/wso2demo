# Morrisons Customer Agent — WSO2 Agent Manager Demo

A customer-facing AI agent that lets shoppers **browse products, check stock, place orders, and track deliveries** via a natural-language chat interface. Built as part of the [Morrisons multi-agent demo](../README.md) for WSO2 Agent Manager.

> **Demo mode:** Uses a `DemoLLM` keyword router — no LLM API key required. Mock OpenTelemetry spans are emitted on every request, compatible with WSO2 Agent Manager's Traceloop instrumentation.

---

## What This Agent Does

| Customer asks… | Agent does… |
|---|---|
| "Show me what's available" | Browses the full product catalogue |
| "Show me dairy products" | Filters catalogue by category |
| "How many PROD-005 are in stock?" | Checks live stock levels |
| "Order 2 PROD-001 and 1 PROD-002" | Places an order, deducts stock, returns order ID |
| "Track my order ORD-9002" | Returns current status, ETA, and items |
| "Show my loyalty points" | Returns customer profile and order history |

---

## Architecture

```
Customer (Browser)
        │
        ▼
  GET /  ──────────────────────────────── static/index.html (WSO2-themed chat UI)
        │
  POST /chat  (ChatRequest)
        │
        ▼
┌──────────────────────────────────────────┐
│           FastAPI  app.py  :8000         │
│                                          │
│  ChatRequest { message, session_id,      │
│                context{customer_id} }    │
└──────────────────────┬───────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────┐
│       Custom ReAct Loop  agent.py        │
│                                          │
│  Observe ──▶ Think (DemoLLM) ──▶ Act    │
│     ▲                          │         │
│     └──────── Observe ◀────────┘         │
│                   │                      │
│              Respond                     │
└──────────────────────────────────────────┘
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
   browse_products  check_stock  place_order
   track_order      get_customer_profile
   (tools.py)
          │
          ▼
   demo_data.py  (in-memory product catalogue, stock, orders)
          │
          ▼
   traces.py  ──▶  [OTLP-SPAN] JSON to stdout
                   (ingested by WSO2 Agent Manager / Traceloop collector)
```

---

## Key Difference from Other Morrisons Agents

All other agents in this demo use **LangGraph** for their ReAct loop. This agent uses a **custom ReAct implementation** (`agent.py`) with no LangGraph dependency — demonstrating that WSO2 Agent Manager is framework-agnostic and works equally well with plain Python agents.

| | Other agents | Customer agent |
|---|---|---|
| ReAct framework | LangGraph StateGraph | Custom `Observe→Think→Act→Respond` loop |
| LLM abstraction | LangChain `BaseChatModel` | Plain Python `DemoLLM` class |
| Tool wrapping | `@tool` decorator (LangChain) | Plain functions + `@trace_tool` decorator |
| Traceloop | Auto-instrumented via LangGraph | Manual OTLP span emission via `traces.py` |
| Port | 8001–8005 | 8000 |

---

## Files

```
customer_agent/
├── app.py              FastAPI app — POST /chat, GET /health, GET /tools, GET /
├── agent.py            Custom ReAct loop + DemoLLM keyword router
├── tools.py            5 tool functions + TOOL_REGISTRY
├── demo_data.py        Mock product catalogue, stock levels, customers, orders
├── traces.py           Mock OpenTelemetry tracer (OTLP-style JSON to stdout)
├── requirements.txt    fastapi, uvicorn, pydantic
└── static/
    └── index.html      WSO2 orange-themed chat UI with trace log panel
```

---

## Tools

### `browse_products`
Returns the product catalogue, optionally filtered by category.

**Parameters:**

| Name | Type | Required | Description |
|---|---|---|---|
| `category` | string | No | One of: `dairy`, `meat`, `bakery`, `fruit`, `vegetables`, `eggs`, `canned`, `confectionery` |

**Example:**
```json
{ "category": "dairy" }
```

---

### `check_stock`
Returns the current stock level and availability status for a product.

**Parameters:**

| Name | Type | Required | Description |
|---|---|---|---|
| `product_id` | string | Yes | e.g. `PROD-001` |

**Availability statuses:** `in_stock` (>20 units), `low_stock` (1–20 units), `out_of_stock` (0 units)

---

### `place_order`
Places an order for one or more products. Deducts stock in memory and creates an order record.

**Parameters:**

| Name | Type | Required | Description |
|---|---|---|---|
| `customer_id` | string | Yes | e.g. `CUST-5001` |
| `items` | array | Yes | List of `{ "product_id": "PROD-001", "quantity": 2 }` |

Returns an order ID, line items, total, and estimated delivery time.

---

### `track_order`
Returns the current status and delivery details for an existing order.

**Parameters:**

| Name | Type | Required | Description |
|---|---|---|---|
| `order_id` | string | Yes | e.g. `ORD-9002` |

**Order statuses:** `confirmed`, `picking`, `out_for_delivery`, `delivered`, `cancelled`

---

### `get_customer_profile`
Returns a customer's name, email, loyalty tier, points balance, and recent order history.

**Parameters:**

| Name | Type | Required | Description |
|---|---|---|---|
| `customer_id` | string | Yes | e.g. `CUST-5001` |

---

## Demo Data

### Products (`PROD-001` – `PROD-010`)

| ID | Product | Category | Price |
|---|---|---|---|
| PROD-001 | Morrisons British Whole Milk 4pt | dairy | £1.65 |
| PROD-002 | Morrisons Free Range Eggs 12pk | eggs | £3.25 |
| PROD-003 | Hovis Best of Both 800g | bakery | £1.40 |
| PROD-004 | Lurpak Spreadable Butter 500g | dairy | £3.75 |
| PROD-005 | Morrisons Chicken Breast Fillets 600g | meat | £4.50 |
| PROD-006 | Morrisons Red Seedless Grapes 500g | fruit | £2.00 |
| PROD-007 | Cadbury Dairy Milk 200g | confectionery | £2.20 |
| PROD-008 | Morrisons Broccoli 400g | vegetables | £0.89 |
| PROD-009 | Heinz Baked Beans 415g | canned | £0.99 |
| PROD-010 | Morrisons Greek Style Yogurt 500g | dairy | £1.85 |

### Customers

| ID | Name | Loyalty Tier | Points |
|---|---|---|---|
| CUST-5001 | Emma Johnson | Gold | 4,320 |
| CUST-5002 | Liam Thompson | Silver | 1,780 |
| CUST-5003 | Sophie Williams | Bronze | 420 |

### Pre-seeded Orders

| ID | Customer | Status |
|---|---|---|
| ORD-9001 | CUST-5001 | delivered |
| ORD-9002 | CUST-5001 | out_for_delivery |
| ORD-9003 | CUST-5002 | confirmed |

---

## API Reference

### `POST /chat`

```json
Request:
{
  "message":    "Track my order ORD-9002",
  "session_id": "sess-abc123",
  "context": {
    "customer_id": "CUST-5001",
    "user_id":     "CUST-5001"
  }
}

Response:
{
  "reply":      "📦 Order ORD-9002 — Out for delivery\n\nCustomer: Emma Johnson\n...",
  "session_id": "sess-abc123",
  "agent":      "customer_agent",
  "port":       8000
}
```

### `GET /health`

```json
{ "status": "ok", "agent": "customer_agent", "version": "1.0.0" }
```

### `GET /tools`

Returns the full OpenAPI-style tool schema for all 5 registered tools.

---

## Running Locally

```bash
cd Morrisons/customer_agent
pip install -r requirements.txt
python app.py
```

Open **http://localhost:8000** for the chat UI.

To call the API directly:

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Show me dairy products",
    "session_id": "test-1",
    "context": { "customer_id": "CUST-5001" }
  }'
```

---

## Observability — Mock OTLP Spans

Every `/chat` request emits a hierarchy of OTLP-compatible spans to stdout:

```
agent:chat          ← root span (full request)
  llm:think         ← DemoLLM keyword routing decision
  tool:<name>       ← tool execution (e.g. tool:track_order)
  react:step:1      ← ReAct loop step
```

Each span includes:
- `traceId`, `spanId`, `parentSpanId`
- `startTimeNs`, `endTimeNs`, `durationMs`
- `status` (OK / ERROR)
- `attributes` (service name, tool name, session ID, input/output sizes)
- `events` (LLM prompt/response snippets, exceptions if any)

When deployed to WSO2 Agent Manager, stdout is captured by the platform's Traceloop collector and surfaced in the **Traces** view.

---

## WSO2 Agent Manager Deployment

### Agent Details

| Field | Value |
|---|---|
| Name | `Morrisons Customer Agent` |
| Description | `Customer-facing agent for browsing products, checking stock, placing orders and tracking deliveries` |

### Repository Details

| Field | Value |
|---|---|
| GitHub Repository | `https://github.com/thanujeashwin/wso2demo` |
| Branch | `main` |
| Project Path | `Morrisons/customer_agent` |

### Build Details

| Field | Value |
|---|---|
| Language | `Python` |
| Start Command | `python app.py` |
| Language Version | `3.11` |
| Enable auto instrumentation | ✅ checked |

### Agent Type

`Chat Agent` — standard chat interface with `POST /chat` on port 8000

### Environment Variables

| Key | Value | Secret |
|---|---|---|
| `PORT` | `8000` | ☐ |

> No API key needed — the agent runs fully in demo mode.

---

## Demo Scenarios (Quick Reference)

| Scenario | Example message |
|---|---|
| Browse all products | `Show me what products you have` |
| Filter by category | `Show me dairy products` |
| Check stock | `How many PROD-005 are in stock?` |
| Place an order | `I want to order 2 PROD-001 and 1 PROD-002` |
| Track an order | `Track my order ORD-9002` |
| View loyalty profile | `Show my loyalty points` |

All scenarios are also available as one-click shortcuts in the chat UI sidebar.

---

## Switching to a Real LLM

To replace `DemoLLM` with a real model, update `agent.py`:

```python
# In agent.py, replace the DemoLLM class with:
from anthropic import Anthropic

client = Anthropic()

def select_tool_with_llm(message: str) -> tuple[str, dict]:
    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=1024,
        tools=[...],   # pass TOOL_REGISTRY schemas
        messages=[{"role": "user", "content": message}],
    )
    # parse tool_use block from response
    ...
```

Then set `ANTHROPIC_API_KEY` in the environment. The rest of `app.py`, `tools.py`, and `traces.py` require no changes.
