"""demo_data.py — Mock product catalog, stock levels, customer records and orders."""

from __future__ import annotations
from datetime import datetime, timedelta, timezone

# ---------------------------------------------------------------------------
# Product catalogue
# ---------------------------------------------------------------------------
PRODUCTS: dict[str, dict] = {
    "PROD-001": {
        "id": "PROD-001",
        "name": "Morrisons British Whole Milk 4pt",
        "category": "dairy",
        "price": 1.65,
        "unit": "bottle",
        "description": "Fresh semi-skimmed whole milk from British farms",
    },
    "PROD-002": {
        "id": "PROD-002",
        "name": "Morrisons Free Range Eggs 12pk",
        "category": "eggs",
        "price": 3.25,
        "unit": "pack",
        "description": "12 free-range large eggs, barn reared",
    },
    "PROD-003": {
        "id": "PROD-003",
        "name": "Hovis Best of Both 800g",
        "category": "bakery",
        "price": 1.40,
        "unit": "loaf",
        "description": "White bread with wholemeal goodness",
    },
    "PROD-004": {
        "id": "PROD-004",
        "name": "Lurpak Spreadable Butter 500g",
        "category": "dairy",
        "price": 3.75,
        "unit": "tub",
        "description": "Spreadable butter blend, slightly salted",
    },
    "PROD-005": {
        "id": "PROD-005",
        "name": "Morrisons Chicken Breast Fillets 600g",
        "category": "meat",
        "price": 4.50,
        "unit": "pack",
        "description": "British chicken breast fillets, skinless",
    },
    "PROD-006": {
        "id": "PROD-006",
        "name": "Morrisons Red Seedless Grapes 500g",
        "category": "fruit",
        "price": 2.00,
        "unit": "bag",
        "description": "Sweet red seedless grapes, South Africa",
    },
    "PROD-007": {
        "id": "PROD-007",
        "name": "Cadbury Dairy Milk 200g",
        "category": "confectionery",
        "price": 2.20,
        "unit": "bar",
        "description": "Classic milk chocolate bar",
    },
    "PROD-008": {
        "id": "PROD-008",
        "name": "Morrisons Broccoli 400g",
        "category": "vegetables",
        "price": 0.89,
        "unit": "head",
        "description": "Fresh British broccoli",
    },
    "PROD-009": {
        "id": "PROD-009",
        "name": "Heinz Baked Beans 415g",
        "category": "canned",
        "price": 0.99,
        "unit": "can",
        "description": "Heinz baked beans in tomato sauce",
    },
    "PROD-010": {
        "id": "PROD-010",
        "name": "Morrisons Greek Style Yogurt 500g",
        "category": "dairy",
        "price": 1.85,
        "unit": "pot",
        "description": "Thick and creamy Greek style yogurt",
    },
}

# ---------------------------------------------------------------------------
# Stock levels  (units in store)
# ---------------------------------------------------------------------------
STOCK: dict[str, int] = {
    "PROD-001": 142,
    "PROD-002": 88,
    "PROD-003": 213,
    "PROD-004": 57,
    "PROD-005": 34,
    "PROD-006": 96,
    "PROD-007": 251,
    "PROD-008": 71,
    "PROD-009": 189,
    "PROD-010": 62,
}

# ---------------------------------------------------------------------------
# Customer records
# ---------------------------------------------------------------------------
CUSTOMERS: dict[str, dict] = {
    "CUST-5001": {
        "id": "CUST-5001",
        "name": "Emma Johnson",
        "email": "emma.j@example.com",
        "loyalty_tier": "Gold",
        "loyalty_points": 4320,
    },
    "CUST-5002": {
        "id": "CUST-5002",
        "name": "Liam Thompson",
        "email": "liam.t@example.com",
        "loyalty_tier": "Silver",
        "loyalty_points": 1780,
    },
    "CUST-5003": {
        "id": "CUST-5003",
        "name": "Sophie Williams",
        "email": "sophie.w@example.com",
        "loyalty_tier": "Bronze",
        "loyalty_points": 420,
    },
}

# ---------------------------------------------------------------------------
# Order history (in-memory, mutable — new orders appended at runtime)
# ---------------------------------------------------------------------------
_now = datetime.now(timezone.utc)

ORDERS: dict[str, dict] = {
    "ORD-9001": {
        "id": "ORD-9001",
        "customer_id": "CUST-5001",
        "items": [
            {"product_id": "PROD-001", "quantity": 2, "unit_price": 1.65},
            {"product_id": "PROD-002", "quantity": 1, "unit_price": 3.25},
        ],
        "total": 6.55,
        "status": "delivered",
        "placed_at": (_now - timedelta(days=3)).isoformat(),
        "delivered_at": (_now - timedelta(days=1)).isoformat(),
    },
    "ORD-9002": {
        "id": "ORD-9002",
        "customer_id": "CUST-5001",
        "items": [
            {"product_id": "PROD-005", "quantity": 1, "unit_price": 4.50},
            {"product_id": "PROD-008", "quantity": 2, "unit_price": 0.89},
        ],
        "total": 6.28,
        "status": "out_for_delivery",
        "placed_at": (_now - timedelta(hours=6)).isoformat(),
        "estimated_delivery": (_now + timedelta(hours=2)).isoformat(),
    },
    "ORD-9003": {
        "id": "ORD-9003",
        "customer_id": "CUST-5002",
        "items": [
            {"product_id": "PROD-007", "quantity": 3, "unit_price": 2.20},
        ],
        "total": 6.60,
        "status": "confirmed",
        "placed_at": (_now - timedelta(minutes=45)).isoformat(),
        "estimated_delivery": (_now + timedelta(hours=4)).isoformat(),
    },
}

# Counter for new order IDs
_order_counter: int = 9004


def next_order_id() -> str:
    global _order_counter
    oid = f"ORD-{_order_counter}"
    _order_counter += 1
    return oid


# ---------------------------------------------------------------------------
# Category listing helper
# ---------------------------------------------------------------------------
def products_by_category(category: str | None = None) -> list[dict]:
    """Return all products, optionally filtered by category."""
    if category:
        return [p for p in PRODUCTS.values() if p["category"] == category]
    return list(PRODUCTS.values())


CATEGORIES = sorted({p["category"] for p in PRODUCTS.values()})
