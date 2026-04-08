"""
WSO2 Agent Manager – Base Agent Server
════════════════════════════════════════
Provides a continuous-running, gracefully-stoppable MCP-over-TCP server
that every agent inherits from.

Each agent listens on its own port and accepts newline-delimited JSON
requests (MCP-compatible envelope). Results are streamed back over the
same connection (SSE-style chunked response).

Lifecycle
---------
  start  → asyncio event loop + TCP listener + PID file written
  run    → accept connections indefinitely, route tool calls
  stop   → SIGTERM or `stop` command → graceful drain + PID file removed
  force  → SIGKILL if drain timeout exceeded (5 s)

Stop mechanisms
---------------
  1.  python manage_agents.py stop <agent>     (sends SIGTERM via PID file)
  2.  ./stop_agents.sh                         (stops all agents)
  3.  Ctrl+C inside the running process        (SIGINT → graceful shutdown)
  4.  HTTP DELETE /stop  on the agent port     (remote stop via API)
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
from typing import Any, Callable, Dict, Optional

from shared.models import AgentID
from shared.observability import log_event, BOLD, GREEN, RED, YELLOW, RESET, CYAN

logger = logging.getLogger("wso2.server")

# PID files live next to this file's project root
PID_DIR = Path(__file__).parent.parent / "run"
LOG_DIR = Path(__file__).parent.parent / "logs"

# Agent port assignments (fixed so WSO2 API Manager config is stable)
AGENT_PORTS: Dict[AgentID, int] = {
    AgentID.ORCHESTRATOR: 8000,
    AgentID.SAP_ERP:      8001,
    AgentID.ORACLE_ERP:   8002,
    AgentID.SALESFORCE:   8003,
    AgentID.AWS_CLOUD:    8004,
    AgentID.GCP_CLOUD:    8005,
}

# Request envelope (MCP-compatible)
# {"id": "uuid", "method": "tools/call", "params": {"name": "...", "arguments": {...}}}
# Response envelope
# {"id": "uuid", "result": {...}, "error": null, "agent": "...", "latency_ms": N}


class AgentServer:
    """
    Base class – each agent subclasses this and provides `dispatch(tool, args)`.
    Runs a TCP server that accepts MCP-like JSON requests over persistent connections.
    """

    def __init__(
        self,
        agent_id: AgentID,
        dispatch_fn: Callable[[str, Dict[str, Any], Optional[str]], Any],
    ):
        self.agent_id   = agent_id
        self.dispatch   = dispatch_fn
        self.port       = AGENT_PORTS[agent_id]
        self._server    = None
        self._stop_event: asyncio.Event = asyncio.Event()
        self._active_connections: int = 0
        self._requests_served: int = 0
        self._started_at: Optional[datetime] = None

        PID_DIR.mkdir(exist_ok=True)
        LOG_DIR.mkdir(exist_ok=True)

        self.pid_file = PID_DIR / f"{agent_id.value}.pid"
        self.log_file = LOG_DIR / f"{agent_id.value}.log"

        # Attach a file handler so each agent logs to its own file
        fh = logging.FileHandler(self.log_file)
        fh.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)-8s %(message)s", "%Y-%m-%d %H:%M:%S"))
        logger.addHandler(fh)

    # ── PID management ────────────────────────────────────────────────────────
    def _write_pid(self) -> None:
        self.pid_file.write_text(str(os.getpid()))

    def _remove_pid(self) -> None:
        try:
            self.pid_file.unlink(missing_ok=True)
        except Exception:
            pass

    # ── Signal handlers ───────────────────────────────────────────────────────
    def _install_signal_handlers(self) -> None:
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, self._handle_stop_signal)

    def _handle_stop_signal(self) -> None:
        print(f"\n{YELLOW}[{self.agent_id.value}] Shutdown signal received – draining…{RESET}")
        logger.info(f"Shutdown signal received for {self.agent_id.value}")
        self._stop_event.set()

    # ── Connection handler ────────────────────────────────────────────────────
    async def _handle_connection(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        peer = writer.get_extra_info("peername")
        self._active_connections += 1
        logger.debug(f"Connection from {peer}")
        try:
            while not self._stop_event.is_set():
                try:
                    raw = await asyncio.wait_for(reader.readline(), timeout=120.0)
                except asyncio.TimeoutError:
                    continue
                if not raw:
                    break   # client disconnected

                # Parse request
                try:
                    req = json.loads(raw.decode().strip())
                except json.JSONDecodeError as e:
                    await self._send(writer, {"error": f"Invalid JSON: {e}", "id": None})
                    continue

                req_id  = req.get("id", str(uuid.uuid4()))
                method  = req.get("method", "")
                params  = req.get("params", {})

                # ── MCP: tools/list ──────────────────────────────────────────
                if method == "tools/list":
                    await self._send(writer, {
                        "id": req_id,
                        "result": {"tools": self._tool_list()},
                    })
                    continue

                # ── MCP: tools/call ──────────────────────────────────────────
                if method == "tools/call":
                    tool_name = params.get("name", "")
                    arguments = params.get("arguments", {})
                    trace_id  = params.get("trace_id")

                    t0 = time.perf_counter()
                    try:
                        result = await self.dispatch(tool_name, arguments, trace_id)
                        latency_ms = int((time.perf_counter() - t0) * 1000)
                        self._requests_served += 1
                        await self._send(writer, {
                            "id": req_id,
                            "result": {"content": [{"type": "text", "text": json.dumps(result)}]},
                            "agent": self.agent_id.value,
                            "latency_ms": latency_ms,
                            "error": None,
                        })
                    except Exception as exc:
                        await self._send(writer, {
                            "id": req_id,
                            "result": None,
                            "agent": self.agent_id.value,
                            "error": str(exc),
                        })
                    continue

                # ── HTTP-style: DELETE /stop  (remote stop) ──────────────────
                if method == "agent/stop":
                    await self._send(writer, {
                        "id": req_id,
                        "result": {"message": f"{self.agent_id.value} shutting down"},
                    })
                    self._stop_event.set()
                    break

                # ── agent/status ─────────────────────────────────────────────
                if method == "agent/status":
                    await self._send(writer, {
                        "id": req_id,
                        "result": self._status_payload(),
                    })
                    continue

                await self._send(writer, {
                    "id": req_id,
                    "error": f"Unknown method: {method}",
                })

        except (asyncio.IncompleteReadError, ConnectionResetError):
            pass
        finally:
            self._active_connections -= 1
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    async def _send(self, writer: asyncio.StreamWriter, payload: dict) -> None:
        try:
            writer.write((json.dumps(payload) + "\n").encode())
            await writer.drain()
        except Exception:
            pass

    # ── Tool metadata (for tools/list) ────────────────────────────────────────
    def _tool_list(self) -> list:
        """Override in subclass to return richer tool schema."""
        return []

    def _status_payload(self) -> dict:
        uptime = (datetime.utcnow() - self._started_at).total_seconds() if self._started_at else 0
        return {
            "agent":             self.agent_id.value,
            "status":            "RUNNING",
            "port":              self.port,
            "pid":               os.getpid(),
            "uptime_seconds":    int(uptime),
            "active_connections": self._active_connections,
            "requests_served":   self._requests_served,
            "started_at":        self._started_at.isoformat() if self._started_at else None,
        }

    # ── Main run loop ─────────────────────────────────────────────────────────
    async def run_forever(self) -> None:
        """Start the TCP server and run until stop signal."""
        self._started_at = datetime.utcnow()
        self._install_signal_handlers()
        self._write_pid()

        self._server = await asyncio.start_server(
            self._handle_connection, host="127.0.0.1", port=self.port
        )

        log_event(self.agent_id, f"Agent server STARTED",
                  {"port": self.port, "pid": os.getpid()})
        print(
            f"{GREEN}{BOLD}  ✔ {self.agent_id.value}{RESET}"
            f"  listening on port {CYAN}{self.port}{RESET}"
            f"  pid={os.getpid()}"
        )

        async with self._server:
            await self._stop_event.wait()   # ← blocks until stop signal

        # ── Graceful drain ────────────────────────────────────────────────────
        print(f"{YELLOW}  ⏳ {self.agent_id.value}: draining {self._active_connections} connection(s)…{RESET}")
        logger.info(f"Draining – active connections: {self._active_connections}")

        drain_deadline = time.monotonic() + 5.0
        while self._active_connections > 0 and time.monotonic() < drain_deadline:
            await asyncio.sleep(0.1)

        self._server.close()
        await self._server.wait_closed()
        self._remove_pid()

        print(
            f"{RED}  ✖ {self.agent_id.value} stopped"
            f"  (served {self._requests_served} requests){RESET}"
        )
        log_event(self.agent_id, "Agent server STOPPED",
                  {"requests_served": self._requests_served})

    def run(self) -> None:
        """Blocking entry point – call from __main__."""
        try:
            asyncio.run(self.run_forever())
        except KeyboardInterrupt:
            pass


# ── Convenience: send a single request to a running agent ─────────────────
async def send_request(
    agent_id: AgentID,
    method: str,
    params: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Send one MCP-style request to a running agent and return the response.
    Used by manage_agents.py for status checks and remote stop.
    """
    port = AGENT_PORTS[agent_id]
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection("127.0.0.1", port), timeout=3.0
        )
        req = json.dumps({"id": str(uuid.uuid4()), "method": method, "params": params})
        writer.write((req + "\n").encode())
        await writer.drain()
        raw = await asyncio.wait_for(reader.readline(), timeout=5.0)
        writer.close()
        await writer.wait_closed()
        return json.loads(raw.decode())
    except (ConnectionRefusedError, asyncio.TimeoutError, OSError):
        return {"error": f"Agent {agent_id.value} not reachable on port {port}"}
