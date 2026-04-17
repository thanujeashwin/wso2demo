"""agent.py — Supplier Agent processing loop.

Receives low-stock notifications from the Inventory Agent and
raises purchase orders with the appropriate supplier.
"""

from __future__ import annotations

import json
import logging
import re

from tools import TOOL_REGISTRY
from traces import start_span, trace_agent_step

logger   = logging.getLogger("supplier_agent.agent")
_PROD_RE = re.compile(r"PROD-\d{3,}", re.IGNORECASE)
_QTY_RE  = re.compile(r"(\d+)\s*x?\s*(PROD-\d{3,})", re.IGNORECASE)

_DEFAULT_REORDER_QTY = 500


def run(message: str, session_id: str, context: dict | None = None) -> str:
    context = context or {}

    with start_span("supplier_agent.process", attributes={
        "session.id":    session_id,
        "agent.type":    "supplier_agent",
        "input.message": message[:256],
    }):
        products = _extract_products(message, context)

        if not products:
            return json.dumps({"status": "ok", "message": "No reorder products identified."})

        purchase_orders = []
        for item in products:
            pid = item.get("product_id", "")
            qty = item.get("quantity", _DEFAULT_REORDER_QTY)

            # Step 1 — Get supplier info
            info_raw = TOOL_REGISTRY["get_supplier_info"]["fn"](product_id=pid)
            info     = json.loads(info_raw)
            trace_agent_step(1, f"get_supplier_info({pid})", info_raw)

            if info.get("status") != "ok":
                logger.warning("No supplier info for %s", pid)
                continue

            # Step 2 — Raise purchase order
            po_raw = TOOL_REGISTRY["raise_purchase_order"]["fn"](product_id=pid, quantity=qty)
            po     = json.loads(po_raw)
            trace_agent_step(2, f"raise_purchase_order({pid}, {qty})", po_raw)
            logger.info("PO raised: %s", po.get("message"))

            if po.get("status") == "ok":
                purchase_orders.append({
                    "po_id":      po["po_id"],
                    "product_id": pid,
                    "supplier":   po["supplier_name"],
                    "quantity":   po["quantity"],
                    "eta":        po["eta"],
                })

        return json.dumps({
            "status":          "ok",
            "purchase_orders": purchase_orders,
            "po_count":        len(purchase_orders),
            "message":         f"Raised {len(purchase_orders)} purchase order(s).",
        })


def _extract_products(message: str, context: dict) -> list[dict]:
    # Context may carry pre-parsed products from inventory agent
    if "products" in context:
        return [{"product_id": p.get("product_id"), "quantity": _DEFAULT_REORDER_QTY}
                for p in context["products"]]

    qty_matches = _QTY_RE.findall(message.upper())
    if qty_matches:
        return [{"product_id": p, "quantity": int(q)} for q, p in qty_matches]

    prod_matches = _PROD_RE.findall(message.upper())
    return [{"product_id": p, "quantity": _DEFAULT_REORDER_QTY} for p in prod_matches]
