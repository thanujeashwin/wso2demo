"""agent.py — Warehouse Agent processing loop.

Receives order notifications from the Customer Agent and:
  1. Creates a pick-and-pack fulfilment task
  2. Assigns an available picker to the task
"""

from __future__ import annotations

import json
import logging
import re

from tools import TOOL_REGISTRY
from traces import start_span, trace_agent_step

logger   = logging.getLogger("warehouse_agent.agent")
_ORD_RE  = re.compile(r"ORD-\d{4,}", re.IGNORECASE)
_PROD_RE = re.compile(r"PROD-\d{3,}", re.IGNORECASE)
_QTY_RE  = re.compile(r"(\d+)\s*x?\s*(PROD-\d{3,})", re.IGNORECASE)


def run(message: str, session_id: str, context: dict | None = None) -> str:
    context  = context or {}

    with start_span("warehouse_agent.process", attributes={
        "session.id":    session_id,
        "agent.type":    "warehouse_agent",
        "input.message": message[:256],
    }):
        order_id = _extract_order_id(message)
        items    = _extract_items(message, context)

        if not items:
            return json.dumps({"status": "ok", "message": "No items to fulfil."})

        # Step 1 — Create fulfilment task
        task_raw = TOOL_REGISTRY["create_fulfilment_task"]["fn"](order_id=order_id, items=items)
        task     = json.loads(task_raw)
        trace_agent_step(1, f"create_fulfilment_task({order_id})", task_raw)
        logger.info("Created fulfilment task %s for order %s", task.get("task_id"), order_id)

        # Step 2 — Assign a picker
        task_id      = task.get("task_id", "")
        assign_raw   = TOOL_REGISTRY["assign_picker"]["fn"](task_id=task_id)
        assign_result = json.loads(assign_raw)
        trace_agent_step(2, f"assign_picker({task_id})", assign_raw)
        logger.info("Picker assignment: %s", assign_result.get("message"))

        return json.dumps({
            "status":      "ok",
            "order_id":    order_id,
            "task_id":     task_id,
            "picker":      assign_result.get("picker_name", "unassigned"),
            "task_status": assign_result.get("task_status", task.get("task_status")),
            "message":     f"Order {order_id} queued for picking by {assign_result.get('picker_name', 'next available picker')}.",
        })


def _extract_order_id(message: str) -> str:
    m = _ORD_RE.search(message)
    return m.group(0).upper() if m else "ORD-UNKNOWN"


def _extract_items(message: str, context: dict) -> list[dict]:
    if "items" in context:
        return context["items"]
    qty_matches = _QTY_RE.findall(message.upper())
    if qty_matches:
        return [{"product_id": p, "quantity": int(q)} for q, p in qty_matches]
    prod_matches = _PROD_RE.findall(message.upper())
    return [{"product_id": p, "quantity": 1} for p in prod_matches]
