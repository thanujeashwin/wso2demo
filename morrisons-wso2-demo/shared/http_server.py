"""
WSO2 Agent Manager – HTTP Agent Server
════════════════════════════════════════
Replaces the raw TCP server with a proper HTTP/REST API so each agent
can be registered in WSO2 Agent Manager as a "Custom API Agent".

WSO2 Agent Manager expects:
  • An HTTP server on a declared port
  • An OpenAPI 3.0 spec at a declared path (e.g. /openapi.json)
  • A base path (e.g. /)
  • Health endpoint at GET /health
  • OTEL auto-instrumentation supported (WSO2 injects OTEL SDK on deploy)

Endpoint layout
────────────────
  GET  /health              → liveness probe (used by WSO2 platform)
  GET  /status              → agent status (uptime, request count, model)
  GET  /tools               → list all tools (MCP tools/list equivalent)
  GET  /openapi.json        → OpenAPI 3.0 spec (required by WSO2 form)
  POST /tools/{tool_name}   → invoke a tool  (JSON body = arguments)
  POST /stop                → graceful shutdown (admin only)

All requests/responses use JSON.
Errors follow RFC 7807 Problem Details format.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

try:
    from aiohttp import web
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False

from shared.models import AgentID
from shared.observability import log_event, trace_span, GREEN, RED, YELLOW, BOLD, RESET, CYAN

logger = logging.getLogger("wso2.http_server")

# ── Port map (must match wso2/agent_manager_config.yaml) ────────────────────
AGENT_PORTS: Dict[AgentID, int] = {
    AgentID.ORCHESTRATOR: 8000,
    AgentID.SAP_ERP:      8001,
    AgentID.ORACLE_ERP:   8002,
    AgentID.SALESFORCE:   8003,
    AgentID.AWS_CLOUD:    8004,
    AgentID.GCP_CLOUD:    8005,
}

LOG_DIR = Path(__file__).parent.parent / "logs"
PID_DIR = Path(__file__).parent.parent / "run"


class HTTPAgentServer:
    """
    HTTP server that makes any agent deployable on WSO2 Agent Manager
    as a "Custom API Agent".
    """

    def __init__(
        self,
        agent_id: AgentID,
        dispatch_fn: Callable,
        tools_meta: List[Dict[str, Any]],
        openapi_spec: Optional[Dict[str, Any]] = None,
    ):
        self.agent_id    = agent_id
        self.dispatch    = dispatch_fn
        self.tools_meta  = tools_meta
        self.port        = AGENT_PORTS[agent_id]
        self._openapi    = openapi_spec or self._default_openapi()
        self._started_at: Optional[datetime] = None
        self._requests   = 0
        self._runner     = None
        self._site       = None

        LOG_DIR.mkdir(exist_ok=True)
        PID_DIR.mkdir(exist_ok=True)
        self._pid_file = PID_DIR / f"{agent_id.value}.pid"
        self._log_file = LOG_DIR / f"{agent_id.value}.log"

        fh = logging.FileHandler(self._log_file)
        fh.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)-8s %(message)s", "%Y-%m-%d %H:%M:%S"))
        logger.addHandler(fh)

    # ── Route handlers ────────────────────────────────────────────────────────

    async def _health(self, request: "web.Request") -> "web.Response":
        """GET /health — WSO2 liveness probe."""
        return web.json_response({"status": "UP", "agent": self.agent_id.value})

    async def _status(self, request: "web.Request") -> "web.Response":
        """GET /status — detailed agent status."""
        uptime = int((datetime.utcnow() - self._started_at).total_seconds()) \
                 if self._started_at else 0
        return web.json_response({
            "agent":            self.agent_id.value,
            "status":           "RUNNING",
            "port":             self.port,
            "pid":              os.getpid(),
            "uptime_seconds":   uptime,
            "requests_served":  self._requests,
            "started_at":       self._started_at.isoformat() if self._started_at else None,
            "tools":            [t["name"] for t in self.tools_meta],
        })

    async def _list_tools(self, request: "web.Request") -> "web.Response":
        """GET /tools — MCP tools/list equivalent."""
        return web.json_response({"tools": self.tools_meta})

    async def _openapi_spec(self, request: "web.Request") -> "web.Response":
        """GET /openapi.json — OpenAPI 3.0 spec required by WSO2 form."""
        return web.json_response(self._openapi)

    async def _invoke_tool(self, request: "web.Request") -> "web.Response":
        """POST /tools/{tool_name} — invoke a single tool."""
        tool_name = request.match_info["tool_name"]
        trace_id  = request.headers.get("X-Trace-Id", uuid.uuid4().hex)

        try:
            body = await request.json() if request.can_read_body else {}
        except json.JSONDecodeError:
            return web.json_response(
                {"type": "about:blank", "title": "Bad Request",
                 "detail": "Request body must be valid JSON", "status": 400},
                status=400,
            )

        # Validate tool exists
        known = {t["name"] for t in self.tools_meta}
        if tool_name not in known:
            return web.json_response(
                {"type": "about:blank", "title": "Not Found",
                 "detail": f"Tool '{tool_name}' not registered on this agent.",
                 "available_tools": list(known), "status": 404},
                status=404,
            )

        t0 = time.perf_counter()
        try:
            result = await self.dispatch(tool_name, body, trace_id)
            latency_ms = int((time.perf_counter() - t0) * 1000)
            self._requests += 1
            log_event(self.agent_id, f"Tool called: {tool_name}",
                      {"latency_ms": latency_ms, "trace_id": trace_id})
            return web.json_response({
                "tool":       tool_name,
                "result":     result,
                "agent":      self.agent_id.value,
                "trace_id":   trace_id,
                "latency_ms": latency_ms,
            })
        except Exception as exc:
            logger.exception(f"Error invoking tool {tool_name}")
            return web.json_response(
                {"type": "about:blank", "title": "Internal Server Error",
                 "detail": str(exc), "tool": tool_name, "status": 500},
                status=500,
            )

    async def _stop_endpoint(self, request: "web.Request") -> "web.Response":
        """POST /stop — graceful remote shutdown."""
        asyncio.get_event_loop().call_later(0.5, self._initiate_shutdown)
        return web.json_response({
            "message": f"{self.agent_id.value} shutting down gracefully"})

    def _initiate_shutdown(self):
        log_event(self.agent_id, "Remote stop received – shutting down")
        asyncio.create_task(self._shutdown())

    # ── Middleware: request logging ───────────────────────────────────────────
    @web.middleware
    async def _log_middleware(self, request: "web.Request", handler) -> "web.Response":
        start = time.perf_counter()
        try:
            response = await handler(request)
            elapsed  = int((time.perf_counter() - start) * 1000)
            logger.info(f"{request.method} {request.path} → {response.status} ({elapsed}ms)")
            response.headers["X-Agent-Id"]    = self.agent_id.value
            response.headers["X-Latency-Ms"]  = str(elapsed)
            return response
        except Exception as exc:
            logger.error(f"{request.method} {request.path} → ERROR: {exc}")
            raise

    # ── App builder ───────────────────────────────────────────────────────────
    def _build_app(self) -> "web.Application":
        app = web.Application(middlewares=[self._log_middleware])
        app.router.add_get ("/health",                self._health)
        app.router.add_get ("/status",                self._status)
        app.router.add_get ("/tools",                 self._list_tools)
        app.router.add_get ("/openapi.json",          self._openapi_spec)
        app.router.add_post("/tools/{tool_name}",     self._invoke_tool)
        app.router.add_post("/stop",                  self._stop_endpoint)
        return app

    # ── Default OpenAPI spec ──────────────────────────────────────────────────
    def _default_openapi(self) -> Dict[str, Any]:
        paths: Dict[str, Any] = {}
        for tool in self.tools_meta:
            name = tool["name"]
            paths[f"/tools/{name}"] = {
                "post": {
                    "operationId": name,
                    "summary":     tool.get("description", name),
                    "tags":        [self.agent_id.value],
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {
                            "schema": tool.get("inputSchema",
                                              {"type": "object"})
                        }},
                    },
                    "responses": {
                        "200": {"description": "Tool result",
                                "content": {"application/json": {
                                    "schema": {"type": "object"}}}},
                        "400": {"description": "Bad request"},
                        "404": {"description": "Tool not found"},
                        "500": {"description": "Internal error"},
                    },
                }
            }
        return {
            "openapi": "3.0.3",
            "info": {
                "title":       f"{self.agent_id.value} API",
                "description": f"Morrisons WSO2 Agent Manager – {self.agent_id.value}",
                "version":     "1.0.0",
            },
            "servers": [{"url": f"http://localhost:{self.port}"}],
            "paths": paths,
        }

    # ── Signal handling ───────────────────────────────────────────────────────
    def _install_signals(self) -> None:
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(self._shutdown()))

    async def _shutdown(self) -> None:
        print(f"\n{YELLOW}[{self.agent_id.value}] Shutdown – draining…{RESET}")
        logger.info(f"Shutdown initiated – served {self._requests} requests")
        if self._runner:
            await self._runner.cleanup()
        try:
            self._pid_file.unlink(missing_ok=True)
        except PermissionError:
            pass
        print(f"{RED}  ✖ {self.agent_id.value} stopped  "
              f"(served {self._requests} requests){RESET}")
        asyncio.get_event_loop().stop()

    # ── Main run loop ─────────────────────────────────────────────────────────
    async def run_forever(self) -> None:
        if not AIOHTTP_AVAILABLE:
            print(f"{RED}aiohttp not installed. Run: pip install aiohttp{RESET}")
            sys.exit(1)

        self._started_at = datetime.utcnow()
        self._install_signals()

        # Write PID
        self._pid_file.write_text(str(os.getpid()))

        app     = self._build_app()
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, "0.0.0.0", self.port)
        await self._site.start()

        log_event(self.agent_id, "HTTP Agent Server STARTED",
                  {"port": self.port, "pid": os.getpid()})
        print(
            f"{GREEN}{BOLD}  ✔ {self.agent_id.value}{RESET}"
            f"  http://0.0.0.0:{CYAN}{self.port}{RESET}"
            f"  /openapi.json  /health  /tools"
            f"  pid={os.getpid()}"
        )

        # Run until stop is called
        await asyncio.Event().wait()

    def run(self) -> None:
        """Blocking entry point called from main.py."""
        try:
            asyncio.run(self.run_forever())
        except (KeyboardInterrupt, RuntimeError):
            pass
