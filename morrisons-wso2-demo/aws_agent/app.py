from __future__ import annotations
import json, logging
from datetime import datetime, timezone
from typing import Any
from fastapi import FastAPI, HTTPException, status
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field, field_validator
from graph import build_graph

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)
app = FastAPI(title="Morrisons AWS Cloud Agent", version="1.0.0")
agent_graph = build_graph()

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    session_id: str
    context: dict[str, Any] = Field(default_factory=dict)
    @field_validator("session_id", mode="before")
    @classmethod
    def validate_session_id(cls, v: Any) -> str:
        v = str(v).strip()
        if not v: raise ValueError("session_id must be non-empty")
        return v

class ChatResponse(BaseModel):
    response: str

@app.get("/health")
def health(): return {"status": "ok", "agent": "morrisons-aws-cloud-agent"}

@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    now = datetime.now(timezone.utc).isoformat()
    ctx = json.dumps(request.context, default=str)
    wrapped = f"Context: {ctx}\nTime: {now}\n\nUser: {request.message}"
    uid = request.context.get("user_id", "")
    thread = f"{uid}:{request.session_id}" if uid else f"anonymous:{request.session_id}"
    try:
        result = agent_graph.invoke(
            {"messages": [HumanMessage(content=wrapped)]},
            config={"recursion_limit": 25, "configurable": {"thread_id": thread}},
        )
    except Exception:
        logger.exception("Agent invoke failed: session=%s", request.session_id)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")
    messages = result.get("messages") if isinstance(result, dict) else None
    if not messages: return ChatResponse(response="")
    content = messages[-1].content
    if isinstance(content, str): return ChatResponse(response=content)
    if isinstance(content, list): return ChatResponse(response="\n".join(str(p) for p in content))
    return ChatResponse(response=str(content))
