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

import random
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from shared.http_server import HTTPAgentServer
from shared.models import AgentID
from shared.observability import log_event, increment
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


# ── Demo AWS service health state ─────────────────────────────────────────────
_LAMBDA_FUNCTIONS = [
    "morrisons-stock-reorder",
    "morrisons-po-approval-router",
    "morrisons-customer-offer-trigger",
    "morrisons-waste-reporting",
]
_REDSHIFT_QUEUE_DEPTH = {"n": 3}


# ── Periodic: AWS infrastructure health check ─────────────────────────────────
async def aws_periodic_infra_health() -> None:
    """
    Periodically report Lambda concurrency, Redshift queue depth, and SNS
    throughput to WSO2 Choreo Observability.
    In production this polls CloudWatch Metrics API.
    """
    tracer = trace.get_tracer(AgentID.AWS_CLOUD.value)

    with tracer.start_as_current_span(
        f"{AgentID.AWS_CLOUD.value}/infra_health",
        kind=trace.SpanKind.INTERNAL,
        attributes={
            "agent.id":        AgentID.AWS_CLOUD.value,
            "agent.operation": "infra_health",
            "aws.region":      os.environ.get("AWS_REGION", "eu-west-1"),
            "aws.account":     os.environ.get("AWS_SNS_ACCOUNT_ID", "123456789012"),
        },
    ) as span:
        # Simulate Lambda concurrency metrics
        total_invocations = 0
        for fn in _LAMBDA_FUNCTIONS:
            concurrency = random.randint(0, 8)
            errors      = random.randint(0, 1)
            invocations = random.randint(5, 40)
            total_invocations += invocations
            span.add_event(
                "lambda_metrics",
                attributes={
                    "function":    fn,
                    "concurrency": str(concurrency),
                    "errors_1m":   str(errors),
                    "invocations": str(invocations),
                },
            )
            if errors > 0:
                increment("aws.lambda_errors")

        # Simulate Redshift queue depth
        _REDSHIFT_QUEUE_DEPTH["n"] = random.randint(0, 12)
        span.add_event(
            "redshift_queue",
            attributes={"queued_queries": str(_REDSHIFT_QUEUE_DEPTH["n"])},
        )

        # Simulate DynamoDB active sessions (online grocery)
        active_sessions = random.randint(1200, 4800)
        span.add_event(
            "dynamodb_sessions",
            attributes={"active_basket_sessions": str(active_sessions)},
        )
        span.set_attribute("aws.total_lambda_invocations_30s", total_invocations)
        span.set_attribute("aws.active_sessions", active_sessions)

        log_event(AgentID.AWS_CLOUD, "AWS infra health check",
                  {"lambda_fns": len(_LAMBDA_FUNCTIONS),
                   "redshift_queue": _REDSHIFT_QUEUE_DEPTH["n"],
                   "active_sessions": active_sessions})
        increment("aws.health_checks")
        span.set_status(Status(StatusCode.OK))


server = HTTPAgentServer(
    agent_id=AgentID.AWS_CLOUD,
    dispatch_fn=aws_agent.handle_mcp_call,
    tools_meta=TOOLS,
    periodic_callbacks=[aws_periodic_infra_health],
    heartbeat_interval=30,
)

if __name__ == "__main__":
    server.run()
