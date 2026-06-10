"""agent.py — Supplier Agent with LLM-driven ReAct loop.

LLM selection (auto-detected at startup):
  • GatewayLLM  — used when GEMINILLM_URL and GEMINILLM_API_KEY are set
  • DemoLLM     — deterministic keyword router, no API key required (local dev)
"""

from __future__ import annotations

import json
import logging
import os
import re

from tools import TOOL_REGISTRY
from traces import start_span, trace_llm_call, trace_agent_step

logger    = logging.getLogger("supplier_agent.agent")
MAX_STEPS = 6

_PROD_RE = re.compile(r"PROD-\d{3,}", re.IGNORECASE)
_QTY_RE  = re.compile(r"(\d+)\s*x?\s*(PROD-\d{3,})", re.IGNORECASE)

_DEFAULT_REORDER_QTY = 500

_TOOL_ROUTES = [
    (["supplier", "info", "lead time", "details"], "get_supplier_info", {"product_id": "PROD-001"}),
    (["order", "purchase", "restock", "reorder", "low", "below"], "raise_purchase_order",
     {"product_id": "PROD-001", "quantity": _DEFAULT_REORDER_QTY}),
]
_DEFAULT_TOOL = ("raise_purchase_order", {"product_id": "PROD-001", "quantity": _DEFAULT_REORDER_QTY})


# ---------------------------------------------------------------------------
# GatewayLLM
# ---------------------------------------------------------------------------

class GatewayLLM:
    """Gemini via WSO2 AI gateway."""

    MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")

    _SYSTEM_PROMPT = (
        "You are a supplier and procurement agent for a retail supermarket. "
        "Your job is to raise purchase orders with suppliers for low-stock products "
        "and retrieve supplier information. "
        "Always use the available tools. Be precise and concise."
    )

    _TOOL_DESCRIPTIONS = (
        "raise_purchase_order(product_id: string, quantity: int) — raise a purchase order with the supplier for restocking\n"
        "get_supplier_info(product_id: string) — get supplier details and lead time for a product"
    )

    def __init__(self):
        url    = os.environ.get("GEMINILLM_URL")
        apikey = os.environ.get("GEMINILLM_API_KEY")

        if not url or not apikey:
            raise EnvironmentError(
                "GEMINILLM_URL and GEMINILLM_API_KEY must be set to use GatewayLLM. "
                f"Got GEMINILLM_URL={'<set>' if url else '<missing>'}, "
                f"GEMINILLM_API_KEY={'<set>' if apikey else '<missing>'}."
            )

        from google import genai
        from google.genai import types as gtypes

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
            name   = parsed.get("tool", "raise_purchase_order")
            args   = parsed.get("args", {})
            self._last_tool = {"name": name, "args": args}
            return name, args
        except (json.JSONDecodeError, TypeError) as exc:
            logger.warning("Could not parse tool JSON (%s): %s", exc, raw[:200])
            return "raise_purchase_order", {}

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
        prod_m = _PROD_RE.findall(text.upper())
        qty_m  = _QTY_RE.findall(text.upper())
        if prod_m and "product_id" in args:
            args["product_id"] = prod_m[0]
        if tool_name == "raise_purchase_order" and qty_m:
            args["quantity"] = int(qty_m[0][0])
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
# ReAct loop
# ---------------------------------------------------------------------------

def run(message: str, session_id: str, context: dict | None = None) -> str:
    context = context or {}
    conversation = [
        {"role": "system", "content": f"context={json.dumps(context)}"},
        {"role": "user",   "content": message},
    ]
    llm = _get_llm()

    with start_span("supplier_agent.chat", attributes={
        "session.id":    session_id,
        "agent.type":    "supplier_agent",
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
                return reply

            conversation.append({"role": "assistant", "content": f"Tool error: {observation}"})

    return "Unable to process request."


def _safe_json(raw: str) -> dict:
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {"status": "error", "message": raw}
