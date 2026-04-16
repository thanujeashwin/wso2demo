"""traces.py — Mock OpenTelemetry tracing compatible with Traceloop / WSO2 Agent Manager.

Publishes realistic span data to stdout as OTLP-style JSON so it can be
piped to a collector or inspected directly.  No real OTLP endpoint needed.
"""

from __future__ import annotations

import json
import time
import uuid
import logging
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Generator

logger = logging.getLogger("customer_agent.traces")


# ---------------------------------------------------------------------------
# Span model
# ---------------------------------------------------------------------------

@dataclass
class Span:
    name: str
    trace_id: str
    span_id: str
    parent_span_id: str | None
    start_time_ns: int
    end_time_ns: int = 0
    status: str = "UNSET"          # UNSET | OK | ERROR
    attributes: dict[str, Any] = field(default_factory=dict)
    events: list[dict] = field(default_factory=list)

    def finish(self, status: str = "OK") -> None:
        self.end_time_ns = time.time_ns()
        self.status = status

    def add_event(self, name: str, attributes: dict | None = None) -> None:
        self.events.append({
            "name": name,
            "timestamp_ns": time.time_ns(),
            "attributes": attributes or {},
        })

    def to_dict(self) -> dict:
        return {
            "traceId":      self.trace_id,
            "spanId":       self.span_id,
            "parentSpanId": self.parent_span_id,
            "name":         self.name,
            "status":       self.status,
            "startTimeNs":  self.start_time_ns,
            "endTimeNs":    self.end_time_ns,
            "durationMs":   round((self.end_time_ns - self.start_time_ns) / 1_000_000, 3),
            "attributes":   self.attributes,
            "events":       self.events,
        }


# ---------------------------------------------------------------------------
# Tracer / context management
# ---------------------------------------------------------------------------

class Tracer:
    """Lightweight mock tracer.  Mimics opentelemetry-sdk API surface."""

    def __init__(self, service_name: str = "customer_agent"):
        self.service_name = service_name
        self._active_spans: list[Span] = []

    # ── public API ──────────────────────────────────────────────────────────

    @contextmanager
    def start_span(
        self,
        name: str,
        attributes: dict | None = None,
        parent: Span | None = None,
    ) -> Generator[Span, None, None]:
        trace_id = (
            parent.trace_id if parent else uuid.uuid4().hex + uuid.uuid4().hex
        )
        parent_id = parent.span_id if parent else (
            self._active_spans[-1].span_id if self._active_spans else None
        )
        span = Span(
            name=name,
            trace_id=trace_id,
            span_id=uuid.uuid4().hex[:16],
            parent_span_id=parent_id,
            start_time_ns=time.time_ns(),
            attributes={
                "service.name": self.service_name,
                **(attributes or {}),
            },
        )
        self._active_spans.append(span)
        try:
            yield span
            span.finish("OK")
        except Exception as exc:
            span.add_event("exception", {"exception.message": str(exc)})
            span.finish("ERROR")
            raise
        finally:
            self._active_spans.remove(span)
            self._export(span)

    def current_span(self) -> Span | None:
        return self._active_spans[-1] if self._active_spans else None

    # ── internal ────────────────────────────────────────────────────────────

    def _export(self, span: Span) -> None:
        """Emit span as JSON to stdout (simulates OTLP export)."""
        payload = {
            "resourceSpans": [{
                "resource": {
                    "attributes": {
                        "service.name":    self.service_name,
                        "service.version": "1.0.0",
                        "deployment.env":  "demo",
                    }
                },
                "scopeSpans": [{
                    "scope": {"name": "customer_agent.tracer", "version": "1.0.0"},
                    "spans": [span.to_dict()],
                }]
            }]
        }
        print(f"[OTLP-SPAN] {json.dumps(payload)}", flush=True)
        logger.debug("exported span: %s (%s) — %s ms",
                     span.name, span.status,
                     round((span.end_time_ns - span.start_time_ns) / 1_000_000, 1))


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

tracer = Tracer(service_name="customer_agent")


# ---------------------------------------------------------------------------
# Convenience decorators / helpers
# ---------------------------------------------------------------------------

def trace_tool(tool_name: str):
    """Decorator: wraps a sync tool function in a span."""
    def decorator(fn):
        def wrapper(*args, **kwargs):
            attrs = {
                "tool.name":    tool_name,
                "tool.args":    json.dumps({**kwargs}, default=str)[:512],
                "agent.type":   "customer_agent",
                "span.kind":    "tool_call",
            }
            with tracer.start_span(f"tool:{tool_name}", attributes=attrs) as span:
                result = fn(*args, **kwargs)
                span.attributes["tool.result_chars"] = len(str(result))
                return result
        wrapper.__name__ = fn.__name__
        return wrapper
    return decorator


def trace_llm_call(model_name: str, prompt: str, response: str, span: Span | None = None) -> None:
    """Emit a child span representing an LLM inference call."""
    attrs = {
        "llm.model":          model_name,
        "llm.prompt_chars":   len(prompt),
        "llm.response_chars": len(response),
        "span.kind":          "llm",
        "gen_ai.system":      "demo_llm",
    }
    parent = span or tracer.current_span()
    with tracer.start_span("llm:think", attributes=attrs, parent=parent) as s:
        s.add_event("llm.prompt",    {"content": prompt[:256]})
        s.add_event("llm.response",  {"content": response[:256]})


def trace_agent_step(step: int, action: str, observation: str, span: Span | None = None) -> None:
    """Emit a child span for one ReAct step."""
    attrs = {
        "react.step":         step,
        "react.action":       action,
        "react.observation":  observation[:256],
        "span.kind":          "agent_step",
    }
    parent = span or tracer.current_span()
    with tracer.start_span(f"react:step:{step}", attributes=attrs, parent=parent):
        pass
