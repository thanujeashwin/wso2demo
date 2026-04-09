"""
WSO2 Agent Manager entry point – Orchestrator
Port is read from the PORT environment variable (set by Agent Manager).
Falls back to 8000 for local development.

Sub-agent URLs are configured via environment variables:
  SAP_AGENT_URL        = http://<host>:<port>
  ORACLE_AGENT_URL     = http://<host>:<port>
  SALESFORCE_AGENT_URL = http://<host>:<port>
  AWS_AGENT_URL        = http://<host>:<port>
  GCP_AGENT_URL        = http://<host>:<port>
"""
import os
from app import app

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
