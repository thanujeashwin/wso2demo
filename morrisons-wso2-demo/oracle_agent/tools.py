"""
Morrisons Oracle ERP Agent – LangChain Tools
=============================================
Wraps Oracle Fusion Cloud (GL, AME, AP) operations as @tool functions.
"""
import random
from datetime import date

from langchain_core.tools import tool

# ── Mock Oracle Fusion data ────────────────────────────────────────────────────
BUDGETS = {
    "CC-FRESH-001": {"name": "Fresh Foods Buying",   "allocated": 500_000, "spent": 412_000},
    "CC-FISH-003":  {"name": "Fish & Seafood Buying", "allocated": 120_000, "spent":  98_500},
    "CC-BAKERY-02": {"name": "Bakery Procurement",    "allocated": 250_000, "spent": 231_000},
    "CC-DAIRY-001": {"name": "Dairy Procurement",     "allocated": 180_000, "spent": 142_000},
    "CC-FROZEN-05": {"name": "Frozen Foods",          "allocated":  90_000, "spent":  61_000},
}

_po_approvals: dict[str, str] = {}
_journal_counter = [8800]


@tool
def get_budget_availability(cost_centre: str, fiscal_year: int = 0) -> str:
    """
    Query Oracle Fusion GL for remaining budget on a Morrisons cost centre.
    Returns allocated budget, amount spent, and available balance.

    Args:
        cost_centre: Cost centre code, e.g. CC-FRESH-001, CC-FISH-003, CC-BAKERY-02, CC-DAIRY-001, CC-FROZEN-05
        fiscal_year: Fiscal year (0 = current year)
    """
    if cost_centre not in BUDGETS:
        return (
            f"Cost centre '{cost_centre}' not found in Oracle Fusion GL. "
            f"Valid codes: {', '.join(BUDGETS)}"
        )
    fy = fiscal_year if fiscal_year else date.today().year
    b = BUDGETS[cost_centre]
    available = b["allocated"] - b["spent"]
    utilisation = b["spent"] / b["allocated"] * 100
    status = "⚠ NEAR LIMIT" if utilisation >= 90 else ("⚠ WARNING" if utilisation >= 80 else "✓ OK")
    return (
        f"Oracle Fusion GL – Budget Availability\n"
        f"Cost Centre: {cost_centre} | {b['name']} | FY{fy}\n"
        f"Allocated:   £{b['allocated']:,.0f}\n"
        f"Spent:       £{b['spent']:,.0f} ({utilisation:.1f}%)\n"
        f"Available:   £{available:,.0f}\n"
        f"Status: {status}"
    )


@tool
def approve_purchase_order(po_number: str, total_value: float,
                            cost_centre: str, category: str,
                            requester: str = "SYSTEM") -> str:
    """
    Submit a Purchase Order to Oracle AME (Approval Management Engine).
    Auto-approves orders under £5k. Routes to manager for £5k–£50k.
    Finance Director approval required for orders above £50k.

    Args:
        po_number: SAP PO number, e.g. PO-004501
        total_value: Total order value in GBP
        cost_centre: Oracle cost centre code, e.g. CC-FRESH-001
        category: Product category, e.g. Fresh Meat, Fish, Dairy
        requester: Employee or system requesting approval (default: SYSTEM)
    """
    if total_value <= 0:
        return "Cannot approve PO: total_value must be positive."

    if total_value < 5_000:
        approval_status = "AUTO-APPROVED"
        approver = "System (auto-approval threshold: <£5,000)"
    elif total_value < 50_000:
        approval_status = "APPROVED"
        approver = "Category Buyer Manager"
    else:
        approval_status = "PENDING – Finance Director Review"
        approver = "Finance Director (required for >£50,000)"

    _po_approvals[po_number] = approval_status
    ame_ref = f"AME-{random.randint(10000, 99999)}"

    return (
        f"Oracle AME – Purchase Order Approval\n"
        f"PO Number: {po_number} | AME Ref: {ame_ref}\n"
        f"Value: £{total_value:,.2f} | Category: {category}\n"
        f"Cost Centre: {cost_centre} | Requester: {requester}\n"
        f"Decision: {approval_status}\n"
        f"Approver: {approver}"
    )


@tool
def get_cost_centre_report(cost_centre: str, period: str = "MTD") -> str:
    """
    Retrieve a spend report for a Morrisons cost centre from Oracle Fusion GL.
    Supports Month-to-Date (MTD), Quarter-to-Date (QTD), and Year-to-Date (YTD).

    Args:
        cost_centre: Cost centre code, e.g. CC-FRESH-001
        period: Reporting period – MTD, QTD, or YTD (default: MTD)
    """
    if cost_centre not in BUDGETS:
        return f"Cost centre '{cost_centre}' not found. Valid: {', '.join(BUDGETS)}"
    period = period.upper()
    if period not in ("MTD", "QTD", "YTD"):
        return "Invalid period. Use MTD, QTD, or YTD."

    b = BUDGETS[cost_centre]
    multipliers = {"MTD": 0.08, "QTD": 0.25, "YTD": 1.0}
    mult = multipliers[period]
    spend = round(b["spent"] * mult)
    budget = round(b["allocated"] * mult)
    variance = budget - spend
    top_categories = ["Suppliers", "Logistics", "Wastage", "Promotions"]
    breakdown = "\n".join(
        f"  {cat}: £{round(spend * random.uniform(0.15, 0.35)):,}"
        for cat in top_categories
    )
    return (
        f"Oracle Fusion GL – {period} Spend Report\n"
        f"Cost Centre: {cost_centre} | {b['name']}\n"
        f"Period Budget: £{budget:,} | Spend: £{spend:,} | Variance: £{variance:,}\n"
        f"Top Spend Categories:\n{breakdown}"
    )


@tool
def get_invoice_status(po_number: str) -> str:
    """
    Check Oracle AP invoice payment status for a Purchase Order.
    Returns invoice number, payment date, and current status.

    Args:
        po_number: SAP PO number, e.g. PO-004501
    """
    statuses = ["PAID", "SCHEDULED", "ON_HOLD", "PENDING_APPROVAL"]
    weights = [0.5, 0.25, 0.1, 0.15]
    status = random.choices(statuses, weights=weights)[0]
    inv_num = f"INV-{random.randint(100000, 999999)}"
    pay_date = date.today().replace(day=random.randint(1, 28)).isoformat()
    return (
        f"Oracle AP – Invoice Status\n"
        f"PO: {po_number} | Invoice: {inv_num}\n"
        f"Status: {status}\n"
        f"Payment Date: {pay_date}\n"
        f"Payment Method: BACS | Terms: NET30"
    )


@tool
def create_journal_entry(description: str, debit_account: str,
                          credit_account: str, amount: float,
                          cost_centre: str) -> str:
    """
    Post a journal entry to Oracle Fusion General Ledger.
    Used for accruals, corrections, and inter-company transactions.

    Args:
        description: Journal description, e.g. 'Accrual for Q4 supplier payments'
        debit_account: GL debit account code, e.g. 5001-COGS
        credit_account: GL credit account code, e.g. 2100-AP
        amount: Transaction amount in GBP
        cost_centre: Cost centre code, e.g. CC-FRESH-001
    """
    if amount <= 0:
        return "Cannot post journal: amount must be positive."
    _journal_counter[0] += 1
    je_number = f"JE-{_journal_counter[0]:06d}"
    return (
        f"Oracle GL – Journal Entry Posted ✓\n"
        f"Journal: {je_number} | Ledger: Morrisons_UK_Primary\n"
        f"Description: {description}\n"
        f"Dr: {debit_account}  £{amount:,.2f}\n"
        f"Cr: {credit_account}  £{amount:,.2f}\n"
        f"Cost Centre: {cost_centre} | Status: POSTED | Period: {date.today().strftime('%b-%Y')}"
    )


TOOLS = [
    get_budget_availability,
    approve_purchase_order,
    get_cost_centre_report,
    get_invoice_status,
    create_journal_entry,
]
