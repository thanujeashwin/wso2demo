"""agent.py — Inventory Agent with LLM-driven ReAct loop.

LLM selection (auto-detected at startup):
  • GatewayLLM  — used when GEMINILLM_URL and GEMINILLM_API_KEY are set
  • DemoLLM     — deterministic keyword router, no API key required (local dev)
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading

import httpx

from tools import TOOL_REGISTRY
from traces import start_span, trace_llm_call, trace_agent_step

logger   = logging.getLogger("inventory_agent.agent")
MAX_STEPS = 6

_SUPPLIER_AGENT_URL = os.environ.get("SUPPLIER_AGENT_URL", "")

_PROD_RE = re.compile(r"PROD-\d{3,}", re.IGNORECASE)
_ORD_RE  = re.compile(r"ORD-\d{4,}", re.IGNORECASE)
_QTY_RE  = re.compile(r"(\d+)\s*x?\s*(PROD-\d{3,})", re.IGNORECASE)

_TOOL_ROUTES = [
    (["release", "cancel"],                        "release_reservation", {"order_id": "ORD-UNKNOWN"}),
    (["check", "level", "stock", "inventory"],     "check_inventory_levels", {"product_id": "PROD-001"}),
    (["reserve", "order", "confirm", "placed"],    "reserve_stock",
     {"order_id": "ORD-UNKNOWN", "items": [{"product_id": "PROD-001", "quantity": 1}]}),
]
_DEFAULT_TOOL = ("reserve_stock", {"order_id": "ORD-UNKNOWN", "items": []})


# ---------------------------------------------------------------------------
# GatewayLLM
# ---------------------------------------------------------------------------

class GatewayLLM:
    """Gemini via WSO2 AI gateway."""

    MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")

    _SYSTEM_PROMPT = (
        "You are an inventory management agent for a retail supermarket. "
        "Your job is to reserve stock for confirmed orders, check inventory levels, "
        "and release reservations for cancelled orders. "
        "Always use the available tools. Be precise and concise."
    )

    _TOOL_DESCRIPTIONS = (
        "reserve_stock(order_id: string, items: [{product_id, quantity}]) — reserve warehouse stock for a confirmed order\n"
        "check_inventory_levels(product_id: string) — check current stock level for a product\n"
        "release_reservation(order_id: string) — release stock reservation for a cancelled order"
    )

    def __init__(self):
        from google import genai
        from google.genai import types as gtypes

        url    = os.environ.get("GEMINILLM_URL")
        apikey = os.environ.get("GEMINILLM_API_KEY")

        _http_options = gtypes.HttpOptions(
            base_url=url,
            client_args={"headers": {"API-Key": apikey, "Authorization": ""}},
        )
        self._client    = genai.Client(api_key=apikey, http_options=_http_options)
        self._gtypes    = gtypes
        self._last_tool = None
        self.model_name = f"GatewayLLM ({self.MODEL})"
        logger.info("GatewayLLM initialised — model=%s url=%s", self.MODEL, url)

    def select_tool(self, conversation: list[dict]) -> tuple[str, dict]:
        user_msg = next((m["content"] for m in reversed(conversation) if m["role"] == "user"), "")
        prompt = (
            f"{self._SYSTEM_PROMPT}\n\n"
            f"Available tools:\n{self._TOOL_DESCRIPTIONS}\n\n"
            "Respond with ONLY a JSON object (no markdown):\n"
            '{"tool": "<tool_name>", "args": {<arguments>}}\n\n'
            f"Message: {user_msg}"
        )
        response = self._client.models.generate_content(
            model=self.MODEL,
            contents=[self._gtypes.Content(role="user", parts=[self._gtypes.Part(text=prompt)])],
        )
        raw = response.text or ""
        try:
            clean  = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.DOTALL).strip()
            parsed = json.loads(clean)
            name   = parsed.get("tool", "reserve_stock")
            args   = parsed.get("args", {})
            self._last_tool = {"name": name, "args": args}
            return name, args
        except (json.JSONDecodeError, TypeError) as exc:
            logger.warning("Could not parse tool JSON (%s): %s", exc, raw[:200])
            return "reserve_stock", {}

    def synthesise(self, conversation: list[dict], tool_result: dict) -> str:
        user_msg  = next((m["content"] for m in reversed(conversation) if m["role"] == "user"), "")
        tool_name = (self._last_tool or {}).get("name", "tool")
        prompt = (
            f"{self._SYSTEM_PROMPT}\n\n"
            f"The request was: {user_msg}\n\n"
            f"You called '{tool_name}' and got:\n{json.dumps(tool_result, indent=2)}\n\n"
            "Write a concise operational summary of what was done."
        )
        response = self._client.models.generate_content(
            model=self.MODEL,
            contents=[self._gtypes.Content(role="user", parts=[self._gtypes.Part(text=prompt)])],
        )
        return response.text or json.dumps(tool_result, indent=2)


# ---------------------------------------------------------------------------
# DemoLLM (local dev fallback)
# ---------------------------------------------------------------------------

class DemoLLM:
    model_name = "DemoLLM (keyword-router)"

    def select_tool(self, conversation: list[dict]) -> tuple[str, dict]:
        text = " ".join(m["content"].lower() for m in conversation if m.get("role") in ("user", "system"))
        name, args = self._route(text)
        return name, self._extract_entities(text, name, dict(args))

    def synthesise(self, conversation: list[dict], tool_result: dict) -> str:
        return json.dumps(tool_result, indent=2)

    def _route(self, text: str) -> tuple[str, dict]:
        for keywords, name, args in _TOOL_ROUTES:
            if any(k in text for k in keywords):
                return name, args
        return _DEFAULT_TOOL

    def _extract_entities(self, text: str, tool_name: str, args: dict) -> dict:
        ord_m  = _ORD_RE.search(text.upper())
        prod_m = _PROD_RE.findall(text.upper())
        qty_m  = _QTY_RE.findall(text.upper())
        if ord_m and "order_id" in args:
            args["order_id"] = ord_m.group(0)
        if tool_name == "reserve_stock":
            args["items"] = ([{"product_id": p, "quantity": int(q)} for q, p in qty_m]
                             if qty_m else [{"product_id": p, "quantity": 1} for p in prod_m])
        if tool_name == "check_inventory_levels" and prod_m:
            args["product_id"] = prod_m[0]
        return args


# ---------------------------------------------------------------------------
# LLM selection
# ---------------------------------------------------------------------------

_llm_instance = None

def _get_llm():
    global _llm_instance
    if _llm_instance is not None:
        return _llm_instance
    try:
        _llm_instance = GatewayLLM()
        return _llm_instance
    except Exception as exc:
        logger.error("GatewayLLM init FAILED — falling back to DemoLLM. %s: %s", type(exc).__name__, exc)
    _llm_instance = DemoLLM()
    return _llm_instance


# ---------------------------------------------------------------------------
# Supplier notification helpers
# ---------------------------------------------------------------------------

def _post_to_supplier(payload: dict) -> None:
    """Background thread: POST notification to supplier_agent."""
    if not _SUPPLIER_AGENT_URL:
        return
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(f"{_SUPPLIER_AGENT_URL}/chat", json=payload)
            logger.info("Supplier notified — status=%s", resp.status_code)
    except Exception as exc:
        logger.warning("Supplier notification failed: %s", exc)


def _check_and_notify_supplier(items: list[dict], session_id: str) -> None:
    """Check inventory for each item; fire a supplier notification for any below reorder point."""
    check_fn = (TOOL_REGISTRY.get("check_inventory_levels") or {}).get("fn")
    if not check_fn:
        return

    to_reorder = []
    for item in items:
        pid = item.get("product_id", "")
        if not pid:
            continue
        try:
            result = _safe_json(check_fn(product_id=pid))
            if result.get("needs_reorder"):
                to_reorder.append({
                    "product_id":   pid,
                    "name":         result.get("name", pid),
                    "available":    result.get("available"),
                    "reorder_point": result.get("reorder_point"),
                })
                logger.info("Low stock detected for %s — will notify supplier", pid)
        except Exception as exc:
            logger.warning("Inventory check failed for %s: %s", pid, exc)

    if to_reorder and _SUPPLIER_AGENT_URL:
        msg = (
            f"Low stock alert. The following products need immediate restocking: "
            f"{json.dumps(to_reorder)}. Please raise purchase orders."
        )
        payload = {
            "message":    msg,
            "session_id": session_id,
            "context":    {"reorder_items": to_reorder},
        }
        threading.Thread(target=_post_to_supplier, args=(payload,), daemon=True).start()


# ---------------------------------------------------------------------------
# ReAct loop
# ---------------------------------------------------------------------------

def run(message: str, session_id: str, context: dict | None = None) -> str:
    context = context or {}
    conversation = [
        {"role": "system", "content": f"context={json.dumps(context)}"},
        {"role": "user",   "content": message},
    ]
    llm = _get_llm()
    reply = "Unable to process request."

    with start_span("inventory_agent.chat", attributes={
        "session.id":    session_id,
        "agent.type":    "inventory_agent",
        "input.message": message[:2000],
        "llm.backend":   llm.model_name,
    }) as root_span:

        for step in range(1, MAX_STEPS + 1):
            tool_name, tool_args = llm.select_tool(conversation)
            trace_llm_call(llm.model_name, f"User: {message}", f"Action: {tool_name}({tool_args})")

            tool_entry = TOOL_REGISTRY.get(tool_name)
            if not tool_entry:
                observation = json.dumps({"status": "error", "message": f"Unknown tool: {tool_name}"})
            else:
                try:
                    observation = tool_entry["fn"](**tool_args)
                except TypeError as exc:
                    observation = json.dumps({"status": "error", "message": str(exc)})

            obs_dict = _safe_json(observation)
            trace_agent_step(step, tool_name, observation)

            if obs_dict.get("status") in ("ok", "error") or step == MAX_STEPS:
                reply = llm.synthesise(conversation, obs_dict)
                root_span.set_attribute("react.steps_taken", step)
                break

            conversation.append({"role": "assistant", "content": f"Tool error: {observation}"})

    # Post-reservation: check inventory levels and notify supplier if any product is below reorder point
    items = context.get("items", [])
    if items:
        _check_and_notify_supplier(items, session_id)

    return reply


def _safe_json(raw: str) -> dict:
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {"status": "error", "message": raw}
