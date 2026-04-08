"""
Morrisons SAP ERP Agent – LangChain Tools
==========================================
Wraps SAP S/4HANA operations (MM, IBP, Vendor Master) as @tool functions.
In production these call SAP OData v4 APIs via the WSO2 API Gateway.
For the demo, realistic mock data is returned.
"""
import random
from datetime import date, timedelta

from langchain_core.tools import tool

# ── Mock SAP data ─────────────────────────────────────────────────────────────
STOCK = {
    "SKU-BEEF-001": {"name": "Morrisons Best Beef Mince 500g",  "stock": 48,  "reorder": 120, "supplier": "SUP-001", "cat": "Fresh Meat"},
    "SKU-MILK-003": {"name": "Morrisons Whole Milk 4 Pints",    "stock": 210, "reorder": 300, "supplier": "SUP-002", "cat": "Dairy"},
    "SKU-BREA-007": {"name": "Morrisons White Thick Bread",      "stock": 35,  "reorder": 150, "supplier": "SUP-003", "cat": "Bakery"},
    "SKU-CHIC-002": {"name": "Morrisons Chicken Breast 500g",    "stock": 12,  "reorder": 80,  "supplier": "SUP-001", "cat": "Fresh Meat"},
    "SKU-SALM-004": {"name": "Morrisons Scottish Salmon 240g",   "stock": 5,   "reorder": 60,  "supplier": "SUP-004", "cat": "Fish"},
}

SUPPLIERS = {
    "SUP-001": {"name": "British Meat Supplies Ltd",  "lead_days": 2, "payment_terms": "NET30"},
    "SUP-002": {"name": "Northern Dairy Co-op",       "lead_days": 1, "payment_terms": "NET14"},
    "SUP-003": {"name": "Allied Bakery UK",            "lead_days": 1, "payment_terms": "NET7"},
    "SUP-004": {"name": "Scottish Seafood Partners",  "lead_days": 3, "payment_terms": "NET21"},
}

_po_counter = [4500]


@tool
def check_stock_level(sku: str, store_id: str = "STORE-001") -> str:
    """
    Check current stock level for a product SKU at a Morrisons store using SAP MM.
    Returns stock quantity, reorder level, and whether a reorder is needed.

    Args:
        sku: SAP material number, e.g. SKU-BEEF-001, SKU-MILK-003, SKU-CHIC-002, SKU-SALM-004, SKU-BREA-007
        store_id: Morrisons store ID, e.g. STORE-001, STORE-002
    """
    if sku not in STOCK:
        return f"SKU '{sku}' not found in SAP material master. Valid SKUs: {', '.join(STOCK)}"
    item = STOCK[sku]
    # Simulate small drift each call
    item["stock"] = max(0, item["stock"] + random.randint(-3, 5))
    below = item["stock"] < item["reorder"]
    status = "⚠ BELOW REORDER LEVEL – replenishment required" if below else "✓ OK"
    suggested = (item["reorder"] * 2 - item["stock"]) if below else 0
    return (
        f"SAP MM Stock Check\n"
        f"SKU: {sku} | Store: {store_id} | Plant: GBR1\n"
        f"Product: {item['name']}\n"
        f"Current Stock: {item['stock']} units\n"
        f"Reorder Level: {item['reorder']} units\n"
        f"Status: {status}\n"
        f"Category: {item['cat']} | Supplier: {item['supplier']}"
        + (f"\nSuggested Order Qty: {suggested} units" if below else "")
    )


@tool
def raise_purchase_order(sku: str, quantity: int, supplier_id: str,
                          delivery_date: str = "") -> str:
    """
    Raise a Purchase Order in SAP MM against an approved Morrisons supplier.
    Creates a PO document in SAP S/4HANA for the given SKU and quantity.

    Args:
        sku: SAP material number, e.g. SKU-BEEF-001
        quantity: Number of units to order (must be positive)
        supplier_id: SAP vendor ID, e.g. SUP-001, SUP-002, SUP-003, SUP-004
        delivery_date: Requested delivery date in YYYY-MM-DD format (optional)
    """
    if sku not in STOCK:
        return f"Cannot raise PO: SKU '{sku}' not found in SAP material master."
    if supplier_id not in SUPPLIERS:
        return f"Cannot raise PO: Supplier '{supplier_id}' not found in SAP vendor master."
    if quantity <= 0:
        return "Cannot raise PO: quantity must be greater than zero."

    supplier = SUPPLIERS[supplier_id]
    _po_counter[0] += 1
    po_number = f"PO-{_po_counter[0]:06d}"
    unit_price = round(random.uniform(0.80, 12.50), 2)
    total = round(unit_price * quantity, 2)
    if not delivery_date:
        delivery_date = (date.today() + timedelta(days=supplier["lead_days"])).isoformat()

    return (
        f"SAP Purchase Order Created ✓\n"
        f"PO Number: {po_number} | SAP Doc: 4500{_po_counter[0]}\n"
        f"SKU: {sku} | Qty: {quantity} units\n"
        f"Supplier: {supplier['name']} ({supplier_id})\n"
        f"Unit Price: £{unit_price} | Total: £{total}\n"
        f"Delivery Date: {delivery_date}\n"
        f"Payment Terms: {supplier['payment_terms']} | Status: CREATED"
    )


@tool
def get_supplier_info(supplier_id: str) -> str:
    """
    Retrieve vendor master data for a Morrisons supplier from SAP Business Partner.
    Returns lead times, payment terms, and contract details.

    Args:
        supplier_id: SAP vendor ID, e.g. SUP-001, SUP-002, SUP-003, SUP-004
    """
    if supplier_id not in SUPPLIERS:
        return f"Supplier '{supplier_id}' not found in SAP vendor master. Valid IDs: {', '.join(SUPPLIERS)}"
    s = SUPPLIERS[supplier_id]
    contracts = {"SUP-001": "C-2024-001", "SUP-002": "C-2024-002",
                 "SUP-003": "C-2024-003", "SUP-004": "C-2024-004"}
    return (
        f"SAP Vendor Master: {supplier_id}\n"
        f"Name: {s['name']}\n"
        f"Lead Time: {s['lead_days']} day(s)\n"
        f"Payment Terms: {s['payment_terms']}\n"
        f"Contract: {contracts.get(supplier_id, 'N/A')}\n"
        f"Currency: GBP | Country: GB | Status: ACTIVE"
    )


@tool
def get_goods_movement(sku: str, days: int = 7) -> str:
    """
    Retrieve recent goods receipts and issues (GR/GI) from SAP MIGO for a SKU.
    Shows stock movements over the specified number of days.

    Args:
        sku: SAP material number, e.g. SKU-BEEF-001
        days: Number of days to look back (default 7, max 90)
    """
    if sku not in STOCK:
        return f"SKU '{sku}' not found in SAP material master."
    days = min(days, 90)
    movements = []
    for i in range(days):
        if random.random() > 0.35:
            movements.append(
                f"  {(date.today() - timedelta(days=i)).isoformat()}  "
                f"{random.choice(['101-GR', '261-GI', '551-Scrap'])}  "
                f"Qty: {random.randint(20, 200)}  "
                f"Doc: 490{random.randint(1000, 9999)}"
            )
    if not movements:
        return f"No goods movements found for {sku} in the last {days} days."
    return (
        f"SAP MIGO – Goods Movements for {sku} (last {days} days)\n"
        + "\n".join(movements[:10])
        + (f"\n... and {len(movements)-10} more" if len(movements) > 10 else "")
    )


@tool
def run_demand_forecast(sku: str, horizon_days: int = 90) -> str:
    """
    Pull a rolling demand forecast from SAP IBP (Integrated Business Planning).
    Returns weekly forecast quantities and confidence levels.

    Args:
        sku: SAP material number, e.g. SKU-BEEF-001
        horizon_days: Forecast horizon in days (default 90)
    """
    if sku not in STOCK:
        return f"SKU '{sku}' not found in SAP IBP. Valid SKUs: {', '.join(STOCK)}"
    horizon_days = min(horizon_days, 365)
    base = random.randint(80, 160)
    weeks = horizon_days // 7
    total = 0
    lines = []
    for i in range(min(weeks, 6)):  # show first 6 weeks
        qty = base + random.randint(-20, 30)
        conf = round(random.uniform(0.72, 0.95), 2)
        total += qty
        lines.append(f"  W{i+1}: {qty} units  (confidence: {conf:.0%})")
    total_all = base * weeks + random.randint(-100, 100)
    return (
        f"SAP IBP Demand Forecast | SKU: {sku} | Horizon: {horizon_days} days\n"
        f"Model: SAP_IBP_ARIMA\n"
        + "\n".join(lines)
        + f"\n  ... ({weeks - 6} more weeks)" if weeks > 6 else "\n".join(lines)
        + f"\nTotal Forecast ({horizon_days}d): {total_all} units"
    )


TOOLS = [
    check_stock_level,
    raise_purchase_order,
    get_supplier_info,
    get_goods_movement,
    run_demand_forecast,
]
