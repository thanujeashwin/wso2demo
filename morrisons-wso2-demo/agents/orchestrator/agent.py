"""
Morrisons Master Orchestrator Agent
═════════════════════════════════════
Registered in WSO2 Agent Manager as: morrisons-orchestrator

This is the brain of the multi-agent system. It:

  1. Receives natural-language or structured requests from users / upstream systems
  2. Classifies the request into a domain (supply chain / store ops / CX / finance)
  3. Plans a sequence of sub-agent calls to fulfil the request
  4. Enforces guardrails BEFORE calling any sub-agent
  5. Calls sub-agents in sequence or parallel (using asyncio.gather)
  6. Aggregates results and returns a unified response
  7. Emits a full distributed trace for each request

Architecture in WSO2 Agent Manager:
  ┌─────────────────────────────────────────────────────────────┐
  │                   WSO2 Agent Manager Portal                  │
  │  Single pane of glass – model selection, agent catalogue     │
  └──────────────────────┬──────────────────────────────────────┘
                         │  HTTPS / MCP
  ┌──────────────────────▼──────────────────────────────────────┐
  │              Morrisons Orchestrator Agent                    │
  │   • LLM routing (Claude / Gemini / GPT-4 selectable)        │
  │   • Guardrails engine                                        │
  │   • Parallel sub-agent dispatch                              │
  └──┬────────┬────────┬────────┬────────┬───────────────────────┘
     │        │        │        │        │
    SAP     Oracle  Salesforce  AWS     GCP
  (GCP)    (OCI)    (SaaS)  (eu-west) (EU)
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from shared.models import (
    AgentID, AgentMessage, AgentResponse, AgentStatus,
    Domain, Priority, StockAlert,
)
from shared.observability import log_event, trace_span, render_trace, render_agent_health, increment

from guardrails.guardrails import GuardrailEngine, GuardrailResult
from agents.sap_agent.agent       import sap_agent
from agents.oracle_agent.agent    import oracle_agent
from agents.salesforce_agent.agent import salesforce_agent
from agents.aws_agent.agent       import aws_agent
from agents.gcp_agent.agent       import gcp_agent


# ── Agent registry – shown in WSO2 Agent Manager portal ─────────────────────
AGENT_REGISTRY = {
    AgentID.SAP_ERP:    sap_agent,
    AgentID.ORACLE_ERP: oracle_agent,
    AgentID.SALESFORCE: salesforce_agent,
    AgentID.AWS_CLOUD:  aws_agent,
    AgentID.GCP_CLOUD:  gcp_agent,
}

# ── Available LLM models (selectable in WSO2 portal) ────────────────────────
AVAILABLE_MODELS = {
    "claude-sonnet-4-6":    {"provider": "Anthropic",  "context_k": 200, "cost_per_1k": 0.003},
    "gemini-2.0-pro":       {"provider": "Google",     "context_k": 128, "cost_per_1k": 0.002},
    "gpt-4o":               {"provider": "OpenAI",     "context_k": 128, "cost_per_1k": 0.005},
    "amazon-nova-pro":      {"provider": "AWS Bedrock","context_k": 300, "cost_per_1k": 0.0008},
    "mistral-large":        {"provider": "Mistral AI", "context_k": 128, "cost_per_1k": 0.002},
}


class OrchestratorAgent:
    """
    WSO2 Agent Manager – Master Orchestrator for Morrisons.

    All demo scenarios flow through this class.
    The orchestrator is model-agnostic: the active_model is set in WSO2 portal.
    """

    agent_id    = AgentID.ORCHESTRATOR
    active_model = "claude-sonnet-4-6"    # Default – changeable in WSO2 portal
    guardrails  = GuardrailEngine()

    # ════════════════════════════════════════════════════════════════════════
    # SCENARIO 1 – Supply Chain: Stock Alert → SAP PO → Oracle Approval
    # ════════════════════════════════════════════════════════════════════════
    async def run_supply_chain_workflow(
        self,
        sku: str,
        store_id: str = "STORE-001",
        notify: bool = True,
    ) -> Dict[str, Any]:
        """
        Multi-agent supply chain orchestration:

        Step 1  → SAP Agent:      check_stock_level
        Step 2  → GCP Agent:      call_vertex_ai_prediction (demand forecast)
        Step 3  → SAP Agent:      raise_purchase_order
        Step 4  → Oracle Agent:   approve_purchase_order  (budget check + AME)
        Step 5  → AWS Agent:      send_sns_notification   (supplier + ops alert)
        Step 6  → GCP Agent:      publish_pubsub_event    (event bus)
        """
        trace_id = uuid.uuid4().hex
        with trace_span(self.agent_id, "supply_chain_workflow", trace_id=trace_id,
                        attributes={"sku": sku, "store": store_id}):

            log_event(self.agent_id, "═══ SUPPLY CHAIN WORKFLOW START ═══",
                      {"sku": sku, "store": store_id, "trace_id": trace_id})

            results: Dict[str, Any] = {"trace_id": trace_id, "workflow": "supply_chain"}

            # ── Step 1: Check stock ──────────────────────────────────────────
            guard = await self.guardrails.check_input(
                "supply_chain", {"sku": sku, "store_id": store_id})
            if not guard.allowed:
                return self._guardrail_blocked(trace_id, guard)

            stock = await sap_agent.check_stock_level(sku, store_id, trace_id=trace_id)
            results["stock_check"] = stock
            log_event(self.agent_id, "Step 1 complete: stock checked", stock)

            if not stock.get("below_reorder"):
                return {**results, "outcome": "No action needed – stock level OK",
                        "action_taken": False}

            # ── Step 2: Demand forecast (parallel with supplier lookup) ──────
            log_event(self.agent_id, "Step 2: Parallel – demand forecast + supplier info")
            demand_task    = gcp_agent.call_vertex_ai_prediction(
                "morrisons-demand-forecast-v3",
                [{"sku": sku, "store_id": store_id}],
                trace_id=trace_id,
            )
            supplier_task  = sap_agent.get_supplier_info(
                stock["alert"]["supplier_id"], trace_id=trace_id
            )
            demand_result, supplier_info = await asyncio.gather(demand_task, supplier_task)
            results["demand_forecast"] = demand_result
            results["supplier_info"]   = supplier_info

            # ── Step 3: Raise Purchase Order in SAP ──────────────────────────
            predicted_units = demand_result["predictions"][0].get("predicted_units_next_week", 500)
            qty_to_order    = max(predicted_units, stock["alert"]["suggested_qty"])

            guard2 = await self.guardrails.check_input(
                "purchase_order",
                {"sku": sku, "quantity": qty_to_order, "supplier": supplier_info.get("name")},
            )
            if not guard2.allowed:
                return self._guardrail_blocked(trace_id, guard2)

            po = await sap_agent.raise_purchase_order(
                sku=sku,
                quantity=qty_to_order,
                supplier_id=stock["alert"]["supplier_id"],
                trace_id=trace_id,
            )
            results["purchase_order"] = po
            log_event(self.agent_id, "Step 3 complete: PO raised", {"po": po["po_number"]})

            # ── Step 4: Oracle Finance Approval ──────────────────────────────
            category_cc_map = {"Fresh Meat": "CC-FRESH-001", "Dairy": "CC-DAIRY-004",
                               "Bakery": "CC-BAKERY-002", "Fish": "CC-FISH-003"}
            cost_centre = category_cc_map.get(stock.get("category", ""), "CC-FRESH-001")

            approval = await oracle_agent.approve_purchase_order(
                po_number=po["po_number"],
                total_value=po["total_value"],
                cost_centre=cost_centre,
                category=stock.get("category", "General"),
                trace_id=trace_id,
            )
            results["finance_approval"] = approval
            log_event(self.agent_id, "Step 4 complete: Oracle approval",
                      {"approved": approval["approved"], "tier": approval["approval_tier"]})

            # ── Step 5 & 6: Notify (parallel SNS + Pub/Sub) ─────────────────
            if notify:
                log_event(self.agent_id, "Step 5+6: Parallel notifications")
                sns_task = aws_agent.send_sns_notification(
                    topic="morrisons-po-approvals",
                    subject=f"PO {po['po_number']} {'Approved' if approval['approved'] else 'Pending Approval'}",
                    message=f"SKU {sku} reorder: {qty_to_order} units from {supplier_info.get('name')}. "
                            f"Value: £{po['total_value']:,.2f}. "
                            f"Approval: {approval['notes']}",
                    trace_id=trace_id,
                )
                pubsub_task = gcp_agent.publish_pubsub_event(
                    topic="morrisons-stock-events",
                    event_type="PURCHASE_ORDER_CREATED",
                    data={"po_number": po["po_number"], "sku": sku, "qty": qty_to_order,
                          "approved": approval["approved"]},
                    trace_id=trace_id,
                )
                sns_result, pubsub_result = await asyncio.gather(sns_task, pubsub_task)
                results["notification_sns"]    = sns_result
                results["notification_pubsub"] = pubsub_result

            results["outcome"] = (
                f"✔ PO {po['po_number']} raised and {'APPROVED' if approval['approved'] else 'PENDING APPROVAL'}. "
                f"Ordering {qty_to_order} units of {stock['product_name']} "
                f"from {supplier_info.get('name')}. "
                f"Total value: £{po['total_value']:,.2f}. "
                f"Delivery: {po['delivery_date']}."
            )
            results["action_taken"] = True
            increment("orchestrator.supply_chain_completed")
            log_event(self.agent_id, "═══ SUPPLY CHAIN WORKFLOW COMPLETE ═══", {"outcome": results["outcome"]})
            render_trace(trace_id)
            return results

    # ════════════════════════════════════════════════════════════════════════
    # SCENARIO 2 – Store Operations: IoT + SAP + GCP analytics
    # ════════════════════════════════════════════════════════════════════════
    async def run_store_ops_query(
        self,
        store_id: str,
        query: str,
    ) -> Dict[str, Any]:
        """
        Natural-language store operations query.
        Orchestrator fans out to relevant agents based on query intent.

        Example: "What is the status of store STORE-001 right now?"
        → GCP IoT data + SAP stock + AWS sales trends (parallel)
        """
        trace_id = uuid.uuid4().hex
        with trace_span(self.agent_id, "store_ops_query", trace_id=trace_id,
                        attributes={"store_id": store_id}):

            log_event(self.agent_id, "═══ STORE OPS QUERY ═══",
                      {"store": store_id, "query": query})

            guard = await self.guardrails.check_input("store_ops", {"store_id": store_id, "query": query})
            if not guard.allowed:
                return self._guardrail_blocked(trace_id, guard)

            # Fan out in parallel
            tasks = {
                "iot_fridge_01": gcp_agent.get_store_iot_data("STORE-001-FRIDGE-12", trace_id=trace_id),
                "iot_fridge_02": gcp_agent.get_store_iot_data("STORE-001-FRIDGE-07", trace_id=trace_id),
                "iot_sco":       gcp_agent.get_store_iot_data("STORE-001-SCO-03",    trace_id=trace_id),
                "beef_stock":    sap_agent.check_stock_level("SKU-BEEF-001", store_id, trace_id=trace_id),
                "milk_stock":    sap_agent.check_stock_level("SKU-MILK-003", store_id, trace_id=trace_id),
                "sales_bq":      gcp_agent.run_bigquery_analytics("top_selling_skus", trace_id=trace_id),
            }
            gathered = await asyncio.gather(*tasks.values(), return_exceptions=True)
            data = dict(zip(tasks.keys(), gathered))

            alerts = []
            if isinstance(data.get("iot_fridge_02"), dict) and data["iot_fridge_02"].get("alert"):
                alerts.append(f"⚠ Fridge STORE-001-FRIDGE-07 temperature alert: "
                               f"{data['iot_fridge_02'].get('temperature_c')}°C (max 5°C)")
            for key in ["beef_stock", "milk_stock"]:
                if isinstance(data.get(key), dict) and data[key].get("below_reorder"):
                    alerts.append(f"⚠ Low stock: {data[key].get('product_name')} – "
                                   f"{data[key].get('current_stock')} units remaining")

            increment("orchestrator.store_ops_completed")
            render_trace(trace_id)
            return {
                "trace_id":   trace_id,
                "store_id":   store_id,
                "query":      query,
                "iot_data":   {k: v for k, v in data.items() if k.startswith("iot_")},
                "stock_data": {k: v for k, v in data.items() if k.endswith("_stock")},
                "analytics":  data.get("sales_bq"),
                "alerts":     alerts,
                "alert_count": len(alerts),
                "model_used": self.active_model,
            }

    # ════════════════════════════════════════════════════════════════════════
    # SCENARIO 3 – Customer Personalisation: Salesforce + GCP Vertex + AWS
    # ════════════════════════════════════════════════════════════════════════
    async def run_customer_personalisation(
        self,
        customer_id: str,
        channel: str = "app",
    ) -> Dict[str, Any]:
        """
        Real-time personalisation pipeline:

        Step 1  → Salesforce:  get_customer_profile
        Step 2  → GCP Vertex:  churn propensity prediction (parallel with Salesforce)
        Step 3  → Salesforce:  generate_personalised_offer (based on tier + category)
        Step 4  → GCP Pub/Sub: publish_pubsub_event (trigger delivery pipeline)
        Step 5  → AWS:         query_dynamodb_session (check if customer is online now)
        """
        trace_id = uuid.uuid4().hex
        with trace_span(self.agent_id, "customer_personalisation", trace_id=trace_id,
                        attributes={"customer_id": customer_id, "channel": channel}):

            log_event(self.agent_id, "═══ CUSTOMER PERSONALISATION ═══",
                      {"customer": customer_id, "channel": channel})

            guard = await self.guardrails.check_input(
                "customer_data", {"customer_id": customer_id})
            if not guard.allowed:
                return self._guardrail_blocked(trace_id, guard)

            # Step 1+2: Profile + churn in parallel
            profile_task = salesforce_agent.get_customer_profile(
                customer_id, include_purchase_history=True, trace_id=trace_id)
            churn_task   = gcp_agent.call_vertex_ai_prediction(
                "morrisons-churn-propensity-v1",
                [{"customer_id": customer_id}], trace_id=trace_id)

            profile, churn = await asyncio.gather(profile_task, churn_task)

            # Step 3: Generate offer
            top_cat = profile.get("top_categories", ["General"])[0]
            offer = await salesforce_agent.generate_personalised_offer(
                customer_id=customer_id,
                category=top_cat,
                channel=channel,
                trace_id=trace_id,
            )

            # Step 4+5: Publish event + check online session (parallel)
            churn_prob = churn["predictions"][0].get("churn_probability", 0)
            pubsub_task = gcp_agent.publish_pubsub_event(
                topic="morrisons-agent-events",
                event_type="OFFER_GENERATED",
                data={"customer_id": customer_id, "offer_id": offer["offer_id"],
                      "churn_probability": churn_prob},
                trace_id=trace_id,
            )
            session_task = aws_agent.query_dynamodb_session("SESSION-ABC123", trace_id=trace_id)
            pubsub_result, session = await asyncio.gather(pubsub_task, session_task)

            recommendation = churn["predictions"][0].get("recommended_action", "no_action")
            if churn_prob > 0.35:
                await salesforce_agent.update_customer_segment(
                    customer_id, "AT_RISK_CHURN",
                    reason=f"Vertex AI churn probability: {churn_prob:.1%}", trace_id=trace_id)

            increment("orchestrator.personalisation_completed")
            render_trace(trace_id)
            return {
                "trace_id":          trace_id,
                "customer_id":       customer_id,
                "customer_name":     profile.get("name"),
                "loyalty_tier":      profile.get("loyalty_tier"),
                "offer":             offer,
                "churn_probability": f"{churn_prob:.1%}",
                "recommendation":    recommendation,
                "is_online_now":     not session.get("error"),
                "online_basket":     session if not session.get("error") else None,
                "model_used":        self.active_model,
                "outcome": (
                    f"✔ Offer {offer['offer_id']} generated for {profile.get('name')} "
                    f"({profile.get('loyalty_tier')} tier). "
                    f"{offer['description']}. "
                    f"Churn risk: {churn_prob:.1%}."
                ),
            }

    # ════════════════════════════════════════════════════════════════════════
    # SCENARIO 4 – Finance & Procurement: full P2P flow
    # ════════════════════════════════════════════════════════════════════════
    async def run_finance_procurement(
        self,
        sku: str,
        quantity: int,
        supplier_id: str,
        cost_centre: str,
        requestor: str = "STORE-MGR-001",
    ) -> Dict[str, Any]:
        """
        Purchase-to-Pay (P2P) multi-agent workflow:

        Step 1  → Oracle:      get_budget_availability
        Step 2  → Salesforce:  get_supplier_account  (supplier health check)
        Step 3  → SAP:         get_supplier_info      (lead times, contracts)
        Step 4  → SAP:         raise_purchase_order
        Step 5  → Oracle:      approve_purchase_order (AME routing)
        Step 6  → GCP DocAI:   run_document_ai        (invoice parsing on receipt)
        Step 7  → Oracle:      create_journal_entry   (financial posting)
        Step 8  → AWS:         send_sns_notification  (finance team alert)
        """
        trace_id = uuid.uuid4().hex
        with trace_span(self.agent_id, "finance_procurement_workflow", trace_id=trace_id,
                        attributes={"sku": sku, "qty": quantity, "cc": cost_centre}):

            log_event(self.agent_id, "═══ FINANCE & PROCUREMENT WORKFLOW ═══",
                      {"sku": sku, "qty": quantity, "supplier": supplier_id})

            guard = await self.guardrails.check_input(
                "finance", {"cost_centre": cost_centre, "quantity": quantity})
            if not guard.allowed:
                return self._guardrail_blocked(trace_id, guard)

            # Step 1+2+3: Budget check + supplier health (parallel)
            budget_task   = oracle_agent.get_budget_availability(cost_centre, trace_id=trace_id)
            sf_supp_task  = salesforce_agent.get_supplier_account(supplier_id, trace_id=trace_id)
            sap_supp_task = sap_agent.get_supplier_info(supplier_id, trace_id=trace_id)
            budget, sf_supplier, sap_supplier = await asyncio.gather(
                budget_task, sf_supp_task, sap_supp_task)

            if budget.get("status") == "RED":
                return {
                    "trace_id": trace_id,
                    "outcome": f"✗ Blocked: cost centre {cost_centre} budget exhausted "
                               f"({budget.get('utilisation_pct')}% used). Escalating to Finance Director.",
                    "guardrail": "BUDGET_EXCEEDED",
                    "budget":    budget,
                }

            # Step 4: Raise PO in SAP
            po = await sap_agent.raise_purchase_order(
                sku=sku, quantity=quantity, supplier_id=supplier_id, trace_id=trace_id)

            # Step 5: Oracle approval
            category_map = {"CC-FRESH-001": "Fresh Meat", "CC-DAIRY-004": "Dairy",
                            "CC-BAKERY-002": "Bakery", "CC-FISH-003": "Fish"}
            approval = await oracle_agent.approve_purchase_order(
                po_number=po["po_number"],
                total_value=po["total_value"],
                cost_centre=cost_centre,
                category=category_map.get(cost_centre, "General"),
                requester=requestor,
                trace_id=trace_id,
            )

            # Step 6: Simulate invoice receipt + Document AI parsing
            invoice = await gcp_agent.run_document_ai(
                "supplier_invoice", trace_id=trace_id)

            # Step 7: Journal entry in Oracle GL
            je = await oracle_agent.create_journal_entry(
                description=f"Goods receipt PO {po['po_number']}",
                debit_account="500100",   # Purchases account
                credit_account="200010",  # Accounts payable
                amount=po["total_value"],
                cost_centre=cost_centre,
                trace_id=trace_id,
            )

            # Step 8: Finance alert
            await aws_agent.send_sns_notification(
                topic="morrisons-po-approvals",
                subject=f"P2P Complete: {po['po_number']}",
                message=f"PO raised, approved, and journal posted. "
                        f"Value: £{po['total_value']:,.2f}. Journal: {je['journal_id']}",
                trace_id=trace_id,
            )

            increment("orchestrator.finance_procurement_completed")
            render_trace(trace_id)
            return {
                "trace_id":          trace_id,
                "workflow":          "finance_procurement",
                "purchase_order":    po,
                "budget_check":      budget,
                "supplier_health":   sf_supplier.get("health_score"),
                "approval":          approval,
                "invoice_parsed":    invoice,
                "journal_entry":     je,
                "model_used":        self.active_model,
                "outcome": (
                    f"✔ P2P workflow complete. PO {po['po_number']} "
                    f"{'approved' if approval['approved'] else 'pending human approval'}. "
                    f"Journal {je['journal_id']} posted to Oracle GL. "
                    f"Total: £{po['total_value']:,.2f}."
                ),
            }

    # ── Utility helpers ───────────────────────────────────────────────────────
    def _guardrail_blocked(self, trace_id: str, guard: GuardrailResult) -> Dict[str, Any]:
        log_event(self.agent_id, f"GUARDRAIL BLOCKED: {guard.rule}", {"reason": guard.reason})
        increment("guardrails.blocked")
        return {
            "trace_id":  trace_id,
            "status":    "BLOCKED",
            "guardrail": guard.rule,
            "reason":    guard.reason,
            "outcome":   f"✗ Request blocked by guardrail '{guard.rule}': {guard.reason}",
        }

    def switch_model(self, model_name: str) -> str:
        """Switch active LLM model (callable from WSO2 portal)."""
        if model_name not in AVAILABLE_MODELS:
            return f"Unknown model. Available: {list(AVAILABLE_MODELS.keys())}"
        self.active_model = model_name
        log_event(self.agent_id, f"Model switched to {model_name}", AVAILABLE_MODELS[model_name])
        return f"Active model is now: {model_name}"

    def list_agents(self) -> Dict[str, Any]:
        """Return the agent catalogue (shown in WSO2 portal)."""
        return {
            agent_id.value: {
                "status": "ONLINE",
                "transport": "MCP-SSE",
                "model": self.active_model,
            }
            for agent_id in AGENT_REGISTRY
        }

    def show_health(self) -> None:
        render_agent_health()


# Singleton
orchestrator = OrchestratorAgent()
