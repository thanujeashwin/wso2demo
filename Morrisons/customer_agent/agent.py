"""agent.py — Custom ReAct agent loop (no LangGraph).

Implements: Observe → Think → Act → Observe → … → Respond

LLM selection (auto-detected at startup):
  • GeminiLLM  — used when PRODUCTION_GEMINI_LLM_URL and
                  PRODUCTION_GEMINI_LLM_API_KEY are set (WSO2 Agent Manager)
  • DemoLLM    — deterministic keyword router, no API key required (local dev)

OpenTelemetry spans are emitted for every LLM call, tool execution, and
ReAct step via traces.py.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from tools import TOOL_REGISTRY
from traces import start_span, trace_llm_call, trace_agent_step

logger = logging.getLogger("customer_agent.agent")

MAX_STEPS = 6  # prevent infinite loops

# ---------------------------------------------------------------------------
# Keyword → (tool_name, default_args) routing table  (DemoLLM only)
# ---------------------------------------------------------------------------

_TOOL_ROUTES: list[tuple[list[str], str, dict]] = [
    # Track / follow up an order  ← must come before place_order
    (["track", "where is", "ord-", "my order", "when will", "delivery status"],
     "track_order", {"order_id": "ORD-9002"}),

    # Customer profile / loyalty  ← before browse
    (["profile", "loyalty", "points", "tier", "my account", "my details", "who am i"],
     "get_customer_profile", {"customer_id": "CUST-5001"}),

    # Check specific product stock
    (["stock", "in stock", "how many", "quantity", "units available"],
     "check_stock", {"product_id": "PROD-001"}),

    # Place / make an order
    (["order", "buy", "purchase", "add to", "place", "get me", "i want", "i'd like",
      "can i have", "checkout"],
     "place_order", {"customer_id": "CUST-5001",
                     "items": [{"product_id": "PROD-001", "quantity": 1}]}),

    # Browse / search products  ← catch-all last
    (["browse", "show", "list", "search", "products", "available", "what do you have",
      "what do you sell", "categories", "catalogue"],
     "browse_products", {}),
]

_DEFAULT_TOOL = ("browse_products", {})
_PROD_RE  = re.compile(r"PROD-\d{3,}", re.IGNORECASE)
_ORD_RE   = re.compile(r"ORD-\d{4,}", re.IGNORECASE)
_CUST_RE  = re.compile(r"CUST-\d{4,}", re.IGNORECASE)
_QTY_RE   = re.compile(r"\b(\d+)\s*(?:x\s*)?(?:of\s+)?(PROD-\d{3,})", re.IGNORECASE)
_CATEGORIES = ["dairy", "meat", "bakery", "fruit", "vegetables", "eggs",
               "canned", "confectionery"]


# ---------------------------------------------------------------------------
# GeminiLLM — routed through WSO2 Agent Manager built-in AI gateway
# ---------------------------------------------------------------------------

# WSO2 Agent Manager internal AI gateway — handles routing to the configured
# LLM provider, applies guardrails, rate limiting, and governance centrally.
_AI_GATEWAY_URL = os.environ.get(
    "AI_GATEWAY_URL",
    "http://ai-gateway.amp.localhost:8084",
)


class GeminiLLM:
    """
    Sends requests through the WSO2 Agent Manager AI gateway.
    The gateway routes to the configured LLM provider (Gemini) and applies
    platform-level guardrails before the request reaches the model.

    Env vars:
      AI_GATEWAY_URL             — gateway base URL (default: http://ai-gateway.amp.localhost:8084)
      PRODUCTION_GEMINI_LLM_API_KEY — API key injected by WSO2 Agent Manager
      GEMINI_MODEL               — model name override (default: gemini-1.5-flash)
    """

    GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-1.5-flash")

    _SYSTEM_PROMPT = (
        "You are a helpful Morrisons supermarket shopping assistant. "
        "Help customers browse products, check stock levels, place orders, "
        "and track deliveries. Always use the available tools to get accurate "
        "information before responding. Be friendly and concise."
    )

    def __init__(self):
        from google import genai
        from google.genai import types as gtypes

        apikey = os.environ.get("PRODUCTION_GEMINI_LLM_API_KEY", "").strip()
        url    = _AI_GATEWAY_URL

        http_options = gtypes.HttpOptions(
            base_url=url,
            client_args={"headers": {"API-Key": apikey, "Authorization": ""}},
        )
        self._client  = genai.Client(api_key=apikey or "gateway", http_options=http_options)
        self._gtypes  = gtypes
        self._tools   = self._build_tools()
        self._last_fc = None   # last FunctionCall — shared between select_tool/synthesise
        self.model_name = f"GeminiLLM ({self.GEMINI_MODEL})"
        logger.info("GeminiLLM initialised — model=%s  gateway=%s", self.GEMINI_MODEL, url)

    # ── public API (same interface as DemoLLM) ───────────────────────────────

    def select_tool(self, conversation: list[dict]) -> tuple[str, dict]:
        """Send message to Gemini; return (tool_name, args) from function call."""
        user_msg = self._last_user(conversation)
        customer_id = self._extract_customer(conversation)

        system_ctx = (
            f"{self._SYSTEM_PROMPT}\n"
            f"Current customer ID: {customer_id}. "
            "Use this customer_id when calling place_order or get_customer_profile."
        )

        contents = [
            self._gtypes.Content(
                role="user",
                parts=[self._gtypes.Part(text=f"{system_ctx}\n\nCustomer: {user_msg}")],
            )
        ]

        response = self._client.models.generate_content(
            model=self.GEMINI_MODEL,
            contents=contents,
            config=self._gtypes.GenerateContentConfig(tools=self._tools),
        )

        for part in response.candidates[0].content.parts:
            if part.function_call:
                fc = part.function_call
                self._last_fc = fc
                args = dict(fc.args) if fc.args else {}
                # items comes back as a proto ListValue — normalise to plain list
                if "items" in args:
                    args["items"] = _normalise_items(args["items"])
                logger.info("Gemini selected tool: %s  args=%s", fc.name, args)
                return fc.name, args

        # Gemini returned text without a function call — fall back to browse
        logger.warning("Gemini returned no function call; falling back to browse_products")
        self._last_fc = None
        return "browse_products", {}

    def synthesise(self, conversation: list[dict], tool_result: dict) -> str:
        """Send tool result back to Gemini; return natural-language reply."""
        user_msg = self._last_user(conversation)

        if self._last_fc is None:
            # No function call was recorded — just serialise the result
            return json.dumps(tool_result, indent=2)

        fc = self._last_fc
        contents = [
            self._gtypes.Content(
                role="user",
                parts=[self._gtypes.Part(
                    text=f"{self._SYSTEM_PROMPT}\n\nCustomer: {user_msg}"
                )],
            ),
            self._gtypes.Content(
                role="model",
                parts=[self._gtypes.Part(
                    function_call=self._gtypes.FunctionCall(
                        name=fc.name, args=fc.args
                    )
                )],
            ),
            self._gtypes.Content(
                role="user",
                parts=[self._gtypes.Part(
                    function_response=self._gtypes.FunctionResponse(
                        name=fc.name,
                        response={"result": tool_result},
                    )
                )],
            ),
        ]

        response = self._client.models.generate_content(
            model=self.GEMINI_MODEL,
            contents=contents,
            config=self._gtypes.GenerateContentConfig(tools=self._tools),
        )

        return response.text or json.dumps(tool_result, indent=2)

    # ── private ──────────────────────────────────────────────────────────────

    def _last_user(self, conversation: list[dict]) -> str:
        return next(
            (m["content"] for m in reversed(conversation) if m["role"] == "user"), ""
        )

    def _extract_customer(self, conversation: list[dict]) -> str:
        """Pull customer_id from conversation context if present."""
        for m in conversation:
            if m.get("role") == "system":
                match = _CUST_RE.search(m.get("content", ""))
                if match:
                    return match.group(0)
        return "CUST-5001"

    def _build_tools(self):
        """Convert TOOL_REGISTRY into Gemini FunctionDeclarations."""
        T = self._gtypes
        declarations = []

        for tool in TOOL_REGISTRY.values():
            props  = {}
            required = []

            for pname, pinfo in tool["parameters"].items():
                raw_type = pinfo.get("type", "string").upper()

                if raw_type == "ARRAY":
                    # items array: [{product_id, quantity}]
                    schema = T.Schema(
                        type=T.Type.ARRAY,
                        description=pinfo.get("description", ""),
                        items=T.Schema(
                            type=T.Type.OBJECT,
                            properties={
                                "product_id": T.Schema(
                                    type=T.Type.STRING,
                                    description="Product ID e.g. PROD-001",
                                ),
                                "quantity": T.Schema(
                                    type=T.Type.INTEGER,
                                    description="Number of units",
                                ),
                            },
                            required=["product_id", "quantity"],
                        ),
                    )
                elif raw_type == "INTEGER":
                    schema = T.Schema(
                        type=T.Type.INTEGER,
                        description=pinfo.get("description", ""),
                    )
                else:
                    schema = T.Schema(
                        type=T.Type.STRING,
                        description=pinfo.get("description", ""),
                    )

                props[pname] = schema
                if pinfo.get("required", False):
                    required.append(pname)

            declarations.append(
                T.FunctionDeclaration(
                    name=tool["name"],
                    description=tool["description"],
                    parameters=T.Schema(
                        type=T.Type.OBJECT,
                        properties=props,
                        required=required or None,
                    ),
                )
            )

        return [T.Tool(function_declarations=declarations)]


# ---------------------------------------------------------------------------
# DemoLLM — deterministic keyword router (fallback / local dev)
# ---------------------------------------------------------------------------

class DemoLLM:
    """
    No API key required.  Uses keyword matching to select tools and
    hand-crafted templates to format responses.
    """

    model_name = "DemoLLM-v1 (keyword-router)"

    def select_tool(self, conversation: list[dict]) -> tuple[str, dict]:
        text = " ".join(
            m["content"].lower()
            for m in conversation
            if m.get("role") in ("user", "assistant")
        )
        tool_name, args = self._route(text)
        return tool_name, self._extract_entities(text, tool_name, dict(args))

    def synthesise(self, conversation: list[dict], tool_result: dict) -> str:
        last_user = next(
            (m["content"] for m in reversed(conversation) if m["role"] == "user"), ""
        )
        return self._format_response(last_user.lower(), tool_result)

    def _route(self, text: str) -> tuple[str, dict]:
        for keywords, name, default_args in _TOOL_ROUTES:
            if any(k in text for k in keywords):
                return name, default_args
        return _DEFAULT_TOOL

    def _extract_entities(self, text: str, tool_name: str, args: dict) -> dict:
        prod_matches = _PROD_RE.findall(text.upper())
        if prod_matches:
            pid = prod_matches[0]
            if tool_name == "check_stock":
                args["product_id"] = pid
            elif tool_name == "place_order":
                qty_matches = _QTY_RE.findall(text.upper())
                args["items"] = (
                    [{"product_id": p, "quantity": int(q)} for q, p in qty_matches]
                    if qty_matches else [{"product_id": pid, "quantity": 1}]
                )
        ord_matches = _ORD_RE.findall(text.upper())
        if ord_matches and tool_name == "track_order":
            args["order_id"] = ord_matches[0]
        cust_matches = _CUST_RE.findall(text.upper())
        if cust_matches and tool_name in ("place_order", "get_customer_profile"):
            args["customer_id"] = cust_matches[0]
        for cat in _CATEGORIES:
            if cat in text and tool_name == "browse_products":
                args["category"] = cat
                break
        return args

    def _format_response(self, query: str, result: dict) -> str:
        status = result.get("status", "error")
        if status == "error":
            return (
                f"I'm sorry, I wasn't able to complete that request. "
                f"{result.get('message', 'Please try again.')}"
            )
        if "products" in result:
            prods = result["products"]
            cats  = result.get("categories", [])
            lines = [
                f"Here are {result['count']} products"
                + (f" in the *{result.get('category', '')}* category"
                   if "category" in result else "") + ":"
            ]
            for p in prods[:8]:
                lines.append(
                    f"  • {p['name']} — £{p['price']:.2f} per {p['unit']}  [{p['id']}]"
                )
            if len(prods) > 8:
                lines.append(f"  … and {len(prods) - 8} more.")
            if cats:
                lines.append(f"\nAvailable categories: {', '.join(cats)}")
            lines.append("\nTo check stock: ask \"how many PROD-XXX are available?\"")
            return "\n".join(lines)
        if "units_available" in result:
            avail_map = {
                "in_stock":     "✅ In Stock",
                "low_stock":    "⚠️ Low Stock",
                "out_of_stock": "❌ Out of Stock",
            }
            avail = avail_map.get(result["availability"], result["availability"])
            return (
                f"{avail} — **{result['name']}** [{result['product_id']}]\n"
                f"  Units available: {result['units_available']}\n"
                f"  Price: £{result['price']:.2f} per {result['unit']}\n\n"
                f"Ready to order? Just say \"order 2 {result['product_id']}\"."
            )
        if "customer_name" in result:
            items_txt = "\n".join(
                f"  • {it.get('name', it.get('product_id'))} × {it['quantity']}"
                f"  =  £{it.get('line_total', 0):.2f}"
                for it in result.get("items", [])
            )
            errors_txt = (
                "\n⚠️ Note: " + "; ".join(result["errors"])
                if result.get("errors") else ""
            )
            return (
                f"🛒 Order placed successfully!\n\n"
                f"**Order ID:** {result['order_id']}\n"
                f"**Customer:** {result['customer_name']}\n\n"
                f"**Items:**\n{items_txt}\n\n"
                f"**Total: £{result['total']:.2f}**\n"
                f"**Estimated delivery:** {result['estimated_delivery']}"
                f"{errors_txt}\n\n"
                f"Track your order: ask \"track {result['order_id']}\""
            )
        if "status_label" in result:
            from demo_data import PRODUCTS as _P
            def _item_label(it):
                pid  = it.get("product_id", "")
                name = it.get("name") or _P.get(pid, {}).get("name") or pid
                return f"  • {name} × {it.get('quantity', 1)}"
            items_txt = "\n".join(_item_label(it) for it in result.get("items", []))
            eta = result.get("estimated_delivery") or result.get("delivered_at", "—")
            return (
                f"📦 Order **{result['order_id']}** — {result['status_label']}\n\n"
                f"**Customer:** {result['customer']}\n"
                f"**Items:**\n{items_txt}\n\n"
                f"**Total:** £{result['total']:.2f}\n"
                f"**Delivery:** {eta}"
            )
        if "loyalty_tier" in result:
            orders_txt = "\n".join(
                f"  • {o['id']}  £{o['total']:.2f}  [{o['status']}]"
                for o in result.get("recent_orders", [])
            )
            return (
                f"👤 **{result['name']}** ({result['customer_id']})\n"
                f"  Email: {result['email']}\n"
                f"  Loyalty tier: **{result['loyalty_tier']}**\n"
                f"  Points: **{result['loyalty_points']}**\n\n"
                f"Recent orders:\n{orders_txt or '  No orders yet.'}"
            )
        return json.dumps(result, indent=2)


# ---------------------------------------------------------------------------
# LLM selection — lazy, resolved on first request
# ---------------------------------------------------------------------------

_llm_instance: GeminiLLM | DemoLLM | None = None


def _get_llm() -> GeminiLLM | DemoLLM:
    """
    Return the active LLM, initialising it on first call (lazy).

    Priority:
      1. GeminiLLM via WSO2 AI gateway (AI_GATEWAY_URL, default localhost:8084)
      2. DemoLLM fallback if GeminiLLM init fails (e.g. local dev without gateway)
    """
    global _llm_instance
    if _llm_instance is not None:
        return _llm_instance

    try:
        _llm_instance = GeminiLLM()
        logger.info(
            "LLM: GeminiLLM via gateway=%s  model=%s",
            _AI_GATEWAY_URL,
            _llm_instance.GEMINI_MODEL,
        )
        return _llm_instance
    except Exception as exc:
        logger.error(
            "GeminiLLM init FAILED — falling back to DemoLLM.\n"
            "  AI_GATEWAY_URL = %s\n"
            "  Exception: %s: %s",
            _AI_GATEWAY_URL,
            type(exc).__name__,
            exc,
        )

    _llm_instance = DemoLLM()
    return _llm_instance


# ---------------------------------------------------------------------------
# ReAct loop
# ---------------------------------------------------------------------------

def run(message: str, session_id: str, context: dict | None = None) -> str:
    """
    Main entry-point. Runs Observe → Think → Act → Respond and returns a
    natural-language reply. Emits OTLP-style spans via traces.py.
    """
    context = context or {}
    customer_id = context.get("customer_id", "CUST-5001")

    # Inject customer context so GeminiLLM can read it
    conversation: list[dict] = [
        {"role": "system", "content": f"customer_id={customer_id}"},
        {"role": "user",   "content": message},
    ]

    root_attrs = {
        "session.id":      session_id,
        "user.id":         context.get("user_id", "anonymous"),
        "customer.id":     customer_id,
        "input.message":   message[:256],
        "agent.type":      "customer_agent",
        "react.max_steps": MAX_STEPS,
    }

    llm = _get_llm()

    with start_span("agent.chat", attributes={**root_attrs, "llm.backend": llm.model_name}) as root_span:

        for step in range(1, MAX_STEPS + 1):

            # ── THINK ─────────────────────────────────────────────────────
            tool_name, tool_args = llm.select_tool(conversation)

            trace_llm_call(
                llm.model_name,
                prompt=f"User: {message}",
                response=f"Action: {tool_name}({json.dumps(tool_args, default=str)})",
            )
            logger.info("[step %d] Think → %s(%s)", step, tool_name, tool_args)

            # ── ACT ───────────────────────────────────────────────────────
            tool_entry = TOOL_REGISTRY.get(tool_name)
            if not tool_entry:
                observation = json.dumps(
                    {"status": "error", "message": f"Unknown tool: {tool_name}"}
                )
            else:
                try:
                    observation = tool_entry["fn"](**tool_args)
                except TypeError as exc:
                    logger.warning("Tool %s arg error: %s", tool_name, exc)
                    observation = json.dumps({"status": "error", "message": str(exc)})

            obs_dict = _safe_json(observation)
            trace_agent_step(step, tool_name, observation)
            logger.info("[step %d] Observe → %s", step, observation[:120])

            # ── RESPOND ───────────────────────────────────────────────────
            if obs_dict.get("status") in ("ok", "no_results") or step == MAX_STEPS:
                reply = llm.synthesise(conversation, obs_dict)
                root_span.set_attribute("output.chars",      len(reply))
                root_span.set_attribute("react.steps_taken", step)
                return reply

            # Error on this step — append and retry
            conversation.append(
                {"role": "assistant", "content": f"Tool error: {observation}"}
            )

    return "I'm sorry, I was unable to process your request. Please try again."


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_json(raw: str) -> dict:
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {"status": "error", "message": raw}


def _normalise_items(raw: Any) -> list[dict]:
    """Convert proto ListValue / MapValue from Gemini args to plain Python list."""
    if isinstance(raw, list):
        return [
            {k: v for k, v in (item.items() if hasattr(item, "items") else item)}
            for item in raw
        ]
    # proto MapComposite or similar
    try:
        return list(raw)
    except Exception:
        return []
