#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
# Morrisons WSO2 Agent Manager – Start All Agents
# ═══════════════════════════════════════════════════════════════
# Usage:
#   ./start_agents.sh              # start all 6 agents
#   ./start_agents.sh sap oracle   # start specific agents
# ═══════════════════════════════════════════════════════════════
set -e
cd "$(dirname "$0")"

python manage_agents.py start "$@"
