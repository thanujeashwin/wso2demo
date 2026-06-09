"""app.py — FastAPI service for the Supplier Agent."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

import agent
from tools import TOOL_REGISTRY

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s")
logger = logging.getLogger("supplier_agent.app")

app = FastAPI(title="Morrisons Supplier Agent", version="1.0.0")


class ChatRequest(BaseModel):
    message:    str            = Field(..., min_length=1)
    session_id: str            = Field(...)
    context:    dict[str, Any] = Field(default_factory=dict)


class ChatResponse(BaseModel):
    response:   str
    session_id: str
    agent:      str = "supplier_agent"


@app.get("/health")
def health():
    return {"status": "ok", "agent": "supplier_agent", "version": "1.0.0"}


@app.get("/tools")
def list_tools():
    return {
        "agent": "supplier_agent",
        "tools": [{"name": t["name"], "description": t["description"], "parameters": t["parameters"]}
                  for t in TOOL_REGISTRY.values()],
    }


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    logger.info("chat  session=%s  msg=%r", request.session_id, request.message[:80])
    try:
        reply = agent.run(message=request.message, session_id=request.session_id, context=request.context)
    except Exception as exc:
        logger.exception("agent.run raised: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
    return ChatResponse(response=reply, session_id=request.session_id)
