"""tools.py — Customer-agent tool functions.

Each function is a plain Python callable (no LangGraph / LangChain decorator).
The custom ReAct loop in agent.py calls these directly.
Mock OpenTelemetry spans are emitted via traces.py.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from demo_data import (
    PRODUCTS,
    STOCK,
    CUSTOMERS,
    ORDERS,
    CATEGORIES,
    products_by_category,
    next_order_id,
)
from traces import tracer, trace_tool


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
# 4. Track order
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
# 5. Get customer profile (used for personalisation / loyalty)
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
