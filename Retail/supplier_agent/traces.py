"""traces.py — OpenTelemetry instrumentation for the Supplier Agent."""

from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from typing import Any, Generator

from opentelemetry import trace
from opentelemetry.trace import Span, Status, StatusCode

logger  = logging.getLogger("supplier_agent.traces")
_tracer = trace.get_tracer("supplier_agent", "1.0.0")


@contextmanager
def start_span(name: str, attributes: dict[str, Any] | None = None) -> Generator[Span, None, None]:
    with _tracer.start_as_current_span(name) as span:
        if attributes:
            for k, v in attributes.items():
                try:
                    span.set_attribute(k, v if isinstance(v, (str, int, float, bool)) else str(v))
                except Exception:
                    pass
        try:
            yield span
            span.set_status(Status(StatusCode.OK))
        except Exception as exc:
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            span.record_exception(exc)
            raise


def trace_agent_step(step: int, action: str, observation: str) -> None:
    with _tracer.start_as_current_span("agent.step") as s:
        s.set_attribute("react.step",        step)
        s.set_attribute("react.action",      action)
        s.set_attribute("react.observation", observation[:512])
        s.set_attribute("span.kind",         "agent_step")
        s.set_status(Status(StatusCode.OK))


def trace_tool(tool_name: str):
    def decorator(fn):
        def wrapper(*args, **kwargs):
            with _tracer.start_as_current_span(f"tool.{tool_name}") as s:
                s.set_attribute("tool.name", tool_name)
                s.set_attribute("span.kind", "tool")
                s.set_attribute("tool.args", json.dumps(kwargs, default=str)[:512])
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
