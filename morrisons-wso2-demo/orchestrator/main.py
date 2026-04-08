"""
WSO2 Agent Manager Start Command: python main.py
WSO2 Agent Manager Port:         8000
WSO2 Agent Manager Base Path:    /

Environment variables to configure sub-agent URLs (set in Agent Manager):
  SAP_AGENT_URL        = http://<sap-agent-host>:8001
  ORACLE_AGENT_URL     = http://<oracle-agent-host>:8002
  SALESFORCE_AGENT_URL = http://<salesforce-agent-host>:8003
  AWS_AGENT_URL        = http://<aws-agent-host>:8004
  GCP_AGENT_URL        = http://<gcp-agent-host>:8005
"""
from app import app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
