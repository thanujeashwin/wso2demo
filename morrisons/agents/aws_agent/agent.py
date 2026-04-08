"""
Morrisons AWS Cloud Agent
═════════════════════════
Registered in WSO2 Agent Manager as: morrisons-aws-cloud-agent

Capabilities:
  • analyse_sales_trends      – Run ML query on Redshift (sales data warehouse)
  • trigger_lambda_workflow   – Invoke an AWS Lambda orchestration function
  • get_s3_report             – Retrieve a pre-generated report from S3
  • send_sns_notification     – Publish a notification to SNS (email/SMS/app)
  • query_dynamodb_session    – Look up real-time session / basket data in DynamoDB

MCP Protocol:
  This agent exposes its tools via MCP over HTTP/SSE.
  AWS-side, the agent runs as a Lambda function fronted by API Gateway.
  WSO2 Agent Manager calls it via the MCP client connector.

Integration note for Morrisons:
  Morrisons runs AWS for:
    - Online grocery (Morrisons.com) – hosted on AWS
    - Data analytics (Redshift, S3 Data Lake)
    - Amazon Bedrock (backup LLM inference)
    - Contact centre (Amazon Connect)
"""
from __future__ import annotations

import asyncio
import json
import random
import uuid
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from shared.models import AgentID, AgentMessage, AgentResponse, AgentStatus
from shared.observability import log_event, trace_span, increment

# ── Demo data ─────────────────────────────────────────────────────────────────
MOCK_SALES_DATA: Dict[str, List[Dict[str, Any]]] = {
    "SKU-BEEF-001": [{"week": f"W{i}", "units": random.randint(1200, 2400),
                      "revenue": round(random.uniform(3000, 7000), 2)} for i in range(1, 9)],
    "SKU-MILK-003": [{"week": f"W{i}", "units": random.randint(4000, 8000),
                      "revenue": round(random.uniform(4000, 9000), 2)} for i in range(1, 9)],
    "SKU-BREA-007": [{"week": f"W{i}", "units": random.randint(2000, 5000),
                      "revenue": round(random.uniform(2000, 5500), 2)} for i in range(1, 9)],
}

MOCK_S3_REPORTS = {
    "weekly-sales":      "s3://morrisons-analytics/reports/weekly-sales-latest.parquet",
    "margin-analysis":   "s3://morrisons-analytics/reports/margin-analysis-Q4-2025.xlsx",
    "waste-report":      "s3://morrisons-analytics/reports/waste-by-store-MTD.csv",
    "online-conversion": "s3://morrisons-analytics/reports/online-conversion-daily.json",
}

MOCK_BASKETS: Dict[str, Dict[str, Any]] = {
    "SESSION-ABC123": {
        "customer_id": "CUST-000101", "items": 7, "subtotal": 42.85,
        "channel": "morrisons.com", "device": "mobile", "status": "active"
    },
    "SESSION-DEF456": {
        "customer_id": "CUST-000202", "items": 3, "subtotal": 18.50,
        "channel": "morrisons.com", "device": "desktop", "status": "checkout"
    },
}


class AWSCloudAgent:
    """
    WSO2 Agent Manager – AWS Cloud Agent
    Runs as Lambda + API Gateway, exposes tools via MCP over SSE.
    Uses Amazon Bedrock as fallback LLM inference engine.
    """

    agent_id = AgentID.AWS_CLOUD

    # ── Tool: analyse_sales_trends ────────────────────────────────────────────
    async def analyse_sales_trends(
        self,
        sku: str,
        weeks: int = 8,
        include_forecast: bool = True,
        trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        [MCP Tool] Run analytics query on Amazon Redshift (Morrisons data warehouse).

        AWS service: Amazon Redshift Serverless
        Underlying SQL: SELECT week, units_sold, revenue FROM fact_sales
                        WHERE sku = :sku ORDER BY week DESC LIMIT :weeks

        Lambda function: arn:aws:lambda:eu-west-1:123456789:function:morrisons-sales-analytics
        """
        with trace_span(self.agent_id, "analyse_sales_trends", trace_id=trace_id,
                        attributes={"sku": sku, "weeks": weeks}):
            log_event(self.agent_id, "Querying Redshift sales trends",
                      {"sku": sku, "weeks": weeks})
            await asyncio.sleep(0.45)   # Redshift query latency

            data = MOCK_SALES_DATA.get(sku, [
                {"week": f"W{i}", "units": random.randint(500, 1500),
                 "revenue": round(random.uniform(1000, 4000), 2)} for i in range(1, weeks + 1)
            ])[:weeks]

            total_units   = sum(d["units"] for d in data)
            total_revenue = sum(d["revenue"] for d in data)
            avg_units     = total_units // weeks
            trend         = "UP" if data[-1]["units"] > data[0]["units"] else "DOWN"

            result: Dict[str, Any] = {
                "sku": sku,
                "weeks_analysed": weeks,
                "weekly_data": data,
                "total_units": total_units,
                "total_revenue_gbp": round(total_revenue, 2),
                "avg_weekly_units": avg_units,
                "trend": trend,
                "redshift_query_id": f"QID-{uuid.uuid4().hex[:8].upper()}",
                "data_source": "Redshift Serverless – eu-west-1",
            }
            if include_forecast:
                forecast_units = int(avg_units * (1.05 if trend == "UP" else 0.97))
                result["next_week_forecast"] = {
                    "units": forecast_units,
                    "model": "Amazon Forecast (DeepAR+)",
                    "confidence_interval": [int(forecast_units * 0.88), int(forecast_units * 1.12)],
                }
            increment("aws.redshift_queries")
            return result

    # ── Tool: trigger_lambda_workflow ─────────────────────────────────────────
    async def trigger_lambda_workflow(
        self,
        workflow_name: str,
        payload: Dict[str, Any],
        async_invoke: bool = True,
        trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        [MCP Tool] Invoke an AWS Lambda Step Functions workflow.

        Lambda ARN pattern: arn:aws:lambda:eu-west-1:123456789:function:morrisons-{workflow_name}
        """
        with trace_span(self.agent_id, "trigger_lambda_workflow", trace_id=trace_id,
                        attributes={"workflow": workflow_name, "async": async_invoke}):
            log_event(self.agent_id, f"Triggering Lambda: {workflow_name}", payload)
            await asyncio.sleep(0.2 if async_invoke else 0.6)

            execution_id = f"EXEC-{uuid.uuid4().hex[:12].upper()}"
            increment("aws.lambda_invocations")
            return {
                "workflow_name": workflow_name,
                "execution_id": execution_id,
                "lambda_arn": f"arn:aws:lambda:eu-west-1:123456789012:function:morrisons-{workflow_name}",
                "invocation_type": "Event" if async_invoke else "RequestResponse",
                "status": "ACCEPTED" if async_invoke else "COMPLETED",
                "status_code": 202 if async_invoke else 200,
                "trace_id": trace_id,
                "aws_request_id": str(uuid.uuid4()),
                "input_payload": payload,
            }

    # ── Tool: get_s3_report ───────────────────────────────────────────────────
    async def get_s3_report(
        self,
        report_name: str,
        generate_presigned_url: bool = True,
        trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """[MCP Tool] Retrieve a pre-generated analytics report from Amazon S3."""
        with trace_span(self.agent_id, "get_s3_report", trace_id=trace_id,
                        attributes={"report_name": report_name}):
            await asyncio.sleep(0.15)
            s3_path = MOCK_S3_REPORTS.get(report_name)
            if not s3_path:
                available = list(MOCK_S3_REPORTS.keys())
                return {"error": f"Report '{report_name}' not found", "available_reports": available}
            increment("aws.s3_fetches")
            return {
                "report_name": report_name,
                "s3_path": s3_path,
                "presigned_url": f"https://morrisons-analytics.s3.eu-west-1.amazonaws.com/{report_name}?X-Amz-Expires=3600&...",
                "expires_in_seconds": 3600,
                "generated_at": (date.today() - timedelta(hours=2)).isoformat(),
                "size_mb": round(random.uniform(0.5, 15.0), 2),
            }

    # ── Tool: send_sns_notification ───────────────────────────────────────────
    async def send_sns_notification(
        self,
        topic: str,
        subject: str,
        message: str,
        recipients: Optional[List[str]] = None,
        trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        [MCP Tool] Publish a notification to an Amazon SNS topic.

        SNS topics used by Morrisons:
          arn:aws:sns:eu-west-1:123456789:morrisons-stock-alerts
          arn:aws:sns:eu-west-1:123456789:morrisons-po-approvals
          arn:aws:sns:eu-west-1:123456789:morrisons-ops-critical
        """
        with trace_span(self.agent_id, "send_sns_notification", trace_id=trace_id,
                        attributes={"topic": topic}):
            log_event(self.agent_id, f"SNS notification: {topic}", {"subject": subject})
            await asyncio.sleep(0.1)
            increment("aws.sns_messages")
            return {
                "topic": topic,
                "topic_arn": f"arn:aws:sns:eu-west-1:123456789012:{topic}",
                "message_id": str(uuid.uuid4()),
                "subject": subject,
                "status": "PUBLISHED",
                "recipients_notified": len(recipients) if recipients else "all_subscribers",
            }

    # ── Tool: query_dynamodb_session ──────────────────────────────────────────
    async def query_dynamodb_session(
        self,
        session_id: str,
        trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """[MCP Tool] Look up real-time online basket / session data in DynamoDB."""
        with trace_span(self.agent_id, "query_dynamodb_session", trace_id=trace_id,
                        attributes={"session_id": session_id}):
            await asyncio.sleep(0.05)   # DynamoDB is single-digit ms
            session = MOCK_BASKETS.get(session_id)
            if not session:
                return {"error": f"Session {session_id} not found in DynamoDB"}
            increment("aws.dynamodb_reads")
            return {
                **session,
                "session_id": session_id,
                "table": "morrisons-online-sessions",
                "region": "eu-west-1",
                "ttl": 3600,
            }

    # ── MCP dispatch ──────────────────────────────────────────────────────────
    async def handle_mcp_call(
        self, tool_name: str, arguments: Dict[str, Any], trace_id: Optional[str] = None
    ) -> Dict[str, Any]:
        tools = {
            "analyse_sales_trends":    self.analyse_sales_trends,
            "trigger_lambda_workflow": self.trigger_lambda_workflow,
            "get_s3_report":           self.get_s3_report,
            "send_sns_notification":   self.send_sns_notification,
            "query_dynamodb_session":  self.query_dynamodb_session,
        }
        if tool_name not in tools:
            return {"error": f"Unknown tool: {tool_name}"}
        return await tools[tool_name](**arguments, trace_id=trace_id)

    async def process_message(self, msg: AgentMessage) -> AgentResponse:
        tid = msg.trace_context.get("trace_id", str(uuid.uuid4()).replace("-", ""))
        log_event(self.agent_id, f"Received task from {msg.from_agent.value}", msg.payload)
        try:
            result = await self.handle_mcp_call(
                msg.payload.get("tool"), msg.payload.get("args", {}), trace_id=tid
            )
            return AgentResponse(
                message_id=str(uuid.uuid4()), correlation_id=msg.correlation_id,
                from_agent=self.agent_id, status=AgentStatus.COMPLETED, data=result,
            )
        except Exception as exc:
            return AgentResponse(
                message_id=str(uuid.uuid4()), correlation_id=msg.correlation_id,
                from_agent=self.agent_id, status=AgentStatus.FAILED, data={}, error=str(exc),
            )


aws_agent = AWSCloudAgent()
