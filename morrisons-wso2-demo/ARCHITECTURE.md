# Morrisons × WSO2 Agent Manager – Architecture Reference

## Where Does WSO2 Agent Manager SIT?

```
Internet / Internal Users
         │
         ▼
┌─────────────────────────────────────────────────────────────────────────┐
│              WSO2 Agent Manager Portal (Control Plane)                  │
│  • Single portal for all agents, models, workflows, guardrails          │
│  • Model selector: Claude / Gemini / GPT-4o / Amazon Nova / Mistral    │
│  • Observability dashboard (traces, metrics, logs)                       │
│  • RBAC, guardrail policies, audit log                                  │
│  Hosted on: WSO2 Choreo Cloud (EU region)                               │
└──────────────────────────┬──────────────────────────────────────────────┘
                           │ HTTPS + OAuth2
┌──────────────────────────▼──────────────────────────────────────────────┐
│           WSO2 API Manager (Gateway + ESB)  – Data Plane                │
│  • Routes MCP calls to the correct agent                                 │
│  • Enforces rate limits, TLS, OAuth2 token validation                   │
│  • Proxies SAP OData, Oracle REST, Salesforce REST APIs                 │
│  Hosted on: Morrisons GCP (europe-west2) – primary data plane           │
└──────┬──────────┬────────────────┬────────────┬────────────────────────┘
       │          │                │            │
  MCP/SSE    MCP/SSE           MCP/SSE      MCP/SSE
       │          │                │            │
┌──────▼──┐ ┌────▼──────┐ ┌──────▼──┐ ┌──────▼──────────────────┐
│  SAP    │ │  Oracle   │ │  AWS    │ │  GCP                    │
│ S/4HANA │ │  Fusion   │ │ Lambda  │ │  BigQuery  Vertex AI    │
│  (GCP)  │ │  (OCI)    │ │Redshift │ │  Pub/Sub   Cloud Run    │
│         │ │           │ │  SNS    │ │  Document AI  IoT       │
└─────────┘ └───────────┘ └─────────┘ └─────────────────────────┘
                                │
                       ┌────────▼────────┐
                       │   Salesforce    │
                       │  CRM + MktCloud │
                       │    (SaaS)       │
                       └─────────────────┘
```

## Cloud Footprint (Morrisons-specific)

| System | Cloud | Purpose |
|--------|-------|---------|
| SAP S/4HANA | GCP europe-west2 | Materials Mgmt, POs, Supplier master |
| Oracle Fusion Financials | OCI uk-london-1 | Finance, budgets, GL, AP |
| Salesforce | SaaS (Salesforce.com) | CRM, loyalty, marketing cloud |
| AWS | eu-west-1 | Online grocery, analytics (Redshift), SNS |
| GCP (data platform) | europe-west2 | BigQuery, Vertex AI, Pub/Sub, IoT |
| WSO2 Choreo (control plane) | eu-west-2 | Agent Manager portal |
| WSO2 data plane | GCP europe-west2 | API Gateway, ESB, MCP broker |

## Multi-Agent Orchestration Flow

```
User/System Request
       │
       ▼
Orchestrator Agent  ←──── Guardrail check (Layer 1: input)
       │
       ├─── classify domain → [supply_chain | store_ops | customer | finance]
       │
       ├─── plan sub-agent call sequence
       │
       ├─── PARALLEL dispatch (asyncio.gather) ─────────────────────┐
       │         │                    │                │             │
       │    SAP Agent          Oracle Agent     Salesforce     GCP Agent
       │    (stock/PO)        (budget/AME)      (CRM/offers)  (BQ/Vertex)
       │
       ├─── SEQUENTIAL calls when ordering matters (e.g. PO before approval)
       │
       ├─── Guardrail check (Layer 3: output sanitisation)
       │
       └─── Aggregated response + distributed trace
```

## MCP Protocol (How Agents Communicate)

All agent tool calls use **Model Context Protocol (MCP) 2025-03** over SSE:

```
WSO2 Agent Manager                         Sub-Agent
(MCP Client)                              (MCP Server)
      │                                        │
      │── POST /mcp/sap-erp ─────────────────▶│
      │   {                                    │
      │     "method": "tools/call",            │
      │     "params": {                        │
      │       "name": "check_stock_level",     │
      │       "arguments": {"sku":"SKU-001"}   │
      │     }                                  │
      │   }                                    │
      │                                        │── calls SAP OData API
      │◀── SSE stream: result chunks ──────────│
      │   {"content": [{"type":"text",         │
      │     "text": "{stock: 48, ...}"}]}      │
```

## Guardrails (3 Layers)

```
REQUEST ──▶ Layer 1 (Input) ──▶ Agent Call ──▶ Layer 3 (Output) ──▶ RESPONSE
              │                    │
              │              Layer 2 (Agent-level)
              │              • Rate limits
              │              • Value thresholds
              │              • Allowed/blocked patterns
              │
        Input checks:
        • Prompt injection detection
        • PII in request payload
        • Restricted SKU patterns
        • RBAC domain permissions
        • Suspicious quantities
        • Purchase value flags
```

## Observability Stack

```
Every agent operation emits:

  OTel Span ──────────────────▶ WSO2 Choreo Observability
                                 └── Grafana dashboard
                                 └── Jaeger trace viewer

  Structured JSON log ─────────▶ GCP Cloud Logging (SAP/GCP agents)
                                  AWS CloudWatch (AWS agent)
                                  OCI Logging (Oracle agent)
                                  Splunk (aggregated)

  Prometheus metrics ──────────▶ /metrics endpoint per agent
                                  └── calls, latency, errors per tool
```

## Quick Start

```bash
cd morrisons-wso2-demo
pip install pydantic

# Run all scenarios interactively
python demo/run_demo.py

# Run specific scenario
python demo/run_demo.py --scenario supply_chain
python demo/run_demo.py --scenario store_ops
python demo/run_demo.py --scenario customer
python demo/run_demo.py --scenario finance
python demo/run_demo.py --scenario guardrail
python demo/run_demo.py --scenario models
```

## File Structure

```
morrisons-wso2-demo/
├── shared/
│   ├── models.py              # Pydantic data models (all agents share these)
│   └── observability.py       # OTel tracing, metrics, health dashboard
├── agents/
│   ├── orchestrator/
│   │   └── agent.py           # Master orchestrator – all 4 workflow scenarios
│   ├── sap_agent/
│   │   ├── agent.py           # SAP S/4HANA MCP agent (5 tools)
│   │   └── config.yaml        # WSO2 registration + guardrails
│   ├── oracle_agent/
│   │   ├── agent.py           # Oracle Fusion Financials agent (5 tools)
│   │   └── config.yaml
│   ├── salesforce_agent/
│   │   ├── agent.py           # Salesforce CRM + Marketing Cloud (5 tools)
│   │   └── config.yaml
│   ├── aws_agent/
│   │   ├── agent.py           # AWS Lambda/Redshift/SNS/DynamoDB (5 tools)
│   │   └── config.yaml
│   └── gcp_agent/
│       ├── agent.py           # GCP BigQuery/Vertex/Pub/Sub/IoT (5 tools)
│       └── config.yaml
├── guardrails/
│   └── guardrails.py          # 3-layer guardrail engine
├── mcp/
│   └── mcp_servers.yaml       # MCP server registry (all 5 servers)
├── wso2/
│   └── agent_manager_config.yaml  # Full WSO2 Agent Manager topology
├── demo/
│   └── run_demo.py            # Interactive demo runner
└── ARCHITECTURE.md            # This file
```
