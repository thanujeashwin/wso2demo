"""agent.py — Custom ReAct agent loop (no LangGraph).

Implements: Observe → Think → Act → Observe → … → Respond

The DemoLLM uses deterministic keyword routing (same pattern as salesforce_agent/graph.py)
so the demo works without any external LLM API keys.

Mock OpenTelemetry spans are emitted for every:
  - Chat request (root span)
  - LLM "think" step
  - Tool call
  - ReAct step transition
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from tools import TOOL_REGISTRY
from traces import tracer, trace_llm_call, trace_agent_step

logger = logging.getLogger("customer_agent.agent")

MAX_STEPS = 6   # prevent infinite loops

# ---------------------------------------------------------------------------
# Keyword → (tool_name, default_args) routing table
# ---------------------------------------------------------------------------

_TOOL_ROUTES: list[tuple[list[str], str, dict]] = [
    # Track / follow up an order  ← must come before place_order ("order" keyword conflict)
    (["track", "where is", "ord-", "my order", "when will", "delivery status"],
     "track_order", {"order_id": "ORD-9002"}),

    # Customer profile / loyalty  ← before browse (avoids "show" + "loyalty" ambiguity)
    (["profile", "loyalty", "points", "tier", "my account", "my details", "who am i"],
     "get_customer_profile", {"customer_id": "CUST-5001"}),

    # Check specific product stock
    (["stock", "in stock", "how many", "quantity", "units available"],
     "check_stock", {"product_id": "PROD-001"}),

    # Place / make an order
    (["order", "buy", "purchase", "add to", "place", "get me", "i want", "i'd like",
      "can i have", "checkout"],
     "place_order", {"customer_id": "CUST-5001", "items": [{"product_id": "PROD-001", "quantity": 1}]}),

    # Browse / search products  ← catch-all last
    (["browse", "show", "list", "search", "products", "available", "what do you have",
      "what do you sell", "categories", "catalogue"],
     "browse_products", {}),
]

_DEFAULT_TOOL = ("browse_products", {})

# Product ID extraction pattern
_PROD_RE  = re.compile(r"PROD-\d{3,}", re.IGNORECASE)
_ORD_RE   = re.compile(r"ORD-\d{4,}", re.IGNORECASE)
_CUST_RE  = re.compile(r"CUST-\d{4,}", re.IGNORECASE)
_QTY_RE   = re.compile(r"\b(\d+)\s*(?:x\s*)?(?:of\s+)?(PROD-\d{3,})", re.IGNORECASE)

# Category keywords
_CATEGORIES = ["dairy", "meat", "bakery", "fruit", "vegetables", "eggs", "canned", "confectionery"]


# ---------------------------------------------------------------------------
# DemoLLM: keyword-based tool selector
# ---------------------------------------------------------------------------

class DemoLLM:
    """
    Deterministic mock LLM.  Mimics the DemoLLM class in salesforce_agent/graph.py
    but operates as a plain Python class (no LangChain BaseChatModel).
    """

    model_name = "DemoLLM-v1 (keyword-router)"

    def select_tool(self, conversation: list[dict]) -> tuple[str, dict]:
        """Return (tool_name, args) based on keyword matching."""
        text = " ".join(
            m["content"].lower()
            for m in conversation
            if m.get("role") in ("user", "assistant")
        )

        tool_name, args = self._route(text)
        args = self._extract_entities(text, tool_name, dict(args))
        return tool_name, args

    def synthesise(self, conversation: list[dict], tool_result: dict) -> str:
        """Turn raw tool JSON into a friendly natural-language reply."""
        last_user = next(
            (m["content"] for m in reversed(conversation) if m["role"] == "user"), ""
        )
        return self._format_response(last_user.lower(), tool_result)

    # ── private ─────────────────────────────────────────────────────────────

    def _route(self, text: str) -> tuple[str, dict]:
        for keywords, name, default_args in _TOOL_ROUTES:
            if any(k in text for k in keywords):
                return name, default_args
        return _DEFAULT_TOOL

    def _extract_entities(self, text: str, tool_name: str, args: dict) -> dict:
        """Overwrite default args with entities extracted from the user message."""
        # Product IDs
        prod_matches = _PROD_RE.findall(text.upper())
        if prod_matches:
            pid = prod_matches[0]
            if tool_name == "check_stock":
                args["product_id"] = pid
            elif tool_name == "place_order":
                # Try to extract quantities
                qty_matches = _QTY_RE.findall(text.upper())
                if qty_matches:
                    items = [{"product_id": p, "quantity": int(q)} for q, p in qty_matches]
                else:
                    items = [{"product_id": pid, "quantity": 1}]
                args["items"] = items

        # Order IDs
        ord_matches = _ORD_RE.findall(text.upper())
        if ord_matches and tool_name == "track_order":
            args["order_id"] = ord_matches[0]

        # Customer IDs
        cust_matches = _CUST_RE.findall(text.upper())
        if cust_matches:
            if tool_name in ("place_order", "get_customer_profile"):
                args["customer_id"] = cust_matches[0]

        # Category
        for cat in _CATEGORIES:
            if cat in text:
                if tool_name == "browse_products":
                    args["category"] = cat
                break

        return args

    def _format_response(self, query: str, result: dict) -> str:
        """Generate a friendly response string from a tool result dict."""
        status = result.get("status", "error")

        if status == "error":
            return (
                f"I'm sorry, I wasn't able to complete that request. "
                f"{result.get('message', 'Please try again.')}"
            )

        # browse_products
        if "products" in result:
            prods = result["products"]
            cats  = result.get("categories", [])
            lines = [f"Here are {result['count']} products" +
                     (f" in the *{result.get('category', '')}* category" if "category" in result else "") + ":"]
            for p in prods[:8]:
                lines.append(f"  • {p['name']} — £{p['price']:.2f} per {p['unit']}  [{p['id']}]")
            if len(prods) > 8:
                lines.append(f"  … and {len(prods) - 8} more.")
            if cats:
                lines.append(f"\nAvailable categories: {', '.join(cats)}")
            lines.append("\nTo check stock: ask \"how many PROD-XXX are available?\"")
            return "\n".join(lines)

        # check_stock
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

        # place_order  ← "customer_name" only present in place_order results; check first
        if "customer_name" in result:
            items_txt = "\n".join(
                f"  • {it.get('name', it.get('product_id'))} × {it['quantity']}  =  £{it.get('line_total', 0):.2f}"
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

        # track_order  ← "status_label" only present in track_order results
        if "status_label" in result:
            from demo_data import PRODUCTS as _P
            def _item_label(it):
                pid = it.get("product_id", "")
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

        # get_customer_profile
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
# ReAct loop
# ---------------------------------------------------------------------------

llm = DemoLLM()


def run(message: str, session_id: str, context: dict | None = None) -> str:
    """
    Main entry-point.  Runs the Observe → Think → Act → Respond loop and
    returns a natural-language reply string.

    Emits mock OTLP spans via traces.py.
    """
    context = context or {}
    conversation: list[dict] = [{"role": "user", "content": message}]

    root_attrs = {
        "session.id":    session_id,
        "user.id":       context.get("user_id", "anonymous"),
        "customer.id":   context.get("customer_id", "CUST-5001"),
        "input.message": message[:256],
        "agent.type":    "customer_agent",
        "react.max_steps": MAX_STEPS,
    }

    with tracer.start_span("agent:chat", attributes=root_attrs) as root_span:

        for step in range(1, MAX_STEPS + 1):
            # ── THINK ─────────────────────────────────────────────────────
            tool_name, tool_args = llm.select_tool(conversation)

            think_prompt = f"User: {message}\nSelect tool: {tool_name}, args: {json.dumps(tool_args)}"
            think_response = f"Action: {tool_name}({json.dumps(tool_args)})"
            trace_llm_call(llm.model_name, think_prompt, think_response, span=root_span)

            logger.info("[step %d] Think → %s(%s)", step, tool_name, tool_args)

            # ── ACT ───────────────────────────────────────────────────────
            tool_entry = TOOL_REGISTRY.get(tool_name)
            if not tool_entry:
                observation = json.dumps({"status": "error", "message": f"Unknown tool: {tool_name}"})
            else:
                try:
                    observation = tool_entry["fn"](**tool_args)
                except TypeError as exc:
                    # arg mismatch — fall back gracefully
                    logger.warning("Tool %s arg error: %s", tool_name, exc)
                    observation = json.dumps({"status": "error", "message": str(exc)})

            obs_dict = _safe_json(observation)
            trace_agent_step(step, tool_name, observation, span=root_span)

            logger.info("[step %d] Observe → %s", step, observation[:120])

            # ── CHECK ─────────────────────────────────────────────────────
            # Single-step: one tool call is always enough for this demo
            if obs_dict.get("status") in ("ok", "no_results") or step == MAX_STEPS:
                # ── RESPOND ───────────────────────────────────────────────
                reply = llm.synthesise(conversation, obs_dict)
                root_span.attributes["output.chars"] = len(reply)
                root_span.attributes["react.steps_taken"] = step
                return reply

            # If error, try once more with default tool
            conversation.append({"role": "assistant", "content": f"Tool error: {observation}"})

    # Fallback (should never reach here)
    return "I'm sorry, I was unable to process your request at this time. Please try again."


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_json(raw: str) -> dict:
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {"status": "error", "message": raw}
