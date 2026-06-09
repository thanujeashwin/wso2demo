"""Morrisons AWS Cloud Agent – LangChain Tools"""
import random
from datetime import date, timedelta
from langchain_core.tools import tool

LAMBDA_WORKFLOWS = [
    "morrisons-stock-reorder",
    "morrisons-po-approval-router",
    "morrisons-customer-offer-trigger",
    "morrisons-waste-reporting",
    "morrisons-price-update",
]

S3_REPORTS = {
    "weekly-sales":      "s3://morrisons-analytics/reports/weekly-sales",
    "margin-analysis":   "s3://morrisons-analytics/reports/margin-analysis",
    "waste-report":      "s3://morrisons-analytics/reports/waste-report",
    "online-conversion": "s3://morrisons-analytics/reports/online-conversion",
}

SNS_TOPICS = {
    "morrisons-stock-alerts":  "arn:aws:sns:eu-west-1:123456789012:morrisons-stock-alerts",
    "morrisons-po-approvals":  "arn:aws:sns:eu-west-1:123456789012:morrisons-po-approvals",
    "morrisons-ops-critical":  "arn:aws:sns:eu-west-1:123456789012:morrisons-ops-critical",
}


@tool
def analyse_sales_trends(sku: str, weeks: int = 8, include_forecast: bool = True) -> str:
    """
    Run a sales trend query on Amazon Redshift (Morrisons data warehouse) for a product SKU.
    Returns weekly sales history and optional ML-based forecast.

    Args:
        sku: Product SKU, e.g. SKU-BEEF-001, SKU-MILK-003, SKU-SALM-004
        weeks: Number of historical weeks to analyse (default 8, max 52)
        include_forecast: Whether to include a 4-week forward forecast (default True)
    """
    weeks = min(weeks, 52)
    base_sales = random.randint(150, 400)
    history = []
    for i in range(weeks):
        wk_date = (date.today() - timedelta(weeks=weeks - i)).strftime("W%V-%Y")
        sales = max(0, base_sales + random.randint(-40, 50))
        history.append(f"  {wk_date}: {sales} units  £{sales * random.uniform(1.5, 8.5):.0f}")

    result = (
        f"Amazon Redshift – Sales Trend Analysis\n"
        f"SKU: {sku} | Period: {weeks} weeks | Region: EU-WEST-1\n"
        f"Weekly Sales:\n" + "\n".join(history[-4:]) + f"\n  ... ({weeks-4} earlier weeks)\n"
        f"Avg Weekly Sales: {base_sales} units"
    )
    if include_forecast:
        forecast = [
            f"  {(date.today() + timedelta(weeks=i+1)).strftime('W%V-%Y')}: "
            f"~{base_sales + random.randint(-20, 30)} units (SageMaker)"
            for i in range(4)
        ]
        result += "\n4-Week Forecast (SageMaker):\n" + "\n".join(forecast)
    return result


@tool
def trigger_lambda_workflow(workflow_name: str, payload: str = "{}") -> str:
    """
    Invoke an AWS Lambda / Step Functions workflow for Morrisons operations.
    Supports async and sync invocation modes.

    Args:
        workflow_name: Lambda workflow name – morrisons-stock-reorder, morrisons-po-approval-router,
                       morrisons-customer-offer-trigger, morrisons-waste-reporting, morrisons-price-update
        payload: JSON string payload to pass to the Lambda function (default: empty object)
    """
    if workflow_name not in LAMBDA_WORKFLOWS:
        return (
            f"Workflow '{workflow_name}' not found. "
            f"Available: {', '.join(LAMBDA_WORKFLOWS)}"
        )
    exec_id = f"exec-{random.randint(100000, 999999)}"
    duration_ms = random.randint(120, 2400)
    return (
        f"AWS Lambda – Workflow Triggered ✓\n"
        f"Workflow: {workflow_name}\n"
        f"Execution ID: {exec_id}\n"
        f"Status: SUCCEEDED | Duration: {duration_ms}ms\n"
        f"Region: eu-west-1 | Account: 123456789012"
    )


@tool
def get_s3_report(report_name: str) -> str:
    """
    Retrieve a pre-generated analytics report from Amazon S3 with a presigned URL.

    Args:
        report_name: Report name – weekly-sales, margin-analysis, waste-report, online-conversion
    """
    if report_name not in S3_REPORTS:
        return f"Report '{report_name}' not found. Available: {', '.join(S3_REPORTS)}"
    presigned_url = (
        f"https://morrisons-analytics.s3.eu-west-1.amazonaws.com/"
        f"reports/{report_name}/{date.today().isoformat()}.csv"
        f"?X-Amz-Expires=3600&X-Amz-Signature={random.randint(100000,999999)}"
    )
    size_mb = round(random.uniform(0.5, 12.0), 1)
    return (
        f"Amazon S3 – Report Available\n"
        f"Report: {report_name}\n"
        f"Path: {S3_REPORTS[report_name]}\n"
        f"Size: {size_mb} MB | Generated: {date.today().isoformat()}\n"
        f"Presigned URL (valid 1hr):\n{presigned_url}"
    )


@tool
def send_sns_notification(topic: str, subject: str, message: str) -> str:
    """
    Publish a notification to a Morrisons Amazon SNS topic (email, SMS, or app push).

    Args:
        topic: SNS topic name – morrisons-stock-alerts, morrisons-po-approvals, morrisons-ops-critical
        subject: Notification subject line
        message: Notification body text
    """
    if topic not in SNS_TOPICS:
        return f"Topic '{topic}' not found. Available: {', '.join(SNS_TOPICS)}"
    message_id = f"msg-{random.randint(10000000, 99999999)}"
    return (
        f"Amazon SNS – Notification Published ✓\n"
        f"Topic: {topic}\n"
        f"ARN: {SNS_TOPICS[topic]}\n"
        f"Subject: {subject}\n"
        f"Message ID: {message_id}\n"
        f"Subscribers Notified: {random.randint(3, 25)}"
    )


@tool
def query_dynamodb_session(session_id: str) -> str:
    """
    Look up real-time online basket/session data in Amazon DynamoDB (Morrisons.com).
    Returns current basket contents and session status.

    Args:
        session_id: Online session ID or customer basket ID
    """
    items = random.randint(0, 12)
    basket_value = round(random.uniform(0, 85.0), 2)
    status = random.choice(["ACTIVE", "ACTIVE", "ACTIVE", "ABANDONED", "CHECKED_OUT"])
    return (
        f"Amazon DynamoDB – Session Data\n"
        f"Session ID: {session_id}\n"
        f"Status: {status}\n"
        f"Basket Items: {items} | Basket Value: £{basket_value}\n"
        f"Last Activity: {random.randint(1, 15)} minutes ago\n"
        f"Channel: morrisons.com"
    )


TOOLS = [
    analyse_sales_trends,
    trigger_lambda_workflow,
    get_s3_report,
    send_sns_notification,
    query_dynamodb_session,
]
