"""agent.py — Inventory Agent processing loop.

Receives order notifications from the Customer Agent and:
  1. Reserves warehouse stock for the order items
  2. Checks if any items have dropped below reorder point
  3. Notifies the Supplier Agent if reorder is needed (fire-and-forget)
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading

import httpx

from tools import TOOL_REGISTRY
from traces import start_span, trace_agent_step

logger = logging.getLogger("inventory_agent.agent")

_SUPPLIER_AGENT_URL = os.environ.get("SUPPLIER_AGENT_URL", "http://supplier-agent:8000")

_ORD_RE  = re.compile(r"ORD-\d{4,}", re.IGNORECASE)
_PROD_RE = re.compile(r"PROD-\d{3,}", re.IGNORECASE)
_QTY_RE  = re.compile(r"(\d+)\s*x?\s*(PROD-\d{3,})", re.IGNORECASE)


def run(message: str, session_id: str, context: dict | None = None) -> str:
    context = context or {}

    with start_span("inventory_agent.process", attributes={
        "session.id":    session_id,
        "agent.type":    "inventory_agent",
        "input.message": message[:256],
    }):
        # Parse order_id and items from the notification message
        order_id = _extract_order_id(message)
        items    = _extract_items(message, context)

        if not items:
            logger.info("No items found in message — skipping reservation")
            return json.dumps({"status": "ok", "message": "No items to reserve."})

        # Step 1 — Reserve stock
        result_raw = TOOL_REGISTRY["reserve_stock"]["fn"](order_id=order_id, items=items)
        result     = json.loads(result_raw)
        trace_agent_step(1, f"reserve_stock({order_id})", result_raw)
        logger.info("Reserved stock for %s: %s", order_id, result.get("message"))

        # Step 2 — Check levels and notify supplier if reorder needed
        reorder_products = []
        for item in items:
            pid       = item.get("product_id", "")
            lvl_raw   = TOOL_REGISTRY["check_inventory_levels"]["fn"](product_id=pid)
            lvl       = json.loads(lvl_raw)
            trace_agent_step(2, f"check_inventory_levels({pid})", lvl_raw)

            if lvl.get("needs_reorder"):
                reorder_products.append({
                    "product_id":  pid,
                    "supplier_id": lvl.get("supplier_id"),
                    "available":   lvl.get("available"),
                    "reorder_point": lvl.get("reorder_point"),
                })

        # Step 3 — Fire-and-forget to Supplier Agent if reorder needed
        if reorder_products:
            _notify_supplier(order_id, reorder_products)

        return json.dumps({
            "status":           result.get("status"),
            "order_id":         order_id,
            "reserved":         result.get("reserved", []),
            "reorder_triggered": len(reorder_products),
            "message":          result.get("message"),
        })


def _notify_supplier(order_id: str, products: list[dict]) -> None:
    """Fire-and-forget notification to the Supplier Agent."""
    url     = f"{_SUPPLIER_AGENT_URL}/chat"
    message = (
        f"Reorder needed after order {order_id}. "
        f"Low stock products: {json.dumps(products)}"
    )

    with start_span("agent.notify.supplier-agent", attributes={
        "agent.target":        "supplier-agent",
        "order.id":            order_id,
        "notify.url":          url,
        "notify.async":        True,
        "reorder.product_count": len(products),
    }):
        pass  # span records the dispatch intent immediately

    def _call():
        try:
            resp = httpx.post(
                url,
                json={"message": message, "session_id": f"inv-notify-{order_id}"},
                timeout=10.0,
            )
            logger.info("Notified supplier-agent for reorder — status %d", resp.status_code)
        except Exception as exc:
            logger.warning("Failed to notify supplier-agent: %s", exc)

    threading.Thread(target=_call, daemon=True).start()


# ── helpers ──────────────────────────────────────────────────────────────────

def _extract_order_id(message: str) -> str:
    m = _ORD_RE.search(message)
    return m.group(0).upper() if m else "ORD-UNKNOWN"


def _extract_items(message: str, context: dict) -> list[dict]:
    # Items may come in context (preferred) or be parsed from the message
    if "items" in context:
        return context["items"]

    qty_matches = _QTY_RE.findall(message.upper())
    if qty_matches:
        return [{"product_id": p, "quantity": int(q)} for q, p in qty_matches]

    prod_matches = _PROD_RE.findall(message.upper())
    return [{"product_id": p, "quantity": 1} for p in prod_matches]
