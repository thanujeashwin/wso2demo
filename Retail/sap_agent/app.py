"""
Morrisons SAP ERP Agent – FastAPI Application
==============================================
Exposes a single /chat endpoint following the WSO2 Agent Manager
native agent pattern (identical to the hotel-booking sample agent).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, status
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field, field_validator

from graph import build_graph

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Morrisons SAP ERP Agent",
    description="SAP S/4HANA agent for stock, purchase orders, supplier data, and demand forecasting.",
    version="1.0.0",
)

agent_graph = build_graph()


# ── Request / Response models ─────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="User's question or instruction")
    session_id: str = Field(..., description="Unique session / conversation ID")
    context: dict[str, Any] = Field(default_factory=dict, description="Optional context (store_id, user_id, etc.)")

    @field_validator("session_id", mode="before")
    @classmethod
    def validate_session_id(cls, v: Any) -> str:
        if not isinstance(v, str):
            v = str(v)
        v = v.strip()
        if not v:
            raise ValueError("session_id must be a non-empty string")
        return v


class ChatResponse(BaseModel):
    response: str


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_message(message: str, context: dict[str, Any]) -> str:
    """Wrap the user message with context and timestamp, matching WSO2 sample pattern."""
    now = datetime.now(timezone.utc).isoformat()
    ctx = json.dumps(context, default=str, ensure_ascii=True)
    return f"Request Context:\n{ctx}\nUTC Time: {now}\n\nUser Query:\n{message}"


def _thread_id(session_id: str, context: dict[str, Any]) -> str:
    user_id = context.get("user_id", "")
    if isinstance(user_id, str) and user_id.strip():
        return f"{user_id.strip()}:{session_id}"
    return f"anonymous:{session_id}"


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "agent": "morrisons-sap-erp-agent"}


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    wrapped = _build_message(request.message, request.context)
    thread  = _thread_id(request.session_id, request.context)

    try:
        result = agent_graph.invoke(
            {"messages": [HumanMessage(content=wrapped)]},
            config={
                "recursion_limit": 25,
                "configurable": {"thread_id": thread},
            },
        )
    except Exception:
        logger.exception("Agent invoke failed: session=%s", request.session_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )

    messages = result.get("messages") if isinstance(result, dict) else None
    if not messages:
        return ChatResponse(response="")

    content = messages[-1].content
    if isinstance(content, str):
        return ChatResponse(response=content)
    if isinstance(content, list):
        return ChatResponse(response="\n".join(str(p) for p in content))
    return ChatResponse(response=str(content))
