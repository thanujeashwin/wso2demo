"""
Shared data models for the Morrisons WSO2 Agent Manager Demo.
All agents use these Pydantic models for type-safe communication.
"""
from __future__ import annotations
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from datetime import datetime


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class AgentID(str, Enum):
    ORCHESTRATOR    = "morrisons-orchestrator"
    SAP_ERP         = "morrisons-sap-erp-agent"
    ORACLE_ERP      = "morrisons-oracle-erp-agent"
    SALESFORCE      = "morrisons-salesforce-agent"
    AWS_CLOUD       = "morrisons-aws-cloud-agent"
    GCP_CLOUD       = "morrisons-gcp-cloud-agent"


class Priority(str, Enum):
    LOW      = "low"
    MEDIUM   = "medium"
    HIGH     = "high"
    CRITICAL = "critical"


class AgentStatus(str, Enum):
    IDLE        = "idle"
    PROCESSING  = "processing"
    WAITING     = "waiting"
    COMPLETED   = "completed"
    FAILED      = "failed"
    GUARDRAILED = "guardrailed"


class Domain(str, Enum):
    SUPPLY_CHAIN    = "supply_chain"
    STORE_OPS       = "store_operations"
    CUSTOMER        = "customer_personalisation"
    FINANCE         = "finance_procurement"


# ---------------------------------------------------------------------------
# Base message envelope — all inter-agent messages use this
# ---------------------------------------------------------------------------

class AgentMessage(BaseModel):
    message_id:     str = Field(..., description="Unique message ID (UUID)")
    correlation_id: str = Field(..., description="Ties a request→response chain together")
    from_agent:     AgentID
    to_agent:       AgentID
    domain:         Domain
    priority:       Priority = Priority.MEDIUM
    timestamp:      datetime = Field(default_factory=datetime.utcnow)
    payload:        Dict[str, Any]
    trace_context:  Dict[str, str] = Field(default_factory=dict,
                        description="OpenTelemetry / W3C trace-context headers")


class AgentResponse(BaseModel):
    message_id:     str
    correlation_id: str
    from_agent:     AgentID
    status:         AgentStatus
    timestamp:      datetime = Field(default_factory=datetime.utcnow)
    data:           Dict[str, Any]
    error:          Optional[str] = None
    guardrail_hit:  Optional[str] = None   # which guardrail fired, if any
    latency_ms:     Optional[int] = None


# ---------------------------------------------------------------------------
# Domain-specific models
# ---------------------------------------------------------------------------

class StockAlert(BaseModel):
    sku:            str
    product_name:   str
    store_id:       str
    current_stock:  int
    reorder_level:  int
    suggested_qty:  int
    supplier_id:    str
    category:       str


class PurchaseOrder(BaseModel):
    po_number:      str
    supplier_id:    str
    supplier_name:  str
    sku:            str
    quantity:       int
    unit_price:     float
    total_value:    float
    currency:       str = "GBP"
    delivery_date:  str
    status:         str = "PENDING"


class FinanceApproval(BaseModel):
    po_number:      str
    approver:       str
    approved:       bool
    budget_code:    str
    cost_centre:    str
    notes:          str = ""


class CustomerProfile(BaseModel):
    customer_id:    str
    name:           str
    loyalty_tier:   str        # Bronze / Silver / Gold / Platinum
    lifetime_value: float
    preferred_store: str
    top_categories: List[str]


class Offer(BaseModel):
    offer_id:       str
    customer_id:    str
    description:    str
    discount_pct:   float
    valid_until:    str
    channel:        str        # email / app / in-store


class ObservabilitySpan(BaseModel):
    """Lightweight OTel-style span emitted by every agent."""
    trace_id:       str
    span_id:        str
    parent_span_id: Optional[str] = None
    agent_id:       AgentID
    operation:      str
    start_time:     datetime
    end_time:       Optional[datetime] = None
    status:         str = "OK"       # OK | ERROR
    attributes:     Dict[str, Any] = Field(default_factory=dict)
    events:         List[Dict[str, Any]] = Field(default_factory=list)
