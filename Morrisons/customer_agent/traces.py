"""traces.py — OpenTelemetry instrumentation for the Customer Agent.

Uses the standard opentelemetry-api so spans are exported by whichever
SDK/exporter is active in the process.

When running on WSO2 Agent Manager, Traceloop injects the SDK and OTLP
exporter automatically via sitecustomize.py — no initialisation code is
needed here (adding it would conflict with the platform tracer).

When running locally without a collector, spans are silently dropped
(the no-op tracer is used).  Set OTEL_TRACES_EXPORTER=console to print
spans to stdout during local development.
"""

from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from typing import Any, Generator

from opentelemetry import trace
from opentelemetry.trace import Span, Status, StatusCode

logger = logging.getLogger("customer_agent.traces")

# Module-level tracer — resolved against whichever TracerProvider is active.
# On WSO2 Agent Manager this is the Traceloop provider; locally it is the
# no-op provider unless the user has configured one.
_tracer = trace.get_tracer("customer_agent", "1.0.0")


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

@contextmanager
def start_span(
    name: str,
    attributes: dict[str, Any] | None = None,
) -> Generator[Span, None, None]:
    """Context manager that wraps a block of code in an OTel span."""
    with _tracer.start_as_current_span(name) as span:
        if attributes:
            for k, v in attributes.items():
                try:
                    span.set_attribute(
                        k,
                        v if isinstance(v, (str, int, float, bool)) else str(v),
                    )
                except Exception:
                    pass
        try:
            yield span
            span.set_status(Status(StatusCode.OK))
        except Exception as exc:
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            span.record_exception(exc)
            raise


def trace_llm_call(
    model_name: str,
    prompt: str,
    response: str,
    span: Span | None = None,
) -> None:
    """Emit a child span representing one LLM inference call."""
    with _tracer.start_as_current_span("llm.generate") as s:
        s.set_attribute("gen_ai.system",         "google_gemini")
        s.set_attribute("gen_ai.request.model",  model_name)
        s.set_attribute("llm.prompt_chars",       len(prompt))
        s.set_attribute("llm.response_chars",     len(response))
        s.set_attribute("span.kind",              "llm")
        s.add_event("llm.prompt",   {"content": prompt[:512]})
        s.add_event("llm.response", {"content": response[:512]})
        s.set_status(Status(StatusCode.OK))


def trace_agent_step(
    step: int,
    action: str,
    observation: str,
    span: Span | None = None,
) -> None:
    """Emit a child span for one ReAct step (Think → Act → Observe)."""
    with _tracer.start_as_current_span("agent.step") as s:
        s.set_attribute("react.step",        step)
        s.set_attribute("react.action",      action)
        s.set_attribute("react.observation", observation[:512])
        s.set_attribute("span.kind",         "agent_step")
        s.set_status(Status(StatusCode.OK))


def trace_tool(tool_name: str):
    """Decorator: wraps a sync tool function in an OTel span."""
    def decorator(fn):
        def wrapper(*args, **kwargs):
            with _tracer.start_as_current_span(f"tool.{tool_name}") as s:
                s.set_attribute("tool.name",  tool_name)
                s.set_attribute("span.kind",  "tool")
                s.set_attribute("tool.args",  json.dumps(kwargs, default=str)[:512])
                try:
                    result = fn(*args, **kwargs)
                    s.set_attribute("tool.result_chars", len(str(result)))
                    s.set_status(Status(StatusCode.OK))
                    return result
                except Exception as exc:
                    s.set_status(Status(StatusCode.ERROR, str(exc)))
                    s.record_exception(exc)
                    raise
        wrapper.__name__ = fn.__name__
        return wrapper
    return decorator
