"""demo_data.py — Mock inventory data for the Inventory Agent."""

INVENTORY: dict[str, dict] = {
    "PROD-001": {"name": "Whole Milk 2L",        "warehouse_stock": 1200, "reserved": 0, "reorder_point": 200, "supplier_id": "SUP-001"},
    "PROD-002": {"name": "Free Range Eggs 12pk", "warehouse_stock": 800,  "reserved": 0, "reorder_point": 150, "supplier_id": "SUP-002"},
    "PROD-003": {"name": "Sourdough Bread",      "warehouse_stock": 300,  "reserved": 0, "reorder_point": 100, "supplier_id": "SUP-003"},
    "PROD-004": {"name": "Chicken Breast 500g",  "warehouse_stock": 500,  "reserved": 0, "reorder_point": 100, "supplier_id": "SUP-001"},
    "PROD-005": {"name": "Cheddar Cheese 400g",  "warehouse_stock": 600,  "reserved": 0, "reorder_point": 100, "supplier_id": "SUP-002"},
    "PROD-006": {"name": "Butter 250g",          "warehouse_stock": 400,  "reserved": 0, "reorder_point": 80,  "supplier_id": "SUP-001"},
    "PROD-007": {"name": "Basmati Rice 1kg",     "warehouse_stock": 700,  "reserved": 0, "reorder_point": 120, "supplier_id": "SUP-003"},
}

# In-memory reservation log: {reservation_id: {order_id, product_id, quantity, status}}
RESERVATIONS: dict[str, dict] = {}

_res_counter = 0


def next_reservation_id() -> str:
    global _res_counter
    _res_counter += 1
    return f"RES-{_res_counter:04d}"
