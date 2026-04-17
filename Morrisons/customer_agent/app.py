"""app.py — FastAPI service for the Customer Agent.

Exposes the same /chat interface as all other Morrisons agents
(salesforce_agent, sap_agent, oracle_agent, etc.) so it can be called
from the Orchestrator Agent without any code changes.

POST /chat
  Body:  { "message": "...", "session_id": "...", "context": {...} }
  Reply: { "reply": "...", "session_id": "...", "agent": "customer_agent" }

GET  /health   — liveness probe
GET  /tools    — lists available tools (OpenAPI-style schema)
GET  /         — serves the WSO2-themed chat UI (static/index.html)
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import agent
from tools import TOOL_REGISTRY

# ---------------------------------------------------------------------------
# PII masking
# ---------------------------------------------------------------------------

# Matches 13–19 digit sequences with optional spaces or hyphens between digits
# (covers Visa, Mastercard, Amex, Discover, etc.)
_CC_RE    = re.compile(r"\b(?:\d[ -]*){13,19}\d\b")
_CC_MASK  = "[CARD-MASKED]"

# UK mobile numbers:  07xxx xxxxxx  or  +447xxx xxxxxx
_MOB_RE   = re.compile(r"(?:\+44\s?7|\b07)\d{3}[\s-]?\d{6}\b")
_MOB_MASK = "[MOBILE-MASKED]"

# Basic email addresses
_EMAIL_RE   = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
_EMAIL_MASK = "[EMAIL-MASKED]"


def mask_pii(text: str) -> tuple[str, list[str]]:
    """
    Remove PII from a user message before it is sent to the LLM.
    Returns (masked_text, list_of_what_was_masked).
    """
    masked = []
    result = text

    if _CC_RE.search(result):
        result = _CC_RE.sub(_CC_MASK, result)
        masked.append("credit card number")

    if _MOB_RE.search(result):
        result = _MOB_RE.sub(_MOB_MASK, result)
        masked.append("mobile number")

    if _EMAIL_RE.search(result):
        result = _EMAIL_RE.sub(_EMAIL_MASK, result)
        masked.append("email address")

    return result, masked

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger("customer_agent.app")

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Morrisons Customer Agent",
    description=(
        "Customer-facing agent for browsing products, checking stock, "
        "placing orders and tracking deliveries. "
        "Uses a custom ReAct loop (no LangGraph) with mock OpenTelemetry tracing."
    ),
    version="1.0.0",
)

# Serve static files (chat UI)
_static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(_static_dir):
    app.mount("/static", StaticFiles(directory=_static_dir), name="static")


# ---------------------------------------------------------------------------
# Request / Response models  (identical to salesforce_agent pattern)
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="User message")
    session_id: str = Field(..., description="Unique session identifier")
    context: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional context: customer_id, user_id, store_id, etc.",
    )


class ChatResponse(BaseModel):
    response: str
    session_id: str
    agent: str = "customer_agent"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", include_in_schema=False)
def root():
    index_path = os.path.join(_static_dir, "index.html")
    if os.path.isfile(index_path):
        return FileResponse(index_path)
    return JSONResponse({"service": "customer_agent", "status": "running", "ui": "not found"})


@app.get("/health")
def health():
    return {"status": "ok", "agent": "customer_agent", "version": "1.0.0"}


@app.get("/tools")
def list_tools():
    """Return the OpenAPI-style tool schema for all registered tools."""
    return {
        "agent":  "customer_agent",
        "tools": [
            {
                "name":        t["name"],
                "description": t["description"],
                "parameters":  t["parameters"],
            }
            for t in TOOL_REGISTRY.values()
        ],
    }


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    """
    Main chat endpoint.  Delegates to the ReAct agent loop in agent.py.
    Context may include customer_id to personalise tool calls.
    """
    # Mask PII before the message reaches the LLM
    clean_message, masked_fields = mask_pii(request.message)
    if masked_fields:
        logger.info(
            "chat  session=%s  PII masked: %s",
            request.session_id,
            ", ".join(masked_fields),
        )

    logger.info(
        "chat  session=%s  customer=%s  msg=%r",
        request.session_id,
        request.context.get("customer_id", "—"),
        clean_message[:80],
    )

    try:
        reply = agent.run(
            message=clean_message,
            session_id=request.session_id,
            context=request.context,
        )
    except Exception as exc:
        logger.exception("agent.run raised: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))

    return ChatResponse(response=reply, session_id=request.session_id)


# ---------------------------------------------------------------------------
# Dev entry-point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import os
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=True)
