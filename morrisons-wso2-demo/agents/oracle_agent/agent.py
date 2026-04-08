"""
Morrisons Oracle ERP Agent
══════════════════════════
Registered in WSO2 Agent Manager as: morrisons-oracle-erp-agent

Capabilities:
  • get_budget_availability   – Query Oracle Fusion Financials for available budget
  • approve_purchase_order    – Submit PO for approval in Oracle Approval Management
  • get_cost_centre_report    – Pull cost-centre spend report from Oracle ERP Cloud
  • get_invoice_status        – Check invoice payment status (Oracle AP)
  • create_journal_entry      – Post a journal entry to Oracle General Ledger

Transport:
  • MCP over SSE, proxied through WSO2 API Manager
  • OAuth 2.0 with Oracle IDCS (Identity Cloud Service)

Integration note for Morrisons:
  Oracle ERP Cloud (Fusion Financials) is Morrisons' finance backbone.
  It runs on Oracle Cloud Infrastructure (OCI). The WSO2 ESB acts as the
  canonical integration hub between SAP (GCP), Oracle (OCI), and Salesforce.
"""
from __future__ import annotations

import asyncio
import random
import uuid
from datetime import date, timedelta
from typing import Any, Dict, Optional

from shared.models import AgentID, AgentMessage, AgentResponse, AgentStatus, FinanceApproval
from shared.observability import log_event, trace_span, increment

# ── Demo data ────────────────────────────────────────────────────────────────
MOCK_BUDGETS: Dict[str, Dict[str, Any]] = {
    "CC-FRESH-001":  {"name": "Fresh Foods Buying",    "annual": 2_400_000, "spent": 1_180_000, "currency": "GBP"},
    "CC-BAKERY-002": {"name": "Bakery & Deli Buying",  "annual":   800_000, "spent":   420_000, "currency": "GBP"},
    "CC-FISH-003":   {"name": "Fish & Seafood Buying", "annual":   600_000, "spent":   390_000, "currency": "GBP"},
    "CC-DAIRY-004":  {"name": "Dairy & Eggs Buying",   "annual": 1_200_000, "spent":   710_000, "currency": "GBP"},
    "CC-OPEX-010":   {"name": "Store Operations",      "annual": 5_000_000, "spent": 2_950_000, "currency": "GBP"},
}

MOCK_PO_APPROVALS: Dict[str, Dict[str, Any]] = {}

CATEGORY_TO_COSTCENTRE = {
    "Fresh Meat": "CC-FRESH-001",
    "Dairy":      "CC-DAIRY-004",
    "Bakery":     "CC-BAKERY-002",
    "Fish":       "CC-FISH-003",
}


class OracleERPAgent:
    """
    WSO2 Agent Manager – Oracle ERP (Fusion Financials) Agent
    Exposes Oracle ERP Cloud REST/SOAP APIs as MCP tools.
    """

    agent_id = AgentID.ORACLE_ERP

    # ── Tool: get_budget_availability ────────────────────────────────────────
    async def get_budget_availability(
        self,
        cost_centre: str,
        fiscal_year: Optional[int] = None,
        trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        [MCP Tool] Query Oracle Fusion Financials for available budget.

        Oracle REST endpoint (via WSO2 ESB):
          GET /fscmRestApi/resources/11.13.18.05/ledgerBalances
              ?q=CostCenter={cost_centre};FiscalYear={year}
        """
        with trace_span(self.agent_id, "get_budget_availability", trace_id=trace_id,
                        attributes={"cost_centre": cost_centre}):
            log_event(self.agent_id, "Querying Oracle budget", {"cost_centre": cost_centre})
            await asyncio.sleep(0.35)
            if not fiscal_year:
                fiscal_year = date.today().year

            budget = MOCK_BUDGETS.get(cost_centre)
            if not budget:
                return {"error": f"Cost centre {cost_centre} not found in Oracle GL"}

            remaining = budget["annual"] - budget["spent"]
            utilisation_pct = round((budget["spent"] / budget["annual"]) * 100, 1)
            increment("oracle.budget_queries")
            return {
                "cost_centre":       cost_centre,
                "cost_centre_name":  budget["name"],
                "fiscal_year":       fiscal_year,
                "annual_budget":     budget["annual"],
                "spent_to_date":     budget["spent"],
                "remaining_budget":  remaining,
                "utilisation_pct":   utilisation_pct,
                "currency":          budget["currency"],
                "status":            "GREEN" if utilisation_pct < 80 else ("AMBER" if utilisation_pct < 95 else "RED"),
                "oracle_ledger_id":  "LED-UK-001",
            }

    # ── Tool: approve_purchase_order ─────────────────────────────────────────
    async def approve_purchase_order(
        self,
        po_number: str,
        total_value: float,
        cost_centre: str,
        category: str,
        requester: str = "SYSTEM",
        trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        [MCP Tool] Submit PO for approval via Oracle Approval Management Engine (AME).

        Approval matrix (Morrisons policy):
          < £5,000   → Auto-approved
          £5k–£50k   → Category manager approval
          > £50,000  → Finance director + CFO approval
        """
        with trace_span(self.agent_id, "approve_purchase_order", trace_id=trace_id,
                        attributes={"po_number": po_number, "value": total_value}):
            log_event(self.agent_id, "Oracle PO Approval requested",
                      {"po": po_number, "value": total_value, "cc": cost_centre})
            await asyncio.sleep(0.4)

            # Determine approval tier
            if total_value < 5_000:
                approver = "AUTO_APPROVAL"
                approved = True
                tier = "Tier 1 – Auto"
            elif total_value < 50_000:
                approver = "CAT-MGR-" + cost_centre[-3:]
                approved = True   # In demo, auto-approve for flow
                tier = "Tier 2 – Category Manager"
            else:
                approver = "FINANCE-DIRECTOR"
                approved = False  # High-value needs human
                tier = "Tier 3 – Finance Director (human required)"

            # Check budget availability
            budget = MOCK_BUDGETS.get(cost_centre, {})
            remaining = budget.get("annual", 999999) - budget.get("spent", 0)
            budget_ok = remaining >= total_value

            result = FinanceApproval(
                po_number=po_number,
                approver=approver,
                approved=approved and budget_ok,
                budget_code=f"BUD-{fiscal_year_code()}-{cost_centre}",
                cost_centre=cost_centre,
                notes=(
                    f"Auto-approved by Oracle AME ({tier})."
                    if approved and budget_ok
                    else f"Rejected – {'insufficient budget' if not budget_ok else 'requires human approval (' + tier + ')'}"
                ),
            )

            if result.approved and cost_centre in MOCK_BUDGETS:
                MOCK_BUDGETS[cost_centre]["spent"] += total_value

            MOCK_PO_APPROVALS[po_number] = result.model_dump()
            increment("oracle.po_approvals")
            log_event(self.agent_id, f"PO approval result: {result.approved}", result.model_dump())
            return {
                **result.model_dump(),
                "approval_tier": tier,
                "oracle_approval_id": f"AME-{uuid.uuid4().hex[:8].upper()}",
                "budget_remaining_after": remaining - (total_value if result.approved else 0),
            }

    # ── Tool: get_cost_centre_report ─────────────────────────────────────────
    async def get_cost_centre_report(
        self,
        cost_centre: str,
        period: str = "MTD",
        trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """[MCP Tool] Pull spend report for a cost centre from Oracle Financials Cloud."""
        with trace_span(self.agent_id, "get_cost_centre_report", trace_id=trace_id,
                        attributes={"cost_centre": cost_centre, "period": period}):
            await asyncio.sleep(0.3)
            budget = MOCK_BUDGETS.get(cost_centre)
            if not budget:
                return {"error": f"Cost centre {cost_centre} not found"}
            lines = [
                {"account": f"5{i:03d}00", "description": f"Supplier Payment #{i}",
                 "amount": round(random.uniform(1000, 50000), 2), "date": (date.today() - timedelta(days=i * 3)).isoformat()}
                for i in range(1, 8)
            ]
            return {"cost_centre": cost_centre, "period": period,
                    "total_spend": sum(l["amount"] for l in lines),
                    "transactions": lines, "currency": "GBP"}

    # ── Tool: get_invoice_status ─────────────────────────────────────────────
    async def get_invoice_status(
        self,
        po_number: str,
        trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """[MCP Tool] Check invoice payment status in Oracle Accounts Payable."""
        with trace_span(self.agent_id, "get_invoice_status", trace_id=trace_id,
                        attributes={"po_number": po_number}):
            await asyncio.sleep(0.2)
            status = random.choice(["PAID", "UNPAID", "PARTIALLY_PAID", "OVERDUE"])
            return {
                "po_number": po_number,
                "invoice_number": f"INV-{uuid.uuid4().hex[:8].upper()}",
                "status": status,
                "due_date": (date.today() + timedelta(days=random.randint(-5, 30))).isoformat(),
                "amount_due": round(random.uniform(500, 25000), 2),
                "currency": "GBP",
            }

    # ── Tool: create_journal_entry ───────────────────────────────────────────
    async def create_journal_entry(
        self,
        description: str,
        debit_account: str,
        credit_account: str,
        amount: float,
        cost_centre: str,
        trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """[MCP Tool] Post a journal entry to Oracle General Ledger."""
        with trace_span(self.agent_id, "create_journal_entry", trace_id=trace_id,
                        attributes={"amount": amount, "cc": cost_centre}):
            await asyncio.sleep(0.3)
            je_id = f"JE-{uuid.uuid4().hex[:8].upper()}"
            increment("oracle.journal_entries")
            return {
                "journal_id": je_id,
                "description": description,
                "debit_account": debit_account,
                "credit_account": credit_account,
                "amount": amount,
                "currency": "GBP",
                "cost_centre": cost_centre,
                "status": "POSTED",
                "ledger": "UK Corporate Ledger",
                "period": date.today().strftime("%b-%Y"),
            }

    # ── MCP dispatch ─────────────────────────────────────────────────────────
    async def handle_mcp_call(
        self, tool_name: str, arguments: Dict[str, Any], trace_id: Optional[str] = None
    ) -> Dict[str, Any]:
        tools = {
            "get_budget_availability":  self.get_budget_availability,
            "approve_purchase_order":   self.approve_purchase_order,
            "get_cost_centre_report":   self.get_cost_centre_report,
            "get_invoice_status":       self.get_invoice_status,
            "create_journal_entry":     self.create_journal_entry,
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


def fiscal_year_code() -> str:
    return str(date.today().year)[-2:]


oracle_agent = OracleERPAgent()
