"""demo_data.py — Mock supplier data for the Supplier Agent."""

SUPPLIERS = {
    "SUP-001": {"name": "Freshfields Dairy",     "contact": "orders@freshfields.co.uk", "lead_time_days": 1},
    "SUP-002": {"name": "Golden Egg Co.",         "contact": "supply@goldenegg.co.uk",   "lead_time_days": 2},
    "SUP-003": {"name": "Artisan Bakes Ltd",      "contact": "trade@artisanbakes.co.uk", "lead_time_days": 1},
}

PRODUCT_SUPPLIER_MAP = {
    "PROD-001": {"supplier_id": "SUP-001", "unit_cost": 0.85, "min_order_qty": 100},
    "PROD-002": {"supplier_id": "SUP-002", "unit_cost": 1.20, "min_order_qty": 50},
    "PROD-003": {"supplier_id": "SUP-003", "unit_cost": 0.65, "min_order_qty": 50},
    "PROD-004": {"supplier_id": "SUP-001", "unit_cost": 2.10, "min_order_qty": 20},
    "PROD-005": {"supplier_id": "SUP-002", "unit_cost": 1.50, "min_order_qty": 30},
    "PROD-006": {"supplier_id": "SUP-001", "unit_cost": 0.90, "min_order_qty": 50},
    "PROD-007": {"supplier_id": "SUP-003", "unit_cost": 0.70, "min_order_qty": 40},
}

# In-memory purchase orders
PURCHASE_ORDERS: dict[str, dict] = {}

_po_counter = 0


def next_po_id() -> str:
    global _po_counter
    _po_counter += 1
    return f"PO-{_po_counter:04d}"
