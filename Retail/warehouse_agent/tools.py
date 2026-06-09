"""tools.py — Warehouse Agent tool functions."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from demo_data import PICKERS, TASKS, next_task_id
from traces import trace_tool

TOOL_REGISTRY: dict[str, dict] = {}


def _register(name: str, description: str, parameters: dict):
    def decorator(fn):
        TOOL_REGISTRY[name] = {"name": name, "description": description, "parameters": parameters, "fn": fn}
        return fn
    return decorator


@_register(
    name="create_fulfilment_task",
    description="Create a pick-and-pack fulfilment task for a customer order.",
    parameters={
        "order_id": {"type": "string", "required": True,  "description": "Customer order ID"},
        "items":    {"type": "array",  "required": True,  "description": "List of {product_id, quantity}"},
    },
)
@trace_tool("create_fulfilment_task")
def create_fulfilment_task(order_id: str, items: list[dict[str, Any]]) -> str:
    task_id = next_task_id()
    now     = datetime.now(timezone.utc).isoformat()

    TASKS[task_id] = {
        "task_id":    task_id,
        "order_id":   order_id,
        "items":      items,
        "status":     "pending",
        "picker_id":  None,
        "created_at": now,
    }

    return json.dumps({
        "status":    "ok",
        "task_id":   task_id,
        "order_id":  order_id,
        "item_count": len(items),
        "task_status": "pending",
        "message":   f"Fulfilment task {task_id} created for order {order_id}.",
    })


@_register(
    name="assign_picker",
    description="Assign an available picker to a fulfilment task.",
    parameters={
        "task_id": {"type": "string", "required": True, "description": "Fulfilment task ID"},
    },
)
@trace_tool("assign_picker")
def assign_picker(task_id: str) -> str:
    task = TASKS.get(task_id)
    if not task:
        return json.dumps({"status": "error", "message": f"Task {task_id} not found."})

    # Find an available picker
    picker_id = next((pid for pid, p in PICKERS.items() if p["available"]), None)
    if not picker_id:
        return json.dumps({"status": "error", "message": "No pickers available right now."})

    PICKERS[picker_id]["available"] = False
    task["picker_id"] = picker_id
    task["status"]    = "picking"

    return json.dumps({
        "status":      "ok",
        "task_id":     task_id,
        "order_id":    task["order_id"],
        "picker_id":   picker_id,
        "picker_name": PICKERS[picker_id]["name"],
        "task_status": "picking",
        "message":     f"Picker {PICKERS[picker_id]['name']} assigned to task {task_id}.",
    })


@_register(
    name="update_dispatch_status",
    description="Update the dispatch status of a fulfilment task.",
    parameters={
        "task_id": {"type": "string", "required": True, "description": "Fulfilment task ID"},
        "status":  {"type": "string", "required": True, "description": "New status: picking | packed | dispatched | delivered"},
    },
)
@trace_tool("update_dispatch_status")
def update_dispatch_status(task_id: str, status: str) -> str:
    task = TASKS.get(task_id)
    if not task:
        return json.dumps({"status": "error", "message": f"Task {task_id} not found."})

    old_status  = task["status"]
    task["status"] = status
    now         = datetime.now(timezone.utc).isoformat()

    if status == "dispatched":
        task["dispatched_at"] = now
    elif status == "delivered":
        task["delivered_at"] = now
        # Free up the picker
        if task.get("picker_id") and task["picker_id"] in PICKERS:
            PICKERS[task["picker_id"]]["available"] = True

    return json.dumps({
        "status":      "ok",
        "task_id":     task_id,
        "order_id":    task["order_id"],
        "old_status":  old_status,
        "task_status": status,
        "updated_at":  now,
    })
