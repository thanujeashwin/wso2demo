"""
AWS Cloud Agent – WSO2 Agent Manager Entry Point
─────────────────────────────────────────────────
WSO2 Start Command:  python main.py
WSO2 Port:           8004
WSO2 OpenAPI Path:   /openapi.json
WSO2 Base Path:      /
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from shared.http_server import HTTPAgentServer
from shared.models import AgentID
from agents.aws_agent.agent import aws_agent

TOOLS = [
    {
        "name": "analyse_sales_trends",
        "description": "Run analytics query on Amazon Redshift (Morrisons data warehouse) and return trend data with forecasts.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "sku":              {"type": "string"},
                "weeks":            {"type": "integer", "default": 8, "maximum": 52},
                "include_forecast": {"type": "boolean", "default": True},
            },
            "required": ["sku"],
        },
    },
    {
        "name": "trigger_lambda_workflow",
        "description": "Invoke an AWS Lambda / Step Functions workflow by name.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workflow_name": {"type": "string", "description": "Lambda function suffix (e.g. stock-reorder)"},
                "payload":       {"type": "object"},
                "async_invoke":  {"type": "boolean", "default": True},
            },
            "required": ["workflow_name"],
        },
    },
    {
        "name": "get_s3_report",
        "description": "Retrieve a pre-generated analytics report from Amazon S3 with a presigned URL.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "report_name":           {"type": "string",
                                          "enum": ["weekly-sales", "margin-analysis",
                                                   "waste-report", "online-conversion"]},
                "generate_presigned_url": {"type": "boolean", "default": True},
            },
            "required": ["report_name"],
        },
    },
    {
        "name": "send_sns_notification",
        "description": "Publish a notification to an Amazon SNS topic (email, SMS, or app push).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "topic":      {"type": "string",
                               "enum": ["morrisons-stock-alerts", "morrisons-po-approvals",
                                        "morrisons-ops-critical"]},
                "subject":    {"type": "string"},
                "message":    {"type": "string"},
                "recipients": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["topic", "subject", "message"],
        },
    },
    {
        "name": "query_dynamodb_session",
        "description": "Look up real-time online basket/session data in Amazon DynamoDB.",
        "inputSchema": {
            "type": "object",
            "properties": {"session_id": {"type": "string"}},
            "required": ["session_id"],
        },
    },
]

server = HTTPAgentServer(
    agent_id=AgentID.AWS_CLOUD,
    dispatch_fn=aws_agent.handle_mcp_call,
    tools_meta=TOOLS,
)

if __name__ == "__main__":
    server.run()
