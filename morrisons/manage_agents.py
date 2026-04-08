#!/usr/bin/env python3
"""
WSO2 Agent Manager – Agent Supervisor CLI
═══════════════════════════════════════════
Manages all Morrisons demo agents as background processes.

Usage
─────
  python manage_agents.py start              # start all 6 agents
  python manage_agents.py start sap oracle   # start specific agents
  python manage_agents.py stop               # stop all agents (graceful)
  python manage_agents.py stop sap           # stop one agent
  python manage_agents.py restart            # restart all
  python manage_agents.py restart gcp        # restart one
  python manage_agents.py status             # show live status table
  python manage_agents.py logs sap           # tail agent log
  python manage_agents.py logs sap --lines 50
  python manage_agents.py call sap check_stock_level '{"sku":"SKU-BEEF-001"}'

Agent names (short aliases)
────────────────────────────
  orchestrator  →  morrisons-orchestrator       port 8000
  sap           →  morrisons-sap-erp-agent      port 8001
  oracle        →  morrisons-oracle-erp-agent   port 8002
  salesforce    →  morrisons-salesforce-agent   port 8003
  aws           →  morrisons-aws-cloud-agent    port 8004
  gcp           →  morrisons-gcp-cloud-agent    port 8005
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

# ── Project root on path ──────────────────────────────────────────────────────
ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(ROOT))

from shared.agent_server import AGENT_PORTS, PID_DIR, LOG_DIR, send_request
from shared.models import AgentID
from shared.observability import (
    BOLD, RESET, GREEN, RED, YELLOW, CYAN, MAGENTA, BLUE,
)

# ── Agent alias → module path + AgentID ──────────────────────────────────────
AGENTS: Dict[str, Dict] = {
    "orchestrator": {"id": AgentID.ORCHESTRATOR, "module": "agents.orchestrator.run"},
    "sap":          {"id": AgentID.SAP_ERP,       "module": "agents.sap_agent.run"},
    "oracle":       {"id": AgentID.ORACLE_ERP,    "module": "agents.oracle_agent.run"},
    "salesforce":   {"id": AgentID.SALESFORCE,    "module": "agents.salesforce_agent.run"},
    "aws":          {"id": AgentID.AWS_CLOUD,     "module": "agents.aws_agent.run"},
    "gcp":          {"id": AgentID.GCP_CLOUD,     "module": "agents.gcp_agent.run"},
}

# Start order – sub-agents first, orchestrator last
START_ORDER  = ["sap", "oracle", "salesforce", "aws", "gcp", "orchestrator"]
# Stop order  – orchestrator first so it drains before backends go away
STOP_ORDER   = ["orchestrator", "gcp", "aws", "salesforce", "oracle", "sap"]


# ── PID helpers ───────────────────────────────────────────────────────────────
def _pid_file(alias: str) -> Path:
    agent_id = AGENTS[alias]["id"]
    return PID_DIR / f"{agent_id.value}.pid"


def _read_pid(alias: str) -> Optional[int]:
    pf = _pid_file(alias)
    if pf.exists():
        try:
            return int(pf.read_text().strip())
        except ValueError:
            return None
    return None


def _is_running(alias: str) -> bool:
    pid = _read_pid(alias)
    if pid is None:
        return False
    try:
        os.kill(pid, 0)   # probe – raises if process dead
        return True
    except ProcessLookupError:
        # Process is gone – try to clean up PID file (may be owned by subprocess)
        try:
            _pid_file(alias).unlink(missing_ok=True)
        except PermissionError:
            pass
        return False
    except PermissionError:
        # Process exists but owned by another user – treat as running
        return True


# ── Port helpers ─────────────────────────────────────────────────────────────
def _port(alias: str) -> int:
    return AGENT_PORTS[AGENTS[alias]["id"]]


# ── Display helpers ───────────────────────────────────────────────────────────
def _colour_status(running: bool) -> str:
    return f"{GREEN}● RUNNING{RESET}" if running else f"{RED}○ STOPPED{RESET}"


def _banner(text: str) -> None:
    print(f"\n{BOLD}{CYAN}{'═' * 60}{RESET}")
    print(f"{BOLD}{CYAN}  {text}{RESET}")
    print(f"{BOLD}{CYAN}{'═' * 60}{RESET}\n")


# ════════════════════════════════════════════════════════════════════════════
# COMMANDS
# ════════════════════════════════════════════════════════════════════════════

def cmd_start(aliases: List[str]) -> None:
    """Start agents as background subprocesses."""
    _banner("WSO2 Agent Manager – Starting Agents")
    ordered = [a for a in START_ORDER if a in aliases]

    for alias in ordered:
        if _is_running(alias):
            pid = _read_pid(alias)
            print(f"  {YELLOW}⚠  {alias:<14}{RESET} already running  (pid={pid})")
            continue

        module = AGENTS[alias]["module"]
        log_path = LOG_DIR / f"{AGENTS[alias]['id'].value}.log"
        LOG_DIR.mkdir(exist_ok=True)

        with open(log_path, "a") as log_fh:
            proc = subprocess.Popen(
                [sys.executable, "-m", module],
                cwd=str(ROOT),
                stdout=log_fh,
                stderr=log_fh,
                start_new_session=True,   # detach from this terminal
            )

        # Wait up to 3 s for the PID file to appear (agent startup)
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            if _is_running(alias):
                break
            time.sleep(0.1)

        if _is_running(alias):
            print(f"  {GREEN}✔  {alias:<14}{RESET}  port={_port(alias)}  pid={_read_pid(alias)}")
        else:
            print(f"  {RED}✗  {alias:<14}{RESET}  failed to start – check logs/{AGENTS[alias]['id'].value}.log")

    print()


def cmd_stop(aliases: List[str]) -> None:
    """Send SIGTERM to agents and wait for them to exit."""
    _banner("WSO2 Agent Manager – Stopping Agents")
    ordered = [a for a in STOP_ORDER if a in aliases]

    for alias in ordered:
        if not _is_running(alias):
            print(f"  {YELLOW}⚠  {alias:<14}{RESET} not running")
            continue

        pid = _read_pid(alias)
        try:
            os.kill(pid, signal.SIGTERM)
            print(f"  {YELLOW}⏳ {alias:<14}{RESET}  sent SIGTERM to pid={pid} …", end="", flush=True)
        except ProcessLookupError:
            print(f"  {RED}✗  {alias:<14}{RESET}  process {pid} already gone")
            _pid_file(alias).unlink(missing_ok=True)
            continue

        # Wait up to 6 s for graceful exit
        deadline = time.monotonic() + 6.0
        while time.monotonic() < deadline:
            if not _is_running(alias):
                break
            time.sleep(0.2)

        if not _is_running(alias):
            print(f"\r  {RED}✖  {alias:<14}{RESET}  stopped  (pid={pid} exited)          ")
        else:
            # Force kill
            print(f"\n  {RED}⚡  {alias:<14}{RESET}  graceful timeout – sending SIGKILL")
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                _pid_file(alias).unlink(missing_ok=True)
            except PermissionError:
                pass

    print()


def cmd_restart(aliases: List[str]) -> None:
    cmd_stop(aliases)
    time.sleep(0.5)
    cmd_start(aliases)


def cmd_status(aliases: List[str]) -> None:
    """Print a live status table with uptime and request counts."""
    _banner("WSO2 Agent Manager – Agent Status")

    col_w = [18, 8, 7, 7, 10, 8]
    header = (
        f"  {'AGENT':<{col_w[0]}} {'STATUS':<{col_w[1]+10}} "
        f"{'PORT':>{col_w[2]}} {'PID':>{col_w[3]}} "
        f"{'REQUESTS':>{col_w[4]}} {'UPTIME':>{col_w[5]}}"
    )
    print(f"{BOLD}{header}{RESET}")
    print("  " + "─" * 70)

    async def _fetch_all():
        results = {}
        for alias in START_ORDER:
            if alias not in aliases:
                continue
            agent_id = AGENTS[alias]["id"]
            if _is_running(alias):
                resp = await send_request(agent_id, "agent/status", {})
                results[alias] = resp.get("result", {})
            else:
                results[alias] = None
        return results

    live = asyncio.run(_fetch_all())

    for alias in START_ORDER:
        if alias not in aliases:
            continue
        data     = live.get(alias)
        running  = data is not None and "error" not in data
        pid      = data.get("pid", _read_pid(alias) or "-") if running else _read_pid(alias) or "-"
        port     = _port(alias)
        reqs     = data.get("requests_served", "-") if running else "-"
        uptime   = data.get("uptime_seconds", 0) if running else 0
        uptime_s = f"{uptime//3600:02d}h{(uptime%3600)//60:02d}m" if running else "-"
        status   = _colour_status(running)

        print(
            f"  {alias:<{col_w[0]}} {status:<{col_w[1]+10+9}} "   # +ANSI escape len
            f"{port:>{col_w[2]}} {str(pid):>{col_w[3]}} "
            f"{str(reqs):>{col_w[4]}} {uptime_s:>{col_w[5]}}"
        )

    print()


def cmd_logs(alias: str, lines: int = 30) -> None:
    """Tail the log file for an agent."""
    if alias not in AGENTS:
        print(f"{RED}Unknown agent: {alias}{RESET}")
        return
    log_path = LOG_DIR / f"{AGENTS[alias]['id'].value}.log"
    if not log_path.exists():
        print(f"{YELLOW}No log file yet for {alias}{RESET}")
        return
    print(f"{BOLD}  ── {alias} log (last {lines} lines) ──{RESET}")
    all_lines = log_path.read_text().splitlines()
    for line in all_lines[-lines:]:
        print(f"  {line}")
    print()


def cmd_call(alias: str, tool: str, args_json: str) -> None:
    """Send a single tool call to a running agent and print the response."""
    if alias not in AGENTS:
        print(f"{RED}Unknown agent: {alias}{RESET}")
        return
    try:
        arguments = json.loads(args_json) if args_json else {}
    except json.JSONDecodeError as e:
        print(f"{RED}Invalid JSON arguments: {e}{RESET}")
        return

    agent_id = AGENTS[alias]["id"]
    print(f"{CYAN}  → Calling {alias}:{tool} …{RESET}")

    async def _call():
        return await send_request(agent_id, "tools/call",
                                  {"name": tool, "arguments": arguments})
    result = asyncio.run(_call())
    print(json.dumps(result, indent=2))


# ════════════════════════════════════════════════════════════════════════════
# CLI ENTRY POINT
# ════════════════════════════════════════════════════════════════════════════

def _resolve_aliases(args_agents: List[str]) -> List[str]:
    """Return list of valid alias names; empty input = all agents."""
    if not args_agents:
        return list(AGENTS.keys())
    resolved = []
    for a in args_agents:
        if a in AGENTS:
            resolved.append(a)
        else:
            print(f"{YELLOW}Unknown agent alias '{a}' – skipping{RESET}")
    return resolved


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="manage_agents",
        description="Morrisons WSO2 Agent Manager – supervisor CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python manage_agents.py start                           # start all
  python manage_agents.py start sap oracle               # start subset
  python manage_agents.py stop                           # stop all (graceful)
  python manage_agents.py stop sap                       # stop one
  python manage_agents.py restart gcp                    # restart one
  python manage_agents.py status                         # live status table
  python manage_agents.py logs sap                       # last 30 log lines
  python manage_agents.py logs gcp --lines 100           # custom line count
  python manage_agents.py call sap check_stock_level '{"sku":"SKU-BEEF-001"}'
        """,
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    # start
    p_start = sub.add_parser("start",   help="Start one or more agents (default: all)")
    p_start.add_argument("agents", nargs="*", help="Agent aliases (omit for all)")

    # stop
    p_stop  = sub.add_parser("stop",    help="Gracefully stop one or more agents (default: all)")
    p_stop.add_argument("agents", nargs="*")

    # restart
    p_rst   = sub.add_parser("restart", help="Restart one or more agents")
    p_rst.add_argument("agents", nargs="*")

    # status
    p_stat  = sub.add_parser("status",  help="Show live status of all agents")
    p_stat.add_argument("agents", nargs="*")

    # logs
    p_logs  = sub.add_parser("logs",    help="Tail an agent's log file")
    p_logs.add_argument("agent",  help="Agent alias")
    p_logs.add_argument("--lines", type=int, default=30)

    # call
    p_call  = sub.add_parser("call",    help="Send a tool call to a running agent")
    p_call.add_argument("agent",     help="Agent alias")
    p_call.add_argument("tool",      help="Tool name")
    p_call.add_argument("arguments", nargs="?", default="{}", help="JSON arguments")

    args = parser.parse_args()

    if args.command == "start":
        cmd_start(_resolve_aliases(args.agents))

    elif args.command == "stop":
        cmd_stop(_resolve_aliases(args.agents))

    elif args.command == "restart":
        cmd_restart(_resolve_aliases(args.agents))

    elif args.command == "status":
        cmd_status(_resolve_aliases(getattr(args, "agents", [])))

    elif args.command == "logs":
        cmd_logs(args.agent, args.lines)

    elif args.command == "call":
        cmd_call(args.agent, args.tool, args.arguments)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
