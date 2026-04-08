"""
Morrisons Salesforce CRM Agent
════════════════════════════════
Registered in WSO2 Agent Manager as: morrisons-salesforce-agent

Capabilities:
  • get_customer_profile        – Look up loyalty customer profile + tier
  • generate_personalised_offer – Create a targeted promotional offer
  • update_customer_segment     – Assign customer to a marketing segment
  • get_supplier_account        – Retrieve supplier account from Salesforce CRM
  • log_service_case            – Create a service case (customer complaint / query)

Integration note for Morrisons:
  Salesforce is hosted on Salesforce.com (SaaS, multi-tenant).
  WSO2 API Manager handles OAuth2 + JWT token exchange with Salesforce Connected App.
  Real-time events use Salesforce Platform Events → WSO2 Event Broker.
"""
from __future__ import annotations

import asyncio
import random
import uuid
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from shared.models import AgentID, AgentMessage, AgentResponse, AgentStatus, CustomerProfile, Offer
from shared.observability import log_event, trace_span, increment

# ── Demo data ────────────────────────────────────────────────────────────────
MOCK_CUSTOMERS: Dict[str, Dict[str, Any]] = {
    "CUST-000101": {
        "name": "Sarah Thompson", "loyalty_tier": "Gold",
        "lifetime_value": 8_450.20, "preferred_store": "STORE-LDS-001",
        "top_categories": ["Fresh Meat", "Dairy", "Organic"],
        "email": "s.thompson@example.com", "app_installed": True,
    },
    "CUST-000202": {
        "name": "James Patel", "loyalty_tier": "Silver",
        "lifetime_value": 3_120.00, "preferred_store": "STORE-BDF-003",
        "top_categories": ["Bakery", "Ready Meals", "Beer & Wine"],
        "email": "j.patel@example.com", "app_installed": True,
    },
    "CUST-000303": {
        "name": "Emma Clarke", "loyalty_tier": "Platinum",
        "lifetime_value": 22_800.50, "preferred_store": "STORE-MAN-002",
        "top_categories": ["Premium Range", "Fish", "Floral"],
        "email": "e.clarke@example.com", "app_installed": True,
    },
    "CUST-000404": {
        "name": "David Osei", "loyalty_tier": "Bronze",
        "lifetime_value":   890.00, "preferred_store": "STORE-LDN-010",
        "top_categories": ["Snacks", "Soft Drinks", "Frozen"],
        "email": "d.osei@example.com", "app_installed": False,
    },
}

TIER_DISCOUNT = {"Bronze": 5, "Silver": 10, "Gold": 15, "Platinum": 20}

MOCK_SUPPLIERS_SF: Dict[str, Dict[str, Any]] = {
    "SUP-001": {"sf_account_id": "001XX000003GYn2",
                "account_name": "British Meat Supplies Ltd",
                "account_manager": "Helen Bryson",
                "health_score": 87, "last_review": "2025-11-15"},
    "SUP-002": {"sf_account_id": "001XX000003GYn3",
                "account_name": "Northern Dairy Co-op",
                "account_manager": "Mike Hartley",
                "health_score": 92, "last_review": "2025-10-20"},
}


class SalesforceAgent:
    """
    WSO2 Agent Manager – Salesforce CRM Agent
    Wraps Salesforce REST API + Platform Events as MCP tools.
    """

    agent_id = AgentID.SALESFORCE

    # ── Tool: get_customer_profile ───────────────────────────────────────────
    async def get_customer_profile(
        self,
        customer_id: str,
        include_purchase_history: bool = False,
        trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        [MCP Tool] Look up Morrisons loyalty customer profile.

        Salesforce REST endpoint (via WSO2 ESB):
          GET /services/data/v59.0/sobjects/Contact/{sf_contact_id}
          + /services/data/v59.0/query?q=SELECT...FROM Loyalty_Member__c
        """
        with trace_span(self.agent_id, "get_customer_profile", trace_id=trace_id,
                        attributes={"customer_id": customer_id}):
            log_event(self.agent_id, "Fetching Salesforce customer profile", {"id": customer_id})
            await asyncio.sleep(0.25)

            customer = MOCK_CUSTOMERS.get(customer_id)
            if not customer:
                return {"error": f"Customer {customer_id} not found in Salesforce"}

            profile = CustomerProfile(
                customer_id=customer_id,
                name=customer["name"],
                loyalty_tier=customer["loyalty_tier"],
                lifetime_value=customer["lifetime_value"],
                preferred_store=customer["preferred_store"],
                top_categories=customer["top_categories"],
            )
            result = {
                **profile.model_dump(),
                "salesforce_contact_id": f"003{uuid.uuid4().hex[:12].upper()}",
                "email": customer["email"],
                "app_installed": customer["app_installed"],
                "morrisons_more_points": random.randint(200, 5000),
            }
            if include_purchase_history:
                result["recent_purchases"] = [
                    {"date": (date.today() - timedelta(days=i * 7)).isoformat(),
                     "store": customer["preferred_store"],
                     "basket_value": round(random.uniform(25, 120), 2)}
                    for i in range(4)
                ]
            increment("salesforce.customer_lookups")
            return result

    # ── Tool: generate_personalised_offer ────────────────────────────────────
    async def generate_personalised_offer(
        self,
        customer_id: str,
        category: Optional[str] = None,
        channel: str = "app",
        trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        [MCP Tool] Generate a targeted promotional offer via Salesforce Marketing Cloud.

        POST /services/data/v59.0/sobjects/Promotion__c
        """
        with trace_span(self.agent_id, "generate_personalised_offer", trace_id=trace_id,
                        attributes={"customer_id": customer_id, "channel": channel}):
            log_event(self.agent_id, "Generating personalised offer",
                      {"customer": customer_id, "channel": channel})
            await asyncio.sleep(0.3)

            customer = MOCK_CUSTOMERS.get(customer_id)
            if not customer:
                return {"error": f"Customer {customer_id} not found"}

            tier      = customer["loyalty_tier"]
            disc      = TIER_DISCOUNT.get(tier, 5)
            offer_cat = category or random.choice(customer["top_categories"])

            offer = Offer(
                offer_id=f"OFF-{uuid.uuid4().hex[:8].upper()}",
                customer_id=customer_id,
                description=f"{disc}% off {offer_cat} for {customer['name']} – Morrisons More",
                discount_pct=disc,
                valid_until=(date.today() + timedelta(days=14)).isoformat(),
                channel=channel,
            )
            increment("salesforce.offers_generated")
            log_event(self.agent_id, "Offer generated", offer.model_dump())
            return {
                **offer.model_dump(),
                "customer_name": customer["name"],
                "loyalty_tier": tier,
                "salesforce_campaign_id": f"701{uuid.uuid4().hex[:12].upper()}",
                "delivery_status": "QUEUED" if channel == "email" else "DELIVERED",
            }

    # ── Tool: update_customer_segment ────────────────────────────────────────
    async def update_customer_segment(
        self,
        customer_id: str,
        segment: str,
        reason: str = "",
        trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """[MCP Tool] Assign a customer to a Salesforce marketing segment."""
        with trace_span(self.agent_id, "update_customer_segment", trace_id=trace_id,
                        attributes={"customer_id": customer_id, "segment": segment}):
            await asyncio.sleep(0.2)
            increment("salesforce.segment_updates")
            return {
                "customer_id": customer_id,
                "segment": segment,
                "reason": reason,
                "updated_at": date.today().isoformat(),
                "salesforce_record_id": f"a0C{uuid.uuid4().hex[:12].upper()}",
                "status": "SUCCESS",
            }

    # ── Tool: get_supplier_account ────────────────────────────────────────────
    async def get_supplier_account(
        self,
        supplier_id: str,
        trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """[MCP Tool] Retrieve supplier account details from Salesforce CRM."""
        with trace_span(self.agent_id, "get_supplier_account", trace_id=trace_id,
                        attributes={"supplier_id": supplier_id}):
            await asyncio.sleep(0.2)
            supplier = MOCK_SUPPLIERS_SF.get(supplier_id)
            if not supplier:
                return {"error": f"Supplier {supplier_id} not found in Salesforce"}
            return {**supplier, "supplier_id": supplier_id}

    # ── Tool: log_service_case ────────────────────────────────────────────────
    async def log_service_case(
        self,
        customer_id: str,
        subject: str,
        description: str,
        priority: str = "Medium",
        trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """[MCP Tool] Create a Salesforce Service Cloud case."""
        with trace_span(self.agent_id, "log_service_case", trace_id=trace_id,
                        attributes={"customer_id": customer_id, "priority": priority}):
            await asyncio.sleep(0.25)
            case_number = f"CSE-{random.randint(100000, 999999)}"
            increment("salesforce.cases_created")
            return {
                "case_number": case_number,
                "customer_id": customer_id,
                "subject": subject,
                "priority": priority,
                "status": "New",
                "created_at": date.today().isoformat(),
                "salesforce_case_id": f"500{uuid.uuid4().hex[:12].upper()}",
                "sla_breach_date": (date.today() + timedelta(days=2 if priority == "High" else 5)).isoformat(),
            }

    # ── MCP dispatch ─────────────────────────────────────────────────────────
    async def handle_mcp_call(
        self, tool_name: str, arguments: Dict[str, Any], trace_id: Optional[str] = None
    ) -> Dict[str, Any]:
        tools = {
            "get_customer_profile":        self.get_customer_profile,
            "generate_personalised_offer": self.generate_personalised_offer,
            "update_customer_segment":     self.update_customer_segment,
            "get_supplier_account":        self.get_supplier_account,
            "log_service_case":            self.log_service_case,
        }
        if tool_name not in tools:
            return {"error": f"Unknown tool: {tool_name}"}
        return await tools[tool_name](**arguments, trace_id=trace_id)

    async def process_message(self, msg: AgentMessage) -> AgentResponse:
        tid = msg.trace_context.get("trace_id", str(uuid.uuid4()).replace("-", ""))
        log_event(self.agent_id, f"Received task from {msg.from_agent.value}", msg.payload)
        try:
            result = await self.handle_mcp_call(
                msg.payload.get("tool"), msg.payload.get("args", {}), trace_id=tid
            )
            return AgentResponse(
                message_id=str(uuid.uuid4()), correlation_id=msg.correlation_id,
                from_agent=self.agent_id, status=AgentStatus.COMPLETED, data=result,
            )
        except Exception as exc:
            return AgentResponse(
                message_id=str(uuid.uuid4()), correlation_id=msg.correlation_id,
                from_agent=self.agent_id, status=AgentStatus.FAILED, data={}, error=str(exc),
            )


salesforce_agent = SalesforceAgent()
