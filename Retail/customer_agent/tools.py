"""tools.py — Customer-agent tool functions.

Each function is a plain Python callable (no LangGraph / LangChain decorator).
The custom ReAct loop in agent.py calls these directly.
Mock OpenTelemetry spans are emitted via traces.py.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import httpx

from demo_data import (
    PRODUCTS,
    STOCK,
    CUSTOMERS,
    ORDERS,
    CATEGORIES,
    products_by_category,
    next_order_id,
)
from traces import trace_tool

_logger = logging.getLogger("customer_agent.tools")


# ---------------------------------------------------------------------------
# Tool registry — agent.py looks here to resolve tool names
# ---------------------------------------------------------------------------

TOOL_REGISTRY: dict[str, dict] = {}


def _register(name: str, description: str, parameters: dict):
    """Decorator-style registration mirroring OpenAPI tool schema."""
    def decorator(fn):
        TOOL_REGISTRY[name] = {
            "name":        name,
            "description": description,
            "parameters":  parameters,
            "fn":          fn,
        }
        return fn
    return decorator


# ---------------------------------------------------------------------------
# 0. Guardrail check  (runs before every ReAct loop — appears in trace)
# ---------------------------------------------------------------------------

_SHOPPING_KEYWORDS = {
    "product", "products", "stock", "order", "orders", "buy", "purchase",
    "deliver", "delivery", "track", "tracking", "price", "browse", "list",
    "search", "category", "dairy", "meat", "bakery", "fruit", "vegetables",
    "eggs", "canned", "confectionery", "grocery", "groceries", "shop",
    "loyalty", "points", "tier", "profile", "account", "available",
    "milk", "butter", "bread", "chicken", "grapes", "chocolate", "broccoli",
    "beans", "yogurt", "morrisons", "freshmart",
    "hi", "hello", "hey", "thanks", "help", "prod-", "ord-", "cust-",
}

_OFF_TOPIC_KEYWORDS = {
    "recipe", "recipes", "cooking", "baking", "how to cook", "how to make",
    "instructions", "weather", "news", "politics", "sport", "sports",
    "movie", "movies", "music", "programming", "software", "javascript",
    "python", "bitcoin", "crypto", "invest", "translate",
}


@_register(
    name="guardrail_check",
    description="Validate that the customer message is within scope for the FreshMart shopping assistant before invoking the LLM.",
    parameters={
        "message": {"type": "string", "required": True},
    },
)
@trace_tool("guardrail_check")
def guardrail_check(message: str) -> str:
    text = message.lower()
    blocked = [kw for kw in _OFF_TOPIC_KEYWORDS if kw in text]
    allowed = [kw for kw in _SHOPPING_KEYWORDS  if kw in text]
    if blocked and not allowed:
        _logger.info("Guardrail BLOCKED — hits=%s", blocked)
        return json.dumps({
            "status":   "blocked",
            "reason":   "off_topic",
            "keywords": blocked,
            "message":  (
                "I'm sorry, I can only help with FreshMart grocery shopping — "
                "browsing products, checking stock, placing orders, and tracking deliveries. "
                "How can I help you shop today?"
            ),
        })
    _logger.info("Guardrail ALLOWED — blocked=%s allowed=%s", blocked, allowed)
    return json.dumps({"status": "allowed"})


# ---------------------------------------------------------------------------
# 1. Browse products
# ---------------------------------------------------------------------------

@_register(
    name="browse_products",
    description="Browse the available products, optionally filtered by category.",
    parameters={
        "category": {
            "type":        "string",
            "description": "Optional category to filter by (dairy, meat, bakery, fruit, vegetables, eggs, canned, confectionery).",
            "required":    False,
        }
    },
)
@trace_tool("browse_products")
def browse_products(category: str | None = None) -> str:
    items = products_by_category(category)
    if not items:
        return json.dumps({
            "status":  "no_results",
            "message": f"No products found in category '{category}'.",
        })
    return json.dumps({
        "status":     "ok",
        "categories": CATEGORIES,
        "count":      len(items),
        "products": [
            {
                "id":       p["id"],
                "name":     p["name"],
                "category": p["category"],
                "price":    p["price"],
                "unit":     p["unit"],
            }
            for p in items
        ],
    })


# ---------------------------------------------------------------------------
# 2. Check stock
# ---------------------------------------------------------------------------

@_register(
    name="check_stock",
    description="Check the current stock level for a specific product.",
    parameters={
        "product_id": {
            "type":        "string",
            "description": "The product ID (e.g. PROD-001).",
            "required":    True,
        }
    },
)
@trace_tool("check_stock")
def check_stock(product_id: str) -> str:
    product = PRODUCTS.get(product_id)
    if not product:
        return json.dumps({"status": "error", "message": f"Product '{product_id}' not found."})

    qty = STOCK.get(product_id, 0)
    availability = (
        "in_stock"      if qty > 20  else
        "low_stock"     if qty > 0   else
        "out_of_stock"
    )
    return json.dumps({
        "status":       "ok",
        "product_id":   product_id,
        "name":         product["name"],
        "units_available": qty,
        "availability": availability,
        "price":        product["price"],
        "unit":         product["unit"],
    })


# ---------------------------------------------------------------------------
# 3. Place order
# ---------------------------------------------------------------------------

@_register(
    name="place_order",
    description="Place an order for one or more products on behalf of the customer.",
    parameters={
        "customer_id": {
            "type":        "string",
            "description": "The customer ID (e.g. CUST-5001).",
            "required":    True,
        },
        "items": {
            "type":        "array",
            "description": "List of {product_id, quantity} objects.",
            "required":    True,
        },
    },
)
@trace_tool("place_order")
def place_order(customer_id: str, items: list[dict[str, Any]]) -> str:
    # Validate customer
    customer = CUSTOMERS.get(customer_id)
    if not customer:
        return json.dumps({"status": "error", "message": f"Customer '{customer_id}' not found."})

    order_items: list[dict] = []
    errors: list[str] = []
    total = 0.0

    for item in items:
        pid = item.get("product_id", "")
        qty = int(item.get("quantity", 1))

        product = PRODUCTS.get(pid)
        if not product:
            errors.append(f"Product '{pid}' not found.")
            continue

        available = STOCK.get(pid, 0)
        if available < qty:
            errors.append(
                f"Insufficient stock for '{product['name']}': "
                f"requested {qty}, available {available}."
            )
            continue

        # Deduct stock (in-memory)
        STOCK[pid] -= qty
        unit_price = product["price"]
        total += unit_price * qty
        order_items.append({
            "product_id": pid,
            "name":       product["name"],
            "quantity":   qty,
            "unit_price": unit_price,
            "line_total": round(unit_price * qty, 2),
        })

    if errors and not order_items:
        return json.dumps({"status": "error", "errors": errors})

    # Create order record
    oid = next_order_id()
    now = datetime.now(timezone.utc).isoformat()
    ORDERS[oid] = {
        "id":          oid,
        "customer_id": customer_id,
        "items":       order_items,
        "total":       round(total, 2),
        "status":      "confirmed",
        "placed_at":   now,
        "estimated_delivery": "Within 2–4 hours",
    }

    return json.dumps({
        "status":               "ok",
        "order_id":             oid,
        "customer_name":        customer["name"],
        "items":                order_items,
        "total":                round(total, 2),
        "order_status":         "confirmed",
        "estimated_delivery":   "Within 2–4 hours",
        "errors":               errors,  # partial failures if any
    })


# ---------------------------------------------------------------------------
# 4. Notify inventory agent (called programmatically after place_order)
# ---------------------------------------------------------------------------

@_register(
    name="notify_inventory_agent",
    description="Notify the inventory agent to reserve and process stock for a confirmed order.",
    parameters={
        "order_id":    {"type": "string", "required": True},
        "customer_id": {"type": "string", "required": True},
        "items":       {"type": "array",  "required": True, "description": "List of {product_id, quantity}"},
    },
)
@trace_tool("notify_inventory_agent")
def notify_inventory_agent(order_id: str, customer_id: str, items: list) -> str:
    url = os.environ.get("INVENTORY_AGENT_URL", "")
    if not url:
        return json.dumps({"status": "skipped", "reason": "INVENTORY_AGENT_URL not configured"})
    payload = {
        "message": (
            f"Order {order_id} confirmed for customer {customer_id}. "
            f"Items: {json.dumps(items)}. Please reserve and process stock."
        ),
        "session_id": order_id,
        "context": {"order_id": order_id, "customer_id": customer_id, "items": items},
    }
    try:
        resp = httpx.post(f"{url}/chat", json=payload, timeout=15.0)
        return json.dumps({"status": "ok", "agent": "inventory_agent", "http_status": resp.status_code})
    except Exception as exc:
        _logger.warning("notify_inventory_agent failed: %s", exc)
        return json.dumps({"status": "error", "message": str(exc)})


# ---------------------------------------------------------------------------
# 5. Notify warehouse agent (called programmatically after place_order)
# ---------------------------------------------------------------------------

@_register(
    name="notify_warehouse_agent",
    description="Notify the warehouse agent to prepare fulfilment for a confirmed order.",
    parameters={
        "order_id":    {"type": "string", "required": True},
        "customer_id": {"type": "string", "required": True},
        "items":       {"type": "array",  "required": True, "description": "List of {product_id, quantity}"},
    },
)
@trace_tool("notify_warehouse_agent")
def notify_warehouse_agent(order_id: str, customer_id: str, items: list) -> str:
    url = os.environ.get("WAREHOUSE_AGENT_URL", "")
    if not url:
        return json.dumps({"status": "skipped", "reason": "WAREHOUSE_AGENT_URL not configured"})
    payload = {
        "message": (
            f"Order {order_id} confirmed for customer {customer_id}. "
            f"Items: {json.dumps(items)}. Please prepare warehouse fulfilment."
        ),
        "session_id": order_id,
        "context": {"order_id": order_id, "customer_id": customer_id, "items": items},
    }
    try:
        resp = httpx.post(f"{url}/chat", json=payload, timeout=15.0)
        return json.dumps({"status": "ok", "agent": "warehouse_agent", "http_status": resp.status_code})
    except Exception as exc:
        _logger.warning("notify_warehouse_agent failed: %s", exc)
        return json.dumps({"status": "error", "message": str(exc)})


# ---------------------------------------------------------------------------
# 6. Track order
# ---------------------------------------------------------------------------

@_register(
    name="track_order",
    description="Get the current status and tracking details for an existing order.",
    parameters={
        "order_id": {
            "type":        "string",
            "description": "The order ID (e.g. ORD-9001).",
            "required":    True,
        }
    },
)
@trace_tool("track_order")
def track_order(order_id: str) -> str:
    order = ORDERS.get(order_id)
    if not order:
        return json.dumps({"status": "error", "message": f"Order '{order_id}' not found."})

    customer = CUSTOMERS.get(order.get("customer_id", ""), {})

    status_labels = {
        "confirmed":        "Order confirmed — being prepared",
        "picking":          "Items being picked in store",
        "out_for_delivery": "Out for delivery",
        "delivered":        "Delivered",
        "cancelled":        "Cancelled",
    }
    status = order.get("status", "unknown")

    return json.dumps({
        "status":      "ok",
        "order_id":    order_id,
        "customer":    customer.get("name", "unknown"),
        "order_status": status,
        "status_label": status_labels.get(status, status),
        "placed_at":   order.get("placed_at"),
        "items":       order.get("items", []),
        "total":       order.get("total"),
        "estimated_delivery": order.get("estimated_delivery"),
        "delivered_at":       order.get("delivered_at"),
    })


# ---------------------------------------------------------------------------
# 7. Get customer profile (used for personalisation / loyalty)
# ---------------------------------------------------------------------------

@_register(
    name="get_customer_profile",
    description="Retrieve the customer's profile, loyalty tier and points balance.",
    parameters={
        "customer_id": {
            "type":        "string",
            "description": "The customer ID (e.g. CUST-5001).",
            "required":    True,
        }
    },
)
@trace_tool("get_customer_profile")
def get_customer_profile(customer_id: str) -> str:
    customer = CUSTOMERS.get(customer_id)
    if not customer:
        return json.dumps({"status": "error", "message": f"Customer '{customer_id}' not found."})

    # Fetch their orders
    my_orders = [
        {"id": o["id"], "total": o["total"], "status": o["status"]}
        for o in ORDERS.values()
        if o.get("customer_id") == customer_id
    ]

    return json.dumps({
        "status":         "ok",
        "customer_id":    customer_id,
        "name":           customer["name"],
        "email":          customer["email"],
        "loyalty_tier":   customer["loyalty_tier"],
        "loyalty_points": customer["loyalty_points"],
        "recent_orders":  my_orders[-5:],  # last 5
    })
