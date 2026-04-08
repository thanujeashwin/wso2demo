"""
Observability layer for the Morrisons WSO2 Agent Manager demo.

Emits:
  - Structured JSON logs  (stdout → Splunk / GCP Logging / CloudWatch)
  - OpenTelemetry spans   (OTLP → WSO2 Choreo Observability / Jaeger / Grafana)
  - Agent health metrics  (Prometheus-compatible counters & histograms)

In production this wraps the real opentelemetry-sdk.
For the demo it provides a lightweight zero-dependency shim that prints
colour-coded traces so they are easy to follow during a live walkthrough.
"""
from __future__ import annotations

import json
import time
import uuid
import logging
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, Generator, List, Optional

from shared.models import AgentID, ObservabilitySpan

# ── ANSI colours for demo console output ────────────────────────────────────
RESET   = "\033[0m"
BOLD    = "\033[1m"
CYAN    = "\033[36m"
GREEN   = "\033[32m"
YELLOW  = "\033[33m"
RED     = "\033[31m"
MAGENTA = "\033[35m"
BLUE    = "\033[34m"

AGENT_COLOURS: Dict[AgentID, str] = {
    AgentID.ORCHESTRATOR: BOLD + MAGENTA,
    AgentID.SAP_ERP:      BOLD + BLUE,
    AgentID.ORACLE_ERP:   BOLD + CYAN,
    AgentID.SALESFORCE:   BOLD + GREEN,
    AgentID.AWS_CLOUD:    BOLD + YELLOW,
    AgentID.GCP_CLOUD:    BOLD + RED,
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("wso2.agents")


# In-memory span store (demo only; in prod → OTLP exporter)
_spans: List[ObservabilitySpan] = []
# Simple metric counters
_metrics: Dict[str, int] = {}


def _colour(agent: AgentID, text: str) -> str:
    return AGENT_COLOURS.get(agent, "") + text + RESET


def log_event(agent: AgentID, event: str, data: Optional[Dict[str, Any]] = None) -> None:
    """Emit a structured log line and pretty-print for the demo console."""
    record = {
        "ts":     datetime.utcnow().isoformat(),
        "agent":  agent.value,
        "event":  event,
        "data":   data or {},
    }
    logger.info(_colour(agent, f"[{agent.value}] {event}") +
                (f"  {json.dumps(data)}" if data else ""))


def increment(metric: str, value: int = 1) -> None:
    _metrics[metric] = _metrics.get(metric, 0) + value


def get_metrics() -> Dict[str, int]:
    return dict(_metrics)


@contextmanager
def trace_span(
    agent: AgentID,
    operation: str,
    trace_id: Optional[str] = None,
    parent_span_id: Optional[str] = None,
    attributes: Optional[Dict[str, Any]] = None,
) -> Generator[ObservabilitySpan, None, None]:
    """
    Context manager that wraps any agent operation in an OTel-style span.

    Usage:
        with trace_span(AgentID.SAP_ERP, "check_stock") as span:
            span.attributes["sku"] = "SKU-001"
            result = do_work()
    """
    span = ObservabilitySpan(
        trace_id=trace_id or str(uuid.uuid4()).replace("-", ""),
        span_id=str(uuid.uuid4()).replace("-", "")[:16],
        parent_span_id=parent_span_id,
        agent_id=agent,
        operation=operation,
        start_time=datetime.utcnow(),
        attributes=attributes or {},
    )
    start = time.perf_counter()
    logger.info(_colour(agent, f"  ▶ START [{operation}]"))
    try:
        yield span
        span.status = "OK"
        increment(f"span.{agent.value}.ok")
    except Exception as exc:
        span.status = "ERROR"
        span.events.append({"name": "exception", "message": str(exc)})
        increment(f"span.{agent.value}.error")
        logger.error(_colour(agent, f"  ✗ ERROR [{operation}]: {exc}"))
        raise
    finally:
        span.end_time = datetime.utcnow()
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        span.attributes["latency_ms"] = elapsed_ms
        _spans.append(span)
        icon = "✔" if span.status == "OK" else "✗"
        logger.info(_colour(agent, f"  {icon}  END  [{operation}]  ({elapsed_ms} ms)"))


def render_trace(trace_id: str) -> None:
    """Pretty-print all spans for a given trace_id (demo console view)."""
    related = [s for s in _spans if s.trace_id == trace_id]
    if not related:
        print(f"No spans found for trace {trace_id}")
        return

    print(f"\n{BOLD}{'─'*70}{RESET}")
    print(f"{BOLD}  WSO2 Agent Manager – Distributed Trace  {trace_id[:12]}…{RESET}")
    print(f"{BOLD}{'─'*70}{RESET}")
    for s in related:
        colour = AGENT_COLOURS.get(s.agent_id, "")
        indent = "    " if s.parent_span_id else "  "
        icon   = "✔" if s.status == "OK" else "✗"
        lat    = s.attributes.get("latency_ms", "?")
        print(f"{indent}{colour}{icon} {s.agent_id.value:<35} "
              f"{s.operation:<30} {lat:>5} ms{RESET}")
    print(f"{BOLD}{'─'*70}{RESET}\n")


def render_agent_health() -> None:
    """Print a mini Prometheus-style health dashboard for the demo."""
    print(f"\n{BOLD}  WSO2 Agent Manager – Agent Health Dashboard{RESET}")
    print(f"{'─'*50}")
    for agent in AgentID:
        ok    = _metrics.get(f"span.{agent.value}.ok", 0)
        err   = _metrics.get(f"span.{agent.value}.error", 0)
        total = ok + err
        bar   = "█" * ok + "░" * err
        colour = AGENT_COLOURS.get(agent, "")
        print(f"  {colour}{agent.value:<35}{RESET}  "
              f"calls={total:>3}  ok={ok:>3}  err={err:>3}  [{bar}]")
    print(f"{'─'*50}\n")
