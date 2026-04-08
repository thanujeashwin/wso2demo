#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
# Morrisons WSO2 Agent Manager – Stop All Agents (graceful)
# ═══════════════════════════════════════════════════════════════
# Usage:
#   ./stop_agents.sh               # stop all 6 agents
#   ./stop_agents.sh sap oracle    # stop specific agents
#
# Sends SIGTERM to each agent; waits up to 6 s for clean exit.
# Falls back to SIGKILL if the drain timeout is exceeded.
# ═══════════════════════════════════════════════════════════════
set -e
cd "$(dirname "$0")"

python manage_agents.py stop "$@"
