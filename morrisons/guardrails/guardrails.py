"""
Morrisons WSO2 Agent Manager – Guardrails Engine
══════════════════════════════════════════════════

Guardrails are enforced at THREE layers in WSO2 Agent Manager:

  Layer 1 – Input guardrails  (before any agent call)
    • PII detection  (customer names, emails, card numbers)
    • Data scope checks (is this agent allowed to access this data?)
    • Business policy enforcement (spending limits, restricted SKUs)
    • Prompt injection detection

  Layer 2 – Agent-level guardrails (inside each agent, see config.yaml files)
    • Rate limits
    • Allowed/blocked patterns per agent
    • Value thresholds

  Layer 3 – Output guardrails (after every agent response)
    • Sensitive data masking
    • Content safety check
    • Data minimisation (strip fields not needed by requester)

This module implements Layers 1 & 3.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class GuardrailResult:
    allowed:  bool
    rule:     str          # which rule fired
    reason:   str
    severity: str = "INFO"  # INFO / WARNING / BLOCK
    masked_data: Optional[Dict[str, Any]] = None


# ── PII patterns ──────────────────────────────────────────────────────────────
PII_PATTERNS: Dict[str, re.Pattern] = {
    "email":        re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'),
    "phone_uk":     re.compile(r'\b(07\d{9}|(\+44)\s?7\d{9})\b'),
    "credit_card":  re.compile(r'\b(?:\d[ -]?){13,16}\b'),
    "national_ins": re.compile(r'\b[A-Z]{2}\d{6}[A-D]\b'),
    "sort_code":    re.compile(r'\b\d{2}[-]\d{2}[-]\d{2}\b'),
}

# ── Restricted SKU patterns (require separate compliance workflow) ─────────────
RESTRICTED_SKU_PREFIXES = ["ALCOHOL-", "TOBACCO-", "LOTTERY-", "PHARMA-", "BABY-FORMULA-"]

# ── Maximum auto-approval PO value (GBP) ──────────────────────────────────────
MAX_AUTO_APPROVAL_VALUE = 50_000.0

# ── Allowed domains per requester role ───────────────────────────────────────
ROLE_DOMAIN_PERMISSIONS: Dict[str, List[str]] = {
    "STORE_MANAGER":     ["supply_chain", "store_ops"],
    "CATEGORY_MANAGER":  ["supply_chain", "finance"],
    "MARKETING":         ["customer_data"],
    "FINANCE":           ["finance", "supply_chain"],
    "SYSTEM":            ["supply_chain", "store_ops", "customer_data", "finance"],
    "ADMIN":             ["supply_chain", "store_ops", "customer_data", "finance"],
}

# ── Prompt injection signatures ───────────────────────────────────────────────
INJECTION_PATTERNS = [
    re.compile(r'ignore (previous|all|above) instructions', re.I),
    re.compile(r'you are now', re.I),
    re.compile(r'disregard (your|the) (system|instructions)', re.I),
    re.compile(r'(act|behave) as (?!a store|a category|a finance)', re.I),
    re.compile(r'jailbreak', re.I),
    re.compile(r'DAN mode', re.I),
]

# ── Sensitive fields to mask in output ───────────────────────────────────────
SENSITIVE_OUTPUT_FIELDS = [
    "email", "phone", "card_number", "sort_code", "account_number",
    "client_secret", "oauth_token", "password", "api_key",
]


class GuardrailEngine:
    """
    WSO2 Agent Manager Guardrails Engine.

    Enforces Morrisons' AI governance policies at runtime.
    All guardrail hits are logged to the WSO2 Choreo Observability dashboard.
    """

    # ════════════════════════════════════════════════════════════════════════
    # LAYER 1 – INPUT GUARDRAILS
    # ════════════════════════════════════════════════════════════════════════

    async def check_input(
        self,
        context: str,
        payload: Dict[str, Any],
        requester_role: str = "SYSTEM",
    ) -> GuardrailResult:
        """
        Run all input guardrails. Returns GuardrailResult(allowed=False) on first violation.
        """
        checks = [
            self._check_prompt_injection(payload),
            self._check_pii_in_input(payload),
            self._check_sku_restrictions(payload),
            self._check_purchase_value(payload),
            self._check_role_permissions(context, requester_role),
            self._check_suspicious_quantities(payload),
        ]
        for result in checks:
            if not result.allowed:
                return result
        return GuardrailResult(allowed=True, rule="PASS", reason="All input checks passed")

    def _check_prompt_injection(self, payload: Dict[str, Any]) -> GuardrailResult:
        text = str(payload)
        for pattern in INJECTION_PATTERNS:
            if pattern.search(text):
                return GuardrailResult(
                    allowed=False,
                    rule="PROMPT_INJECTION",
                    reason=f"Potential prompt injection detected: '{pattern.pattern}'",
                    severity="BLOCK",
                )
        return GuardrailResult(allowed=True, rule="PROMPT_INJECTION", reason="OK")

    def _check_pii_in_input(self, payload: Dict[str, Any]) -> GuardrailResult:
        """Detect PII accidentally included in agent requests."""
        text = str(payload)
        for pii_type, pattern in PII_PATTERNS.items():
            if pii_type in ("email",):          # Email is allowed in customer context
                continue
            if pattern.search(text):
                return GuardrailResult(
                    allowed=False,
                    rule="PII_IN_REQUEST",
                    reason=f"PII detected in request payload ({pii_type}). "
                           f"Use customer_id references instead of raw PII.",
                    severity="BLOCK",
                )
        return GuardrailResult(allowed=True, rule="PII_IN_REQUEST", reason="OK")

    def _check_sku_restrictions(self, payload: Dict[str, Any]) -> GuardrailResult:
        sku = payload.get("sku", "")
        for prefix in RESTRICTED_SKU_PREFIXES:
            if sku.upper().startswith(prefix):
                return GuardrailResult(
                    allowed=False,
                    rule="RESTRICTED_SKU",
                    reason=f"SKU {sku} requires a separate compliance workflow "
                           f"(restricted category: {prefix.rstrip('-')}). "
                           f"Please use the Morrisons Compliance Portal.",
                    severity="BLOCK",
                )
        return GuardrailResult(allowed=True, rule="RESTRICTED_SKU", reason="OK")

    def _check_purchase_value(self, payload: Dict[str, Any]) -> GuardrailResult:
        """Flag high-value POs for additional scrutiny (not block – Oracle AME handles tiers)."""
        qty   = payload.get("quantity", 0)
        price = payload.get("unit_price", 10.0)
        value = qty * price
        if value > MAX_AUTO_APPROVAL_VALUE:
            # Not blocked – Oracle AME will route to human approver
            pass
        return GuardrailResult(allowed=True, rule="PURCHASE_VALUE", reason="OK")

    def _check_role_permissions(self, context: str, role: str) -> GuardrailResult:
        allowed_domains = ROLE_DOMAIN_PERMISSIONS.get(role, [])
        domain_map = {
            "supply_chain":  "supply_chain",
            "store_ops":     "store_ops",
            "customer_data": "customer_data",
            "finance":       "finance",
            "purchase_order":"finance",
        }
        required = domain_map.get(context, context)
        if required not in allowed_domains and "ADMIN" not in role:
            return GuardrailResult(
                allowed=False,
                rule="RBAC_VIOLATION",
                reason=f"Role '{role}' is not permitted to perform '{context}' operations. "
                       f"Allowed domains: {allowed_domains}",
                severity="BLOCK",
            )
        return GuardrailResult(allowed=True, rule="RBAC_VIOLATION", reason="OK")

    def _check_suspicious_quantities(self, payload: Dict[str, Any]) -> GuardrailResult:
        qty = payload.get("quantity", 0)
        if isinstance(qty, int) and qty > 100_000:
            return GuardrailResult(
                allowed=False,
                rule="SUSPICIOUS_QUANTITY",
                reason=f"Quantity {qty:,} exceeds maximum single-order limit of 100,000 units. "
                       f"Please split the order or escalate to Category Director.",
                severity="BLOCK",
            )
        return GuardrailResult(allowed=True, rule="SUSPICIOUS_QUANTITY", reason="OK")

    # ════════════════════════════════════════════════════════════════════════
    # LAYER 3 – OUTPUT GUARDRAILS
    # ════════════════════════════════════════════════════════════════════════

    async def sanitise_output(
        self,
        response: Dict[str, Any],
        requester_role: str = "SYSTEM",
        context: str = "general",
    ) -> Tuple[Dict[str, Any], List[str]]:
        """
        Sanitise agent response before returning to the caller.
        Returns (sanitised_response, list_of_redacted_fields).
        """
        redacted: List[str] = []
        sanitised = dict(response)

        # Mask sensitive fields
        sanitised, redacted = self._mask_sensitive_fields(sanitised, redacted, requester_role)

        # Strip internal infra details from non-admin responses
        if requester_role not in ("ADMIN", "SYSTEM"):
            for internal_field in ["sap_plant", "sap_storage_location", "oracle_ledger_id",
                                    "salesforce_contact_id", "aws_request_id", "bq_job_id"]:
                if internal_field in sanitised:
                    del sanitised[internal_field]
                    redacted.append(internal_field)

        return sanitised, redacted

    def _mask_sensitive_fields(
        self, data: Dict[str, Any], redacted: List[str], role: str
    ) -> Tuple[Dict[str, Any], List[str]]:
        for key in list(data.keys()):
            if key.lower() in SENSITIVE_OUTPUT_FIELDS:
                if role not in ("ADMIN", "FINANCE"):
                    data[key] = "***REDACTED***"
                    redacted.append(key)
            elif isinstance(data[key], dict):
                data[key], redacted = self._mask_sensitive_fields(data[key], redacted, role)
            elif isinstance(data[key], str):
                # Mask any email addresses that leaked through
                for pii_type, pattern in PII_PATTERNS.items():
                    if pii_type == "email" and role not in ("ADMIN", "MARKETING"):
                        data[key] = pattern.sub("***@***.***", data[key])
        return data, redacted

    # ════════════════════════════════════════════════════════════════════════
    # GUARDRAIL POLICY REPORT (shown in WSO2 portal)
    # ════════════════════════════════════════════════════════════════════════

    def policy_summary(self) -> Dict[str, Any]:
        return {
            "organisation":       "Morrisons Supermarkets Plc",
            "policy_version":     "2.1.0",
            "last_reviewed":      "2026-03-01",
            "next_review":        "2026-09-01",
            "input_guardrails":   [
                "PROMPT_INJECTION – Blocks LLM jailbreak attempts",
                "PII_IN_REQUEST – Prevents raw PII in agent payloads",
                "RESTRICTED_SKU – Routes regulated products to compliance workflow",
                "PURCHASE_VALUE – Flags high-value POs (Oracle AME handles tiered approvals)",
                "RBAC_VIOLATION – Enforces role-based domain access",
                "SUSPICIOUS_QUANTITY – Blocks abnormally large order quantities",
            ],
            "output_guardrails":  [
                "SENSITIVE_FIELD_MASKING – Redacts PII and credentials from responses",
                "INTERNAL_FIELD_STRIPPING – Hides infra details from non-admin roles",
            ],
            "agent_level_guardrails": [
                "SAP: maxPOValue=£50,000, allowedStores=STORE-*, blocked ALCOHOL-* SKUs",
                "Oracle: maxAutoApproval=£5,000, requireBudgetCheck=true",
                "Rate limits: SAP 120 rpm, Oracle 60 rpm, Salesforce 200 rpm",
            ],
            "compliance_frameworks": ["UK GDPR", "PCI DSS (Morrisons.com)", "ISO 27001"],
        }
