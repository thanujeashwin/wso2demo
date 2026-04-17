"""demo_data.py — Mock warehouse data for the Warehouse Agent."""

PICKERS = {
    "PKR-001": {"name": "James R.",  "zone": "A", "available": True},
    "PKR-002": {"name": "Sarah M.",  "zone": "B", "available": True},
    "PKR-003": {"name": "David K.",  "zone": "A", "available": False},
    "PKR-004": {"name": "Emma T.",   "zone": "C", "available": True},
}

# In-memory fulfilment tasks: {task_id: task}
TASKS: dict[str, dict] = {}

_task_counter = 0


def next_task_id() -> str:
    global _task_counter
    _task_counter += 1
    return f"TASK-{_task_counter:04d}"
