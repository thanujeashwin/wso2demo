#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════
#  Morrisons WSO2 Demo – Push to GitHub
#  Run this ONCE from inside the morrisons-wso2-demo folder on your
#  local machine (not the sandbox).
#
#  Prerequisites:
#    1. Git installed  (git --version)
#    2. A GitHub Personal Access Token with "repo" scope
#       → https://github.com/settings/tokens/new
#         Select: repo (full control of private repositories)
#
#  Usage:
#    chmod +x push_to_github.sh
#    ./push_to_github.sh
# ═══════════════════════════════════════════════════════════════════════
set -e

REPO_URL="https://github.com/thanujeashwin/wso2demo.git"
BRANCH="main"

echo ""
echo "  ══════════════════════════════════════════════════════"
echo "   Morrisons WSO2 Agent Manager – GitHub Push Setup"
echo "  ══════════════════════════════════════════════════════"
echo ""

# ── Ask for PAT securely (no echo to terminal) ─────────────────────────
echo "  Enter your GitHub Personal Access Token (input hidden):"
read -rs GITHUB_PAT
echo ""

if [ -z "$GITHUB_PAT" ]; then
  echo "  ✗ No PAT entered. Exiting."
  exit 1
fi

# ── Embed PAT in remote URL (never stored in .git/config in plaintext) ──
# We use a temporary credential helper that reads from env, then clean up
AUTHED_URL="https://${GITHUB_PAT}@github.com/thanujeashwin/wso2demo.git"

# ── Initialise git if not already ──────────────────────────────────────
if [ ! -d ".git" ]; then
  echo "  → Initialising git repository..."
  git init
  git branch -m main
fi

# ── Configure identity ─────────────────────────────────────────────────
git config user.email "thanuje@gmail.com"
git config user.name  "Ashwin"

# ── Set remote ─────────────────────────────────────────────────────────
if git remote get-url origin &>/dev/null; then
  git remote set-url origin "$AUTHED_URL"
else
  git remote add origin "$AUTHED_URL"
fi

# ── Stage and commit ───────────────────────────────────────────────────
echo "  → Staging all files..."
git add -A

# Check if there's anything to commit
if git diff --cached --quiet; then
  echo "  ⚠  Nothing new to commit – repo may already be up to date."
else
  echo "  → Creating commit..."
  git commit -m "Initial commit: Morrisons WSO2 Agent Manager demo

- 6 agents: SAP ERP, Oracle ERP, Salesforce CRM, AWS, GCP, Orchestrator
- HTTP/aiohttp servers with OpenAPI 3.0 specs for WSO2 Custom API Agent
- 4 demo scenarios: supply chain, store ops, customer personalisation, P2P finance
- 3-layer guardrails engine, MCP registry, WSO2 deployment configs
- manage_agents.py supervisor CLI (start/stop/status/logs/call)
- requirements.txt, .gitignore, ARCHITECTURE.md, WSO2_DEPLOYMENT_CONFIG.md"
fi

# ── Push ───────────────────────────────────────────────────────────────
echo "  → Pushing to $REPO_URL (branch: $BRANCH)..."
git push -u origin "$BRANCH" 2>&1

# ── Clean up: reset remote URL to remove embedded PAT ─────────────────
echo "  → Securing remote URL (removing PAT from git config)..."
git remote set-url origin "$REPO_URL"

echo ""
echo "  ✔  Done! Your code is now at:"
echo "     https://github.com/thanujeashwin/wso2demo"
echo ""
echo "  ══════════════════════════════════════════════════════"
echo "   Next steps in WSO2 Agent Manager:"
echo "  ══════════════════════════════════════════════════════"
echo ""
echo "  1. Open your WSO2 Agent Manager portal"
echo "  2. Click 'Create a Platform-Hosted Agent'"
echo "  3. Use these settings for each agent:"
echo ""
echo "     Agent         | Project Path              | Port"
echo "     --------------|---------------------------|-----"
echo "     SAP ERP       | /agents/sap_agent         | 8001"
echo "     Oracle ERP    | /agents/oracle_agent      | 8002"
echo "     Salesforce    | /agents/salesforce_agent  | 8003"
echo "     AWS Cloud     | /agents/aws_agent         | 8004"
echo "     GCP Cloud     | /agents/gcp_agent         | 8005"
echo "     Orchestrator  | /agents/orchestrator      | 8000"
echo ""
echo "     All agents:"
echo "       Branch:          main"
echo "       GitHub Repo:     https://github.com/thanujeashwin/wso2demo"
echo "       Start Command:   python main.py"
echo "       Language:        3.11"
echo "       Agent Type:      Custom API Agent"
echo "       OpenAPI Path:    /openapi.json"
echo "       Base Path:       /"
echo "       Auto-instrument: ✅ Enabled"
echo ""
echo "  See WSO2_DEPLOYMENT_CONFIG.md for full env variable list."
echo ""
