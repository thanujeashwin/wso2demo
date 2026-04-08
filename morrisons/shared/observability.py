"""
WSO2 Agent Manager – Observability Layer (OpenTelemetry)
═════════════════════════════════════════════════════════
Emits real OpenTelemetry traces, metrics, and structured logs that
WSO2 Agent Manager / Choreo Observability can ingest.

How WSO2 Agent Manager picks up traces
───────────────────────────────────────
When "Enable auto instrumentation" is ticked on the agent form, WSO2
injects these environment variables into the running container:

  OTEL_EXPORTER_OTLP_ENDPOINT   → Choreo OTLP collector (grpc or http)
  OTEL_SERVICE_NAME             → agent name (e.g. morrisons-sap-erp-agent)
  OTEL_TRACES_EXPORTER          → otlp
  OTEL_METRICS_EXPORTER         → otlp
  OTEL_RESOURCE_ATTRIBUTES      → deployment.environment=production,...

This module reads those variables automatically via the OTEL SDK's
standard environment-variable configuration, so no hard-coded endpoints
are needed — it just works when deployed on WSO2 Agent Manager.

Span naming convention (WSO2 Agent Manager expects these attributes):
  agent.id          → morrisons-sap-erp-agent
  agent.tool        → check_stock_level
  agent.domain      → supply_chain
  http.method       → POST  (on HTTP server spans)
  http.route        → /tools/{tool_name}
"""
from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, Generator, List, Optional

# ── OpenTelemetry SDK ────────────────────────────────────────────────────────
from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SimpleSpanProcessor,
)
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import (
    ConsoleMetricExporter,
    PeriodicExportingMetricReader,
)
from opentelemetry.sdk.resources import Resource, SERVICE_NAME
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.trace import Status, StatusCode
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from opentelemetry.propagate import set_global_textmap

# OTLP exporters (used when WSO2 injects OTEL_EXPORTER_OTLP_ENDPOINT)
try:
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
    OTLP_AVAILABLE = True
except ImportError:
    try:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
        OTLP_AVAILABLE = True
    except ImportError:
        OTLP_AVAILABLE = False

from shared.models import AgentID

# ── ANSI colours (console only – not included in OTEL spans) ────────────────
RESET   = "\033[0m";  BOLD    = "\033[1m"
CYAN    = "\033[36m"; GREEN   = "\033[32m"
YELLOW  = "\033[33m"; RED     = "\033[31m"
MAGENTA = "\033[35m"; BLUE    = "\033[34m"

AGENT_COLOURS: Dict[AgentID, str] = {
    AgentID.ORCHESTRATOR: BOLD + MAGENTA,
    AgentID.SAP_ERP:      BOLD + BLUE,
    AgentID.ORACLE_ERP:   BOLD + CYAN,
    AgentID.SALESFORCE:   BOLD + GREEN,
    AgentID.AWS_CLOUD:    BOLD + YELLOW,
    AgentID.GCP_CLOUD:    BOLD + RED,
}

logger = logging.getLogger("wso2.agents")


# ════════════════════════════════════════════════════════════════════════════
# PROVIDER INITIALISATION
# Called once per agent process from main.py via init_telemetry()
# ════════════════════════════════════════════════════════════════════════════

_tracer_provider: Optional[TracerProvider] = None
_meter_provider:  Optional[MeterProvider]  = None
_tracer_cache:    Dict[str, trace.Tracer]  = {}
_counters:        Dict[str, Any]           = {}


def _traceloop_already_configured() -> bool:
    """
    Return True when Traceloop / WSO2 auto-instrumentation has already
    installed a global TracerProvider before our init_telemetry() runs.

    We read _TRACER_PROVIDER directly from opentelemetry.trace — the same
    internal variable the SDK checks before emitting
    "Overriding of current TracerProvider is not allowed".
    This is intentional: isinstance() is fragile across SDK versions and
    Traceloop wrapper classes; the internal variable is authoritative.
    """
    import opentelemetry.trace as _t
    return getattr(_t, "_TRACER_PROVIDER", None) is not None


def _meter_provider_already_set() -> bool:
    """
    Return True when a MeterProvider is already globally registered.
    Mirrors the guard in opentelemetry.metrics._internal._set_meter_provider
    so we never trigger "Overriding of current MeterProvider is not allowed".
    """
    try:
        import opentelemetry.metrics._internal as _mi
        return getattr(_mi, "_METER_PROVIDER", None) is not None
    except Exception:
        return False


def init_telemetry(agent_id: AgentID) -> None:
    """
    Initialise OpenTelemetry tracing and metrics for an agent process.

    WSO2 Agent Manager runs Traceloop auto-instrumentation before our code
    starts, which means a real TracerProvider is already registered globally.
    All calls to trace.get_tracer() automatically route through it, so our
    spans (tool calls, heartbeats, periodic checks) are already being exported
    to Choreo Observability — we just must NOT call set_tracer_provider() again
    or the SDK will warn and reject the call.

    Strategy
    ────────
    • Traceloop already active  → adopt the existing provider, attach our
      agent attributes via add_span_processor, skip set_tracer_provider.
    • No provider yet (local dev / bare deploy) → install our own, pointing
      at OTLP if OTEL_EXPORTER_OTLP_ENDPOINT is set, else console.
    """
    global _tracer_provider, _meter_provider

    service_name  = os.environ.get("OTEL_SERVICE_NAME", agent_id.value)
    otlp_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "")

    # ── Case 1: Traceloop / WSO2 already owns the global provider ───────────
    if _traceloop_already_configured():
        existing = trace.get_tracer_provider()
        _tracer_provider = existing  # type: ignore[assignment]

        # Our trace.get_tracer() calls already route through `existing`
        # automatically — no need to re-register.  We only attach one extra
        # BatchSpanProcessor so WSO2 Choreo gets our agent.id / wso2.project
        # attributes on every span (Traceloop doesn't add these by default).
        if hasattr(existing, "add_span_processor") and otlp_endpoint and OTLP_AVAILABLE:
            existing.add_span_processor(
                BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint))
            )
            logger.info(
                f"[{agent_id.value}] Traceloop provider detected – "
                f"attached enriching OTLP processor → {otlp_endpoint}"
            )
        else:
            logger.info(
                f"[{agent_id.value}] Traceloop provider detected – "
                f"spans routed through existing exporter automatically"
            )

        # Metrics: independent of traces, safe to set our own provider.
        _setup_metrics(agent_id, service_name, otlp_endpoint)
        set_global_textmap(TraceContextTextMapPropagator())
        logger.info(
            f"[{agent_id.value}] OpenTelemetry ready  service={service_name}  "
            f"exporter=traceloop→{otlp_endpoint or 'localhost'}"
        )
        return

    # ── Case 2: No provider yet – install our own ───────────────────────────
    resource = Resource.create({
        SERVICE_NAME:             service_name,
        "service.version":        "1.0.0",
        "deployment.environment": os.environ.get("DEPLOYMENT_ENV", "demo"),
        "agent.id":               agent_id.value,
        "wso2.agent.platform":    "agent-manager",
        "wso2.project":           os.environ.get("WSO2_PROJECT", "morrisons-retail"),
    })

    if otlp_endpoint and OTLP_AVAILABLE:
        span_exporter  = OTLPSpanExporter(endpoint=otlp_endpoint)
        span_processor = BatchSpanProcessor(span_exporter)
        logger.info(f"[{agent_id.value}] OTEL traces → OTLP ({otlp_endpoint})")
    else:
        span_exporter  = ConsoleSpanExporter()
        span_processor = SimpleSpanProcessor(span_exporter)
        logger.info(
            f"[{agent_id.value}] OTEL_EXPORTER_OTLP_ENDPOINT not set – "
            f"traces → console"
        )

    _tracer_provider = TracerProvider(resource=resource)
    _tracer_provider.add_span_processor(span_processor)
    trace.set_tracer_provider(_tracer_provider)

    _setup_metrics(agent_id, service_name, otlp_endpoint, resource=resource)
    set_global_textmap(TraceContextTextMapPropagator())
    logger.info(f"[{agent_id.value}] OpenTelemetry initialised  service={service_name}")


def _setup_metrics(
    agent_id: AgentID,
    service_name: str,
    otlp_endpoint: str,
    resource: Optional[Resource] = None,
) -> None:
    """
    Configure MeterProvider — only if one has not already been registered.

    Traceloop may have already called metrics.set_meter_provider(), in which
    case the SDK will warn and reject a second call.  We use the same internal
    check the SDK uses to skip the call entirely when that happens.
    """
    global _meter_provider

    if _meter_provider_already_set():
        # Traceloop (or another auto-instrumentor) already owns the meter —
        # adopt it so our increment() calls route through it automatically.
        _meter_provider = metrics.get_meter_provider()
        logger.info(f"[{agent_id.value}] Adopted existing MeterProvider (Traceloop/WSO2)")
        return

    if resource is None:
        resource = Resource.create({
            SERVICE_NAME:          service_name,
            "agent.id":            agent_id.value,
            "wso2.agent.platform": "agent-manager",
            "wso2.project":        os.environ.get("WSO2_PROJECT", "morrisons-retail"),
        })
    if otlp_endpoint and OTLP_AVAILABLE:
        reader = PeriodicExportingMetricReader(
            OTLPMetricExporter(endpoint=otlp_endpoint),
            export_interval_millis=15_000,
        )
    else:
        reader = PeriodicExportingMetricReader(
            ConsoleMetricExporter(), export_interval_millis=60_000
        )
    _meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
    metrics.set_meter_provider(_meter_provider)


def _get_tracer(agent_id: AgentID) -> trace.Tracer:
    key = agent_id.value
    if key not in _tracer_cache:
        _tracer_cache[key] = trace.get_tracer(
            key, schema_url="https://opentelemetry.io/schemas/1.24.0"
        )
    return _tracer_cache[key]


def _get_counter(name: str) -> Any:
    if name not in _counters:
        meter = metrics.get_meter("wso2.agents")
        _counters[name] = meter.create_counter(name)
    return _counters[name]


# ════════════════════════════════════════════════════════════════════════════
# PUBLIC API  (used by all agents)
# ════════════════════════════════════════════════════════════════════════════

def log_event(
    agent: AgentID,
    event: str,
    data: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Emit a structured log line AND add an event to the current active span.
    WSO2 Agent Manager surfaces span events in the trace timeline.
    """
    colour = AGENT_COLOURS.get(agent, "")
    import json
    logger.info(
        colour + f"[{agent.value}] {event}" + RESET +
        (f"  {json.dumps(data)}" if data else "")
    )
    # Add as a span event so it appears in WSO2 Choreo trace viewer
    current_span = trace.get_current_span()
    if current_span and current_span.is_recording():
        attrs = {f"event.{k}": str(v) for k, v in (data or {}).items()}
        current_span.add_event(event, attributes=attrs)


def increment(metric: str, value: int = 1, attributes: Optional[Dict] = None) -> None:
    """Increment an OTEL counter metric."""
    try:
        _get_counter(metric).add(value, attributes or {})
    except Exception:
        pass   # Never crash an agent due to metrics


@contextmanager
def trace_span(
    agent: AgentID,
    operation: str,
    trace_id: Optional[str] = None,
    parent_span_id: Optional[str] = None,
    attributes: Optional[Dict[str, Any]] = None,
) -> Generator:
    """
    Context manager that wraps any agent operation in a real OTel span.

    The span is exported to WSO2 Choreo Observability (or console if
    OTEL_EXPORTER_OTLP_ENDPOINT is not configured).

    Usage:
        with trace_span(AgentID.SAP_ERP, "check_stock_level",
                        attributes={"sku": sku}) as span:
            span.set_attribute("result.stock", 48)
            result = await do_work()
    """
    tracer = _get_tracer(agent)
    colour = AGENT_COLOURS.get(agent, "")
    logger.info(colour + f"  ▶ START [{operation}]" + RESET)

    span_attrs = {
        "agent.id":        agent.value,
        "agent.operation": operation,
        **(attributes or {}),
    }

    with tracer.start_as_current_span(
        name=f"{agent.value}/{operation}",
        attributes=span_attrs,
        kind=trace.SpanKind.INTERNAL,
    ) as span:
        try:
            yield span
            span.set_status(Status(StatusCode.OK))
            increment(f"span.{agent.value}.ok")
        except Exception as exc:
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            span.record_exception(exc)
            increment(f"span.{agent.value}.error")
            logger.error(colour + f"  ✗ ERROR [{operation}]: {exc}" + RESET)
            raise
        finally:
            # Latency logged for console visibility
            logger.info(colour + f"  ✔  END  [{operation}]" + RESET)


def get_trace_context_headers() -> Dict[str, str]:
    """
    Return W3C traceparent/tracestate headers for the current span.
    Used to propagate context to sub-agent HTTP calls.
    """
    from opentelemetry.propagate import inject
    headers: Dict[str, str] = {}
    inject(headers)
    return headers


def shutdown_telemetry() -> None:
    """Flush and shut down providers gracefully on agent stop."""
    global _tracer_provider, _meter_provider
    if _tracer_provider:
        _tracer_provider.shutdown()
    if _meter_provider:
        _meter_provider.shutdown()


# ── Legacy compat: render_trace / render_agent_health (console only) ─────────
def render_trace(trace_id: str) -> None:
    logger.info(f"Trace {trace_id} – view in WSO2 Choreo Observability dashboard")


def render_agent_health() -> None:
    logger.info("Agent health – view metrics in WSO2 Choreo Observability dashboard")


# ════════════════════════════════════════════════════════════════════════════
# PERIODIC EMITTER
# Runs as an asyncio background task inside each agent process.
# Emits heartbeat spans + structured log lines on a fixed cadence so that
# WSO2 Choreo Observability always shows live activity even when no tool
# calls are in flight.
# ════════════════════════════════════════════════════════════════════════════

import asyncio as _asyncio
import time as _time

class PeriodicEmitter:
    """
    Background task that periodically emits OpenTelemetry spans and
    structured log lines so that WSO2 Choreo always shows live agent activity.

    Emits two kinds of spans:
      • heartbeat  – every `heartbeat_interval` seconds (default 30s)
                     attributes: uptime_seconds, requests_served, agent status
      • health_log – every `log_interval` seconds (default 60s)
                     a structured INFO log line summarising agent health

    Additionally, callers can supply a list of `extra_callbacks`: async
    callables that are invoked on the heartbeat cadence. Use these to emit
    agent-specific periodic spans (e.g. SAP low-stock scan, GCP IoT poll).

    Usage (inside HTTPAgentServer.run_forever):
        self._emitter = PeriodicEmitter(
            agent_id=self.agent_id,
            get_uptime=lambda: int((datetime.utcnow() - self._started_at).total_seconds()),
            get_requests=lambda: self._requests,
            extra_callbacks=[my_agent.periodic_checks],
        )
        await self._emitter.start()
        ...
        await self._emitter.stop()
    """

    def __init__(
        self,
        agent_id: "AgentID",
        get_uptime,                     # callable → int (uptime seconds)
        get_requests,                   # callable → int (total requests served)
        heartbeat_interval: int = 30,   # seconds between heartbeat spans
        log_interval: int = 60,         # seconds between health log lines
        extra_callbacks: Optional[List] = None,
    ):
        self.agent_id           = agent_id
        self.get_uptime         = get_uptime
        self.get_requests       = get_requests
        self.heartbeat_interval = heartbeat_interval
        self.log_interval       = log_interval
        self.extra_callbacks    = extra_callbacks or []
        self._task: Optional[_asyncio.Task] = None
        self._started_wall      = _time.monotonic()

    async def start(self) -> None:
        """Start the background emission loop."""
        self._task = _asyncio.create_task(self._loop(), name=f"periodic-{self.agent_id.value}")
        logger.info(f"[{self.agent_id.value}] PeriodicEmitter started "
                    f"(heartbeat={self.heartbeat_interval}s, log={self.log_interval}s)")

    async def stop(self) -> None:
        """Cancel the loop and flush any in-flight spans."""
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await _asyncio.wait_for(self._task, timeout=3.0)
            except (_asyncio.CancelledError, _asyncio.TimeoutError):
                pass
        logger.info(f"[{self.agent_id.value}] PeriodicEmitter stopped")

    # ── Internal loop ────────────────────────────────────────────────────────
    async def _loop(self) -> None:
        tick = 0
        while True:
            await _asyncio.sleep(self.heartbeat_interval)
            tick += 1
            try:
                await self._emit_heartbeat(tick)
            except Exception as exc:
                logger.warning(f"[{self.agent_id.value}] PeriodicEmitter heartbeat error: {exc}")

            # Health log on every Nth heartbeat
            if tick % max(1, self.log_interval // self.heartbeat_interval) == 0:
                try:
                    self._emit_health_log()
                except Exception as exc:
                    logger.warning(f"[{self.agent_id.value}] PeriodicEmitter health log error: {exc}")

            # Agent-specific callbacks
            for cb in self.extra_callbacks:
                try:
                    await cb()
                except Exception as exc:
                    logger.warning(
                        f"[{self.agent_id.value}] PeriodicEmitter callback "
                        f"{getattr(cb, '__name__', cb)} error: {exc}"
                    )

    async def _emit_heartbeat(self, tick: int) -> None:
        """
        Emit a SHORT-LIVED OpenTelemetry INTERNAL span labelled 'agent/heartbeat'.
        WSO2 Choreo will display this in the Traces view so the agent appears alive
        even between tool invocations.
        """
        tracer  = _get_tracer(self.agent_id)
        uptime  = self.get_uptime()
        reqs    = self.get_requests()
        colour  = AGENT_COLOURS.get(self.agent_id, "")

        with tracer.start_as_current_span(
            f"{self.agent_id.value}/heartbeat",
            kind=trace.SpanKind.INTERNAL,
            attributes={
                "agent.id":                self.agent_id.value,
                "agent.operation":         "heartbeat",
                "heartbeat.tick":          tick,
                "agent.uptime_seconds":    uptime,
                "agent.requests_served":   reqs,
                "agent.status":            "RUNNING",
                "deployment.environment":  os.environ.get("DEPLOYMENT_ENV", "demo"),
            },
        ) as span:
            span.add_event(
                "heartbeat",
                attributes={
                    "uptime_seconds":  str(uptime),
                    "requests_served": str(reqs),
                    "tick":            str(tick),
                },
            )
            span.set_status(Status(StatusCode.OK))

        increment(f"agent.{self.agent_id.value}.heartbeats")
        logger.debug(
            colour + f"  ♥ [{self.agent_id.value}] heartbeat tick={tick} "
            f"uptime={uptime}s requests={reqs}" + RESET
        )

    def _emit_health_log(self) -> None:
        """Emit a structured INFO log line summarising agent health."""
        uptime  = self.get_uptime()
        reqs    = self.get_requests()
        colour  = AGENT_COLOURS.get(self.agent_id, "")
        import json
        logger.info(
            colour + f"[{self.agent_id.value}] HEALTH" + RESET +
            "  " + json.dumps({
                "agent":    self.agent_id.value,
                "status":   "RUNNING",
                "uptime_s": uptime,
                "requests": reqs,
                "env":      os.environ.get("DEPLOYMENT_ENV", "demo"),
            })
        )
