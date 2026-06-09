"""tools.py — Inventory Agent tool functions."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from demo_data import INVENTORY, RESERVATIONS, next_reservation_id
from traces import trace_tool

TOOL_REGISTRY: dict[str, dict] = {}


def _register(name: str, description: str, parameters: dict):
    def decorator(fn):
        TOOL_REGISTRY[name] = {"name": name, "description": description, "parameters": parameters, "fn": fn}
        return fn
    return decorator


@_register(
    name="reserve_stock",
    description="Reserve warehouse stock for a confirmed customer order.",
    parameters={
        "order_id":  {"type": "string", "required": True,  "description": "Customer order ID e.g. ORD-9001"},
        "items":     {"type": "array",  "required": True,  "description": "List of {product_id, quantity}"},
    },
)
@trace_tool("reserve_stock")
def reserve_stock(order_id: str, items: list[dict[str, Any]]) -> str:
    reserved = []
    errors   = []

    for item in items:
        pid = item.get("product_id", "")
        qty = int(item.get("quantity", 1))
        inv = INVENTORY.get(pid)

        if not inv:
            errors.append(f"Product {pid} not in inventory.")
            continue

        available = inv["warehouse_stock"] - inv["reserved"]
        if available < qty:
            errors.append(f"Insufficient warehouse stock for {pid}: need {qty}, available {available}.")
            continue

        inv["reserved"] += qty
        rid = next_reservation_id()
        RESERVATIONS[rid] = {
            "reservation_id": rid,
            "order_id":       order_id,
            "product_id":     pid,
            "product_name":   inv["name"],
            "quantity":       qty,
            "status":         "reserved",
            "reserved_at":    datetime.now(timezone.utc).isoformat(),
        }
        reserved.append({"reservation_id": rid, "product_id": pid, "quantity": qty})

    return json.dumps({
        "status":     "ok" if reserved else "error",
        "order_id":   order_id,
        "reserved":   reserved,
        "errors":     errors,
        "message":    f"Reserved {len(reserved)} line(s) for order {order_id}.",
    })


@_register(
    name="check_inventory_levels",
    description="Check current warehouse stock level for a product.",
    parameters={
        "product_id": {"type": "string", "required": True, "description": "Product ID e.g. PROD-001"},
    },
)
@trace_tool("check_inventory_levels")
def check_inventory_levels(product_id: str) -> str:
    inv = INVENTORY.get(product_id)
    if not inv:
        return json.dumps({"status": "error", "message": f"Product {product_id} not found."})

    available = inv["warehouse_stock"] - inv["reserved"]
    low       = available <= inv["reorder_point"]

    return json.dumps({
        "status":          "ok",
        "product_id":      product_id,
        "name":            inv["name"],
        "warehouse_stock": inv["warehouse_stock"],
        "reserved":        inv["reserved"],
        "available":       available,
        "reorder_point":   inv["reorder_point"],
        "needs_reorder":   low,
        "supplier_id":     inv["supplier_id"],
    })


@_register(
    name="release_reservation",
    description="Release a stock reservation (e.g. order cancelled).",
    parameters={
        "order_id": {"type": "string", "required": True, "description": "Order ID to release reservations for"},
    },
)
@trace_tool("release_reservation")
def release_reservation(order_id: str) -> str:
    released = []
    for rid, res in list(RESERVATIONS.items()):
        if res["order_id"] == order_id and res["status"] == "reserved":
            pid = res["product_id"]
            if pid in INVENTORY:
                INVENTORY[pid]["reserved"] -= res["quantity"]
            res["status"] = "released"
            released.append(rid)

    return json.dumps({
        "status":   "ok",
        "order_id": order_id,
        "released": released,
        "message":  f"Released {len(released)} reservation(s) for order {order_id}.",
    })
