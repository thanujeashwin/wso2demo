"""
Morrisons SAP ERP Agent
═══════════════════════
Registered in WSO2 Agent Manager as: morrisons-sap-erp-agent

Capabilities:
  • check_stock_level        – Query SAP MM (Materials Management) for real-time stock
  • raise_purchase_order     – Create a PO in SAP MM / SAP S/4HANA
  • get_supplier_info        – Look up vendor master data from SAP
  • get_goods_movement       – Retrieve goods receipts / goods issues (MIGO)
  • run_demand_forecast      – Pull rolling 90-day demand forecast from SAP APO/IBP

Transport:
  • Exposes tools via MCP (Model Context Protocol) over SSE
  • WSO2 API Manager gateway enforces OAuth2 + rate limits
  • All calls emit OTel spans → WSO2 Choreo Observability

Integration note for Morrisons:
  SAP S/4HANA is running on GCP (Morrisons migrated in 2023).
  The agent hits SAP's OData v4 APIs via the WSO2 ESB proxy.
"""
from __future__ import annotations

import asyncio
import random
import uuid
from datetime import date, timedelta
from typing import Any, Dict, Optional

from shared.models import (
    AgentID, AgentMessage, AgentResponse, AgentStatus,
    Domain, Priority, PurchaseOrder, StockAlert,
)
from shared.observability import log_event, trace_span, increment

# ── Demo data: realistic Morrisons SKUs and suppliers ───────────────────────
MOCK_STOCK: Dict[str, Dict[str, Any]] = {
    "SKU-BEEF-001": {"name": "Morrisons Best Beef Mince 500g", "stock": 48,  "reorder": 120, "supplier": "SUP-001", "category": "Fresh Meat"},
    "SKU-MILK-003": {"name": "Morrisons Whole Milk 4 Pints",   "stock": 210, "reorder": 300, "supplier": "SUP-002", "category": "Dairy"},
    "SKU-BREA-007": {"name": "Morrisons White Thick Bread",     "stock": 35,  "reorder": 150, "supplier": "SUP-003", "category": "Bakery"},
    "SKU-CHIC-002": {"name": "Morrisons Chicken Breast 500g",   "stock": 12,  "reorder": 80,  "supplier": "SUP-001", "category": "Fresh Meat"},
    "SKU-SALM-004": {"name": "Morrisons Scottish Salmon 240g",  "stock": 5,   "reorder": 60,  "supplier": "SUP-004", "category": "Fish"},
}

MOCK_SUPPLIERS: Dict[str, Dict[str, Any]] = {
    "SUP-001": {"name": "British Meat Supplies Ltd",   "lead_days": 2, "contract": "C-2024-001", "payment_terms": "NET30"},
    "SUP-002": {"name": "Northern Dairy Co-op",        "lead_days": 1, "contract": "C-2024-002", "payment_terms": "NET14"},
    "SUP-003": {"name": "Allied Bakery UK",            "lead_days": 1, "contract": "C-2024-003", "payment_terms": "NET7"},
    "SUP-004": {"name": "Scottish Seafood Partners",   "lead_days": 3, "contract": "C-2024-004", "payment_terms": "NET21"},
}

PO_COUNTER = {"n": 4500}


class SAPERPAgent:
    """
    WSO2 Agent Manager – SAP ERP Agent
    Wraps SAP S/4HANA OData v4 APIs behind an MCP tool surface.
    """

    agent_id = AgentID.SAP_ERP

    # ── Tool: check_stock_level ──────────────────────────────────────────────
    async def check_stock_level(
        self,
        sku: str,
        store_id: str = "STORE-001",
        trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        [MCP Tool] Query SAP MM for current stock level.

        SAP OData endpoint (proxied via WSO2 ESB):
          GET /sap/opu/odata/sap/API_MATERIAL_DOCUMENT_SRV/A_MaterialDocumentItem
              ?$filter=Material eq '{sku}' and StorageLocation eq '{store_id}'
        """
        with trace_span(self.agent_id, "check_stock_level", trace_id=trace_id,
                        attributes={"sku": sku, "store_id": store_id}):
            log_event(self.agent_id, "Checking SAP MM stock", {"sku": sku, "store": store_id})
            await asyncio.sleep(0.3)  # simulate SAP OData round-trip

            if sku not in MOCK_STOCK:
                return {"error": f"SKU {sku} not found in SAP material master"}

            item = MOCK_STOCK[sku]
            below_reorder = item["stock"] < item["reorder"]
            increment("sap.stock_checks")

            alert = None
            if below_reorder:
                alert = StockAlert(
                    sku=sku,
                    product_name=item["name"],
                    store_id=store_id,
                    current_stock=item["stock"],
                    reorder_level=item["reorder"],
                    suggested_qty=item["reorder"] * 2 - item["stock"],
                    supplier_id=item["supplier"],
                    category=item["category"],
                ).model_dump()

            return {
                "sku": sku,
                "product_name": item["name"],
                "store_id": store_id,
                "current_stock": item["stock"],
                "reorder_level": item["reorder"],
                "below_reorder": below_reorder,
                "category": item["category"],
                "alert": alert,
                "sap_plant": "GBR1",
                "sap_storage_location": store_id,
            }

    # ── Tool: raise_purchase_order ───────────────────────────────────────────
    async def raise_purchase_order(
        self,
        sku: str,
        quantity: int,
        supplier_id: str,
        delivery_date: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        [MCP Tool] Create a Purchase Order in SAP MM.

        SAP OData endpoint (proxied via WSO2 ESB):
          POST /sap/opu/odata/sap/API_PURCHASEORDER_PROCESS_SRV/A_PurchaseOrder
        """
        with trace_span(self.agent_id, "raise_purchase_order", trace_id=trace_id,
                        attributes={"sku": sku, "qty": quantity, "supplier": supplier_id}):
            log_event(self.agent_id, "Raising SAP Purchase Order",
                      {"sku": sku, "qty": quantity, "supplier": supplier_id})
            await asyncio.sleep(0.4)

            PO_COUNTER["n"] += 1
            po_number = f"PO-{PO_COUNTER['n']:06d}"

            item = MOCK_STOCK.get(sku, {})
            supplier = MOCK_SUPPLIERS.get(supplier_id, {})
            unit_price = round(random.uniform(0.80, 12.50), 2)
            total = round(unit_price * quantity, 2)

            if not delivery_date:
                lead_days = supplier.get("lead_days", 3)
                delivery_date = (date.today() + timedelta(days=lead_days)).isoformat()

            po = PurchaseOrder(
                po_number=po_number,
                supplier_id=supplier_id,
                supplier_name=supplier.get("name", "Unknown Supplier"),
                sku=sku,
                quantity=quantity,
                unit_price=unit_price,
                total_value=total,
                delivery_date=delivery_date,
                status="CREATED",
            )
            increment("sap.purchase_orders_created")
            log_event(self.agent_id, f"SAP PO created: {po_number}", po.model_dump())
            return {**po.model_dump(), "sap_document_number": f"4500{PO_COUNTER['n']}"}

    # ── Tool: get_supplier_info ──────────────────────────────────────────────
    async def get_supplier_info(
        self,
        supplier_id: str,
        trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """[MCP Tool] Retrieve vendor master data from SAP BP (Business Partner)."""
        with trace_span(self.agent_id, "get_supplier_info", trace_id=trace_id,
                        attributes={"supplier_id": supplier_id}):
            await asyncio.sleep(0.2)
            supplier = MOCK_SUPPLIERS.get(supplier_id)
            if not supplier:
                return {"error": f"Supplier {supplier_id} not found"}
            return {**supplier, "supplier_id": supplier_id, "currency": "GBP",
                    "country": "GB", "sap_vendor_number": f"V{supplier_id[-3:]}001"}

    # ── Tool: get_goods_movement ─────────────────────────────────────────────
    async def get_goods_movement(
        self,
        sku: str,
        days: int = 7,
        trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """[MCP Tool] Retrieve recent goods receipts/issues (SAP MIGO transactions)."""
        with trace_span(self.agent_id, "get_goods_movement", trace_id=trace_id,
                        attributes={"sku": sku, "days": days}):
            await asyncio.sleep(0.25)
            movements = []
            for i in range(days):
                if random.random() > 0.3:
                    movements.append({
                        "date": (date.today() - timedelta(days=i)).isoformat(),
                        "movement_type": random.choice(["101-GR", "261-GI", "551-Scrap"]),
                        "quantity": random.randint(20, 200),
                        "document": f"490{random.randint(1000,9999)}",
                    })
            return {"sku": sku, "period_days": days, "movements": movements}

    # ── Tool: run_demand_forecast ────────────────────────────────────────────
    async def run_demand_forecast(
        self,
        sku: str,
        horizon_days: int = 90,
        trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """[MCP Tool] Pull 90-day demand forecast from SAP IBP (Integrated Business Planning)."""
        with trace_span(self.agent_id, "run_demand_forecast", trace_id=trace_id,
                        attributes={"sku": sku, "horizon": horizon_days}):
            await asyncio.sleep(0.5)
            base_demand = random.randint(80, 160)
            forecast = [
                {
                    "week": f"W{i+1}",
                    "forecast_qty": base_demand + random.randint(-20, 30),
                    "confidence": round(random.uniform(0.72, 0.95), 2),
                }
                for i in range(horizon_days // 7)
            ]
            return {
                "sku": sku,
                "horizon_days": horizon_days,
                "model": "SAP_IBP_ARIMA",
                "forecast": forecast,
                "total_forecast_qty": sum(f["forecast_qty"] for f in forecast),
            }

    # ── MCP dispatch (called by WSO2 Agent Manager MCP runtime) ─────────────
    async def handle_mcp_call(
        self, tool_name: str, arguments: Dict[str, Any], trace_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Route an incoming MCP tool call to the correct method."""
        tools = {
            "check_stock_level":    self.check_stock_level,
            "raise_purchase_order": self.raise_purchase_order,
            "get_supplier_info":    self.get_supplier_info,
            "get_goods_movement":   self.get_goods_movement,
            "run_demand_forecast":  self.run_demand_forecast,
        }
        if tool_name not in tools:
            return {"error": f"Unknown tool: {tool_name}"}
        return await tools[tool_name](**arguments, trace_id=trace_id)

    # ── Agent message handler (called by WSO2 orchestrator) ─────────────────
    async def process_message(self, msg: AgentMessage) -> AgentResponse:
        """Handle a structured AgentMessage from the Orchestrator."""
        tid = msg.trace_context.get("trace_id", str(uuid.uuid4()).replace("-", ""))
        log_event(self.agent_id, f"Received task from {msg.from_agent.value}", msg.payload)
        try:
            tool   = msg.payload.get("tool")
            args   = msg.payload.get("args", {})
            result = await self.handle_mcp_call(tool, args, trace_id=tid)
            return AgentResponse(
                message_id=str(uuid.uuid4()),
                correlation_id=msg.correlation_id,
                from_agent=self.agent_id,
                status=AgentStatus.COMPLETED,
                data=result,
            )
        except Exception as exc:
            return AgentResponse(
                message_id=str(uuid.uuid4()),
                correlation_id=msg.correlation_id,
                from_agent=self.agent_id,
                status=AgentStatus.FAILED,
                data={},
                error=str(exc),
            )


# Singleton – WSO2 Agent Manager imports this
sap_agent = SAPERPAgent()
