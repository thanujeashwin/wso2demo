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
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import agent
from tools import TOOL_REGISTRY

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
    reply: str
    session_id: str
    agent: str = "customer_agent"
    port: int = 8006


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
    logger.info(
        "chat  session=%s  customer=%s  msg=%r",
        request.session_id,
        request.context.get("customer_id", "—"),
        request.message[:80],
    )

    try:
        reply = agent.run(
            message=request.message,
            session_id=request.session_id,
            context=request.context,
        )
    except Exception as exc:
        logger.exception("agent.run raised: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))

    return ChatResponse(reply=reply, session_id=request.session_id)


# ---------------------------------------------------------------------------
# Dev entry-point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=8006, reload=True)
