"""Morrisons Salesforce CRM Agent – LangChain Tools"""
import random
from datetime import date, timedelta
from langchain_core.tools import tool

CUSTOMERS = {
    "CUST-100142": {"name": "Sarah Thompson",  "tier": "Gold",     "points": 4820, "spend_ytd": 3180.50},
    "CUST-100256": {"name": "James Patel",     "tier": "Silver",   "points": 1205, "spend_ytd":  980.00},
    "CUST-100389": {"name": "Emma Clarke",     "tier": "Platinum", "points": 9830, "spend_ytd": 7120.75},
    "CUST-100471": {"name": "David O'Brien",   "tier": "Bronze",   "points":  320, "spend_ytd":  210.25},
}

SUPPLIER_ACCOUNTS = {
    "SUP-001": {"name": "British Meat Supplies Ltd",  "health": 92, "relationship": "Strategic"},
    "SUP-002": {"name": "Northern Dairy Co-op",       "health": 88, "relationship": "Preferred"},
    "SUP-003": {"name": "Allied Bakery UK",            "health": 76, "relationship": "Standard"},
    "SUP-004": {"name": "Scottish Seafood Partners",  "health": 95, "relationship": "Strategic"},
}

_case_counter = [5000]


@tool
def get_customer_profile(customer_id: str, include_purchase_history: bool = False) -> str:
    """
    Look up a Morrisons More loyalty customer profile from Salesforce CRM.
    Returns loyalty tier, points balance, and YTD spend.

    Args:
        customer_id: Morrisons customer ID, e.g. CUST-100142, CUST-100256, CUST-100389, CUST-100471
        include_purchase_history: Whether to include recent purchase summary (default False)
    """
    if customer_id not in CUSTOMERS:
        return (
            f"Customer '{customer_id}' not found in Salesforce. "
            f"Valid IDs: {', '.join(CUSTOMERS)}"
        )
    c = CUSTOMERS[customer_id]
    churn_risk = random.choice(["Low", "Low", "Medium", "High"])
    history = ""
    if include_purchase_history:
        cats = ["Fresh Meat", "Dairy", "Bakery", "Fish", "Frozen"]
        history = "\nRecent Purchases: " + ", ".join(random.sample(cats, 3))
    return (
        f"Salesforce CRM – Customer Profile\n"
        f"ID: {customer_id} | Name: {c['name']}\n"
        f"Loyalty Tier: {c['tier']} | Points: {c['points']:,}\n"
        f"YTD Spend: £{c['spend_ytd']:,.2f} | Churn Risk: {churn_risk}"
        + history
    )


@tool
def generate_personalised_offer(customer_id: str, channel: str = "app",
                                  category: str = "") -> str:
    """
    Generate a tier-appropriate personalised offer via Salesforce Marketing Cloud.
    Tailors discount and product recommendation to the customer's loyalty tier.

    Args:
        customer_id: Morrisons customer ID, e.g. CUST-100142
        channel: Delivery channel – app, email, or in-store (default: app)
        category: Optional product category to target, e.g. Fresh Meat, Dairy
    """
    if customer_id not in CUSTOMERS:
        return f"Customer '{customer_id}' not found in Salesforce."
    c = CUSTOMERS[customer_id]
    discounts = {"Platinum": "20%", "Gold": "15%", "Silver": "10%", "Bronze": "5%"}
    discount = discounts.get(c["tier"], "5%")
    offer_id = f"OFFER-{random.randint(10000, 99999)}"
    cat = category or random.choice(["Fresh Meat", "Dairy", "Fish", "Bakery"])
    expiry = (date.today() + timedelta(days=7)).isoformat()
    return (
        f"Salesforce Marketing Cloud – Personalised Offer Generated ✓\n"
        f"Customer: {c['name']} ({c['tier']} tier)\n"
        f"Offer ID: {offer_id}\n"
        f"Discount: {discount} off {cat}\n"
        f"Channel: {channel} | Expires: {expiry}\n"
        f"Points Bonus: {100 if c['tier'] == 'Platinum' else 50} extra points on redemption"
    )


@tool
def update_customer_segment(customer_id: str, segment: str, reason: str = "") -> str:
    """
    Assign a Morrisons customer to a Salesforce marketing segment.

    Args:
        customer_id: Morrisons customer ID, e.g. CUST-100142
        segment: Segment name – HIGH_VALUE, AT_RISK_CHURN, FREQUENT_BUYER, LAPSED, NEW_CUSTOMER
        reason: Optional reason for segment change
    """
    valid_segments = ["HIGH_VALUE", "AT_RISK_CHURN", "FREQUENT_BUYER", "LAPSED", "NEW_CUSTOMER"]
    if segment not in valid_segments:
        return f"Invalid segment '{segment}'. Valid segments: {', '.join(valid_segments)}"
    if customer_id not in CUSTOMERS:
        return f"Customer '{customer_id}' not found."
    return (
        f"Salesforce – Customer Segment Updated ✓\n"
        f"Customer: {customer_id}\n"
        f"New Segment: {segment}\n"
        f"Reason: {reason or 'Not specified'}\n"
        f"Next Campaign Inclusion: Next scheduled Marketing Cloud run"
    )


@tool
def get_supplier_account(supplier_id: str) -> str:
    """
    Retrieve supplier account details and health score from Salesforce CRM.

    Args:
        supplier_id: Supplier ID, e.g. SUP-001, SUP-002, SUP-003, SUP-004
    """
    if supplier_id not in SUPPLIER_ACCOUNTS:
        return f"Supplier '{supplier_id}' not found. Valid: {', '.join(SUPPLIER_ACCOUNTS)}"
    s = SUPPLIER_ACCOUNTS[supplier_id]
    status = "✓ Healthy" if s["health"] >= 85 else "⚠ At Risk"
    return (
        f"Salesforce CRM – Supplier Account\n"
        f"ID: {supplier_id} | Name: {s['name']}\n"
        f"Relationship: {s['relationship']} | Health Score: {s['health']}/100 {status}\n"
        f"Last Review: {(date.today() - timedelta(days=random.randint(10, 60))).isoformat()}"
    )


@tool
def log_service_case(customer_id: str, subject: str, description: str,
                      priority: str = "Medium") -> str:
    """
    Create a customer service case in Salesforce Service Cloud.

    Args:
        customer_id: Morrisons customer ID
        subject: Brief case subject line
        description: Detailed description of the customer issue
        priority: Case priority – Low, Medium, or High (default: Medium)
    """
    if priority not in ("Low", "Medium", "High"):
        priority = "Medium"
    _case_counter[0] += 1
    case_num = f"CS-{_case_counter[0]:06d}"
    sla = {"High": "4 hours", "Medium": "24 hours", "Low": "72 hours"}
    return (
        f"Salesforce Service Cloud – Case Created ✓\n"
        f"Case: {case_num} | Priority: {priority}\n"
        f"Customer: {customer_id}\n"
        f"Subject: {subject}\n"
        f"SLA: Response within {sla[priority]}\n"
        f"Assigned Queue: Morrisons Customer Service"
    )


TOOLS = [
    get_customer_profile,
    generate_personalised_offer,
    update_customer_segment,
    get_supplier_account,
    log_service_case,
]
