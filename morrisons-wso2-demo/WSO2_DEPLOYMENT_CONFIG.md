# WSO2 Agent Manager – Deployment Configuration Reference
## Morrisons Demo Agents

Use this as your copy-paste guide for the **"Create a Platform-Hosted Agent"** form.
Deploy each agent separately. Start with the 5 sub-agents, then deploy the Orchestrator last.

---

## Form Field Guide (applies to ALL agents)

| Form Field | Selection / Value | Notes |
|---|---|---|
| **Build** | `Python` | Not Docker |
| **Language Version** | `3.11` | |
| **Start Command** | `python main.py` | Entry point in each agent folder |
| **Enable auto instrumentation** | ✅ Checked | Enables OTEL tracing to WSO2 Choreo |
| **Agent Type** | `Custom API Agent` | Not Chat Agent |
| **OpenAPI Spec Path** | `/openapi.json` | Auto-served at runtime by each agent |
| **Base Path** | `/` | |

---

## Agent 1 – SAP ERP Agent

| Field | Value |
|---|---|
| **Name** | `morrisons-sap-erp-agent` |
| **Description** | `SAP S/4HANA ERP agent – stock levels, purchase orders, supplier master, demand forecasting (5 tools)` |
| **GitHub Repository** | `https://github.com/<your-org>/morrisons-wso2-demo` |
| **Branch** | `main` |
| **Project Path** | `/agents/sap_agent` |
| **Start Command** | `python main.py` |
| **Language Version** | `3.11` |
| **Agent Type** | `Custom API Agent` |
| **OpenAPI Spec Path** | `/openapi.json` |
| **Port** | `8001` |
| **Base Path** | `/` |
| **Enable auto instrumentation** | ✅ |

**Environment Variables:**
| Key | Value | Secret? |
|---|---|---|
| `SAP_BASE_URL` | `https://s4hana.morrisons.internal/sap/opu/odata/sap` | No |
| `SAP_OAUTH_CLIENT_ID` | `mcp-sap-client` | No |
| `SAP_OAUTH_CLIENT_SECRET` | `<from AWS Secrets Manager>` | ✅ Yes |
| `WSO2_TOKEN_URL` | `https://wso2-apim.morrisons.internal/token` | No |
| `LOG_LEVEL` | `INFO` | No |

---

## Agent 2 – Oracle ERP Agent

| Field | Value |
|---|---|
| **Name** | `morrisons-oracle-erp-agent` |
| **Description** | `Oracle Fusion Financials agent – budget checks, PO approvals (AME), GL journals, AP (5 tools)` |
| **GitHub Repository** | `https://github.com/<your-org>/morrisons-wso2-demo` |
| **Branch** | `main` |
| **Project Path** | `/agents/oracle_agent` |
| **Start Command** | `python main.py` |
| **Language Version** | `3.11` |
| **Agent Type** | `Custom API Agent` |
| **OpenAPI Spec Path** | `/openapi.json` |
| **Port** | `8002` |
| **Base Path** | `/` |
| **Enable auto instrumentation** | ✅ |

**Environment Variables:**
| Key | Value | Secret? |
|---|---|---|
| `ORACLE_BASE_URL` | `https://oracle-erp.morrisons.internal/fscmRestApi/resources/11.13.18.05` | No |
| `ORACLE_IDCS_CLIENT_ID` | `mcp-oracle-client` | No |
| `ORACLE_IDCS_CLIENT_SECRET` | `<from Oracle Vault>` | ✅ Yes |
| `ORACLE_TOKEN_URL` | `https://idcs.oracle.morrisons.internal/oauth2/v1/token` | No |
| `LOG_LEVEL` | `INFO` | No |

---

## Agent 3 – Salesforce CRM Agent

| Field | Value |
|---|---|
| **Name** | `morrisons-salesforce-agent` |
| **Description** | `Salesforce CRM + Marketing Cloud agent – loyalty profiles, offers, segments, supplier accounts (5 tools)` |
| **GitHub Repository** | `https://github.com/<your-org>/morrisons-wso2-demo` |
| **Branch** | `main` |
| **Project Path** | `/agents/salesforce_agent` |
| **Start Command** | `python main.py` |
| **Language Version** | `3.11` |
| **Agent Type** | `Custom API Agent` |
| **OpenAPI Spec Path** | `/openapi.json` |
| **Port** | `8003` |
| **Base Path** | `/` |
| **Enable auto instrumentation** | ✅ |

**Environment Variables:**
| Key | Value | Secret? |
|---|---|---|
| `SF_INSTANCE_URL` | `https://morrisons.my.salesforce.com` | No |
| `SF_CLIENT_ID` | `<Salesforce Connected App Client ID>` | No |
| `SF_CLIENT_SECRET` | `<Salesforce Connected App Secret>` | ✅ Yes |
| `SF_TOKEN_URL` | `https://login.salesforce.com/services/oauth2/token` | No |
| `LOG_LEVEL` | `INFO` | No |

---

## Agent 4 – AWS Cloud Agent

| Field | Value |
|---|---|
| **Name** | `morrisons-aws-cloud-agent` |
| **Description** | `AWS cloud agent – Redshift analytics, Lambda workflows, S3 reports, SNS notifications, DynamoDB (5 tools)` |
| **GitHub Repository** | `https://github.com/<your-org>/morrisons-wso2-demo` |
| **Branch** | `main` |
| **Project Path** | `/agents/aws_agent` |
| **Start Command** | `python main.py` |
| **Language Version** | `3.11` |
| **Agent Type** | `Custom API Agent` |
| **OpenAPI Spec Path** | `/openapi.json` |
| **Port** | `8004` |
| **Base Path** | `/` |
| **Enable auto instrumentation** | ✅ |

**Environment Variables:**
| Key | Value | Secret? |
|---|---|---|
| `AWS_REGION` | `eu-west-1` | No |
| `AWS_REDSHIFT_CLUSTER` | `morrisons-analytics.eu-west-1.redshift.amazonaws.com` | No |
| `AWS_SNS_ACCOUNT_ID` | `123456789012` | No |
| `AWS_ROLE_ARN` | `arn:aws:iam::123456789012:role/morrisons-mcp-lambda-role` | No |
| `LOG_LEVEL` | `INFO` | No |

> **Note:** No `AWS_ACCESS_KEY_ID` / `SECRET` needed. WSO2 data plane on GCP uses AWS Workload Identity Federation via the IAM Role ARN above.

---

## Agent 5 – GCP Cloud Agent

| Field | Value |
|---|---|
| **Name** | `morrisons-gcp-cloud-agent` |
| **Description** | `GCP cloud agent – BigQuery analytics, Vertex AI predictions, Pub/Sub events, IoT sensor data, Document AI (5 tools)` |
| **GitHub Repository** | `https://github.com/<your-org>/morrisons-wso2-demo` |
| **Branch** | `main` |
| **Project Path** | `/agents/gcp_agent` |
| **Start Command** | `python main.py` |
| **Language Version** | `3.11` |
| **Agent Type** | `Custom API Agent` |
| **OpenAPI Spec Path** | `/openapi.json` |
| **Port** | `8005` |
| **Base Path** | `/` |
| **Enable auto instrumentation** | ✅ |

**Environment Variables:**
| Key | Value | Secret? |
|---|---|---|
| `GCP_PROJECT` | `morrisons-data-platform` | No |
| `GCP_REGION` | `europe-west2` | No |
| `GCP_WI_PROVIDER` | `//iam.googleapis.com/projects/.../workloadIdentityPools/wso2-pool/providers/wso2-provider` | No |
| `GCP_SERVICE_ACCOUNT` | `wso2-agent@morrisons-data-platform.iam.gserviceaccount.com` | No |
| `LOG_LEVEL` | `INFO` | No |

> **Note:** No GCP service account key JSON needed. Uses Workload Identity Federation — the GCP_WI_PROVIDER is the audience WSO2 Choreo presents when calling GCP APIs.

---

## Agent 6 – Orchestrator (deploy LAST)

| Field | Value |
|---|---|
| **Name** | `morrisons-orchestrator` |
| **Description** | `Master orchestrator – supply chain, store ops, customer personalisation, and P2P finance workflows across all 5 sub-agents` |
| **GitHub Repository** | `https://github.com/<your-org>/morrisons-wso2-demo` |
| **Branch** | `main` |
| **Project Path** | `/agents/orchestrator` |
| **Start Command** | `python main.py` |
| **Language Version** | `3.11` |
| **Agent Type** | `Custom API Agent` |
| **OpenAPI Spec Path** | `/openapi.json` |
| **Port** | `8000` |
| **Base Path** | `/` |
| **Enable auto instrumentation** | ✅ |

**Environment Variables:**
| Key | Value | Secret? |
|---|---|---|
| `DEFAULT_MODEL` | `claude-sonnet-4-6` | No |
| `ANTHROPIC_API_KEY` | `<your Anthropic key>` | ✅ Yes |
| `SAP_AGENT_URL` | `http://morrisons-sap-erp-agent:8001` | No |
| `ORACLE_AGENT_URL` | `http://morrisons-oracle-erp-agent:8002` | No |
| `SF_AGENT_URL` | `http://morrisons-salesforce-agent:8003` | No |
| `AWS_AGENT_URL` | `http://morrisons-aws-cloud-agent:8004` | No |
| `GCP_AGENT_URL` | `http://morrisons-gcp-cloud-agent:8005` | No |
| `LOG_LEVEL` | `INFO` | No |

---

## Quick Validation After Each Deployment

Once an agent is deployed, test it with these WSO2 console or `curl` commands:

```bash
# Replace <agent-url> with the URL WSO2 Agent Manager assigns

# Liveness probe (WSO2 uses this automatically)
curl <agent-url>/health
# → {"status": "UP", "agent": "morrisons-sap-erp-agent"}

# List tools
curl <agent-url>/tools
# → {"tools": [...]}

# View OpenAPI spec (paste into Swagger UI for a visual view)
curl <agent-url>/openapi.json

# Call a tool
curl -X POST <agent-url>/tools/check_stock_level \
  -H "Content-Type: application/json" \
  -d '{"sku": "SKU-BEEF-001", "store_id": "STORE-001"}'
```

---

## Deployment Order & Why It Matters

```
1. sap           (no dependencies)
2. oracle        (no dependencies)
3. salesforce    (no dependencies)
4. aws           (no dependencies)
5. gcp           (no dependencies)
6. orchestrator  ← deploy LAST (calls all 5 above)
```

The orchestrator's `*_AGENT_URL` env vars must point to the internal
service names WSO2 assigns to each deployed agent.

---

## Repository Structure WSO2 Expects

```
morrisons-wso2-demo/            ← GitHub repo root
├── requirements.txt            ← WSO2 installs this automatically
├── shared/                     ← imported by all agents
│   ├── models.py
│   ├── observability.py
│   └── http_server.py
├── guardrails/
│   └── guardrails.py
└── agents/
    ├── sap_agent/
    │   ├── main.py             ← WSO2 "Start Command: python main.py"
    │   └── agent.py
    ├── oracle_agent/
    │   ├── main.py
    │   └── agent.py
    ├── salesforce_agent/
    │   ├── main.py
    │   └── agent.py
    ├── aws_agent/
    │   ├── main.py
    │   └── agent.py
    ├── gcp_agent/
    │   ├── main.py
    │   └── agent.py
    └── orchestrator/
        ├── main.py
        └── agent.py
```

> **Project Path** in the WSO2 form should be set to the agent subfolder
> (e.g. `/agents/sap_agent`) so WSO2 sets the working directory correctly
> and `python main.py` picks up the right entry point.
