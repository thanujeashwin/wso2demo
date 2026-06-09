"""tools.py — Supplier Agent tool functions."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from demo_data import SUPPLIERS, PRODUCT_SUPPLIER_MAP, PURCHASE_ORDERS, next_po_id
from traces import trace_tool

TOOL_REGISTRY: dict[str, dict] = {}


def _register(name: str, description: str, parameters: dict):
    def decorator(fn):
        TOOL_REGISTRY[name] = {"name": name, "description": description, "parameters": parameters, "fn": fn}
        return fn
    return decorator


@_register(
    name="raise_purchase_order",
    description="Raise a purchase order with the supplier for a product that needs restocking.",
    parameters={
        "product_id": {"type": "string",  "required": True,  "description": "Product ID e.g. PROD-001"},
        "quantity":   {"type": "integer", "required": True,  "description": "Quantity to order"},
    },
)
@trace_tool("raise_purchase_order")
def raise_purchase_order(product_id: str, quantity: int) -> str:
    mapping  = PRODUCT_SUPPLIER_MAP.get(product_id)
    if not mapping:
        return json.dumps({"status": "error", "message": f"No supplier found for product {product_id}."})

    supplier_id = mapping["supplier_id"]
    supplier    = SUPPLIERS.get(supplier_id)
    if not supplier:
        return json.dumps({"status": "error", "message": f"Supplier {supplier_id} not found."})

    # Enforce minimum order quantity
    qty      = max(quantity, mapping["min_order_qty"])
    po_id    = next_po_id()
    now      = datetime.now(timezone.utc)
    eta      = (now + timedelta(days=supplier["lead_time_days"])).date().isoformat()
    total    = round(qty * mapping["unit_cost"], 2)

    PURCHASE_ORDERS[po_id] = {
        "po_id":       po_id,
        "product_id":  product_id,
        "supplier_id": supplier_id,
        "quantity":    qty,
        "unit_cost":   mapping["unit_cost"],
        "total_cost":  total,
        "status":      "raised",
        "raised_at":   now.isoformat(),
        "eta":         eta,
    }

    return json.dumps({
        "status":        "ok",
        "po_id":         po_id,
        "product_id":    product_id,
        "supplier_name": supplier["name"],
        "quantity":      qty,
        "total_cost":    total,
        "eta":           eta,
        "message":       f"PO {po_id} raised with {supplier['name']} for {qty} units of {product_id}. ETA: {eta}.",
    })


@_register(
    name="get_supplier_info",
    description="Get supplier details and lead time for a product.",
    parameters={
        "product_id": {"type": "string", "required": True, "description": "Product ID e.g. PROD-001"},
    },
)
@trace_tool("get_supplier_info")
def get_supplier_info(product_id: str) -> str:
    mapping = PRODUCT_SUPPLIER_MAP.get(product_id)
    if not mapping:
        return json.dumps({"status": "error", "message": f"No supplier mapping for {product_id}."})

    supplier = SUPPLIERS.get(mapping["supplier_id"], {})
    return json.dumps({
        "status":          "ok",
        "product_id":      product_id,
        "supplier_id":     mapping["supplier_id"],
        "supplier_name":   supplier.get("name"),
        "contact":         supplier.get("contact"),
        "lead_time_days":  supplier.get("lead_time_days"),
        "unit_cost":       mapping["unit_cost"],
        "min_order_qty":   mapping["min_order_qty"],
    })
