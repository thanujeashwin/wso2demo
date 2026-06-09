"""
Morrisons Orchestrator Agent – LangChain Tools
===============================================
Each tool delegates to a specialist sub-agent by calling its /chat endpoint.
This enables genuine multi-agent orchestration: the orchestrator reasons about
which specialist to call and in what order, then combines results.

Sub-agent URLs are configured via environment variables injected by WSO2 Agent Manager:
  SAP_AGENT_URL        (default: http://localhost:8001)
  ORACLE_AGENT_URL     (default: http://localhost:8002)
  SALESFORCE_AGENT_URL (default: http://localhost:8003)
  AWS_AGENT_URL        (default: http://localhost:8004)
  GCP_AGENT_URL        (default: http://localhost:8005)
"""
import logging
import requests
from langchain_core.tools import tool
from config import settings

logger = logging.getLogger(__name__)

TIMEOUT = 30  # seconds per sub-agent call


def _call_agent(url: str, name: str, message: str, session_id: str) -> str:
    """POST to a sub-agent's /chat endpoint and return its text response."""
    try:
        resp = requests.post(
            f"{url}/chat",
            json={"message": message, "session_id": session_id, "context": {}},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json().get("response", "(no response)")
    except requests.exceptions.ConnectionError:
        return f"[{name}] Connection error – is the agent running at {url}?"
    except requests.exceptions.Timeout:
        return f"[{name}] Request timed out after {TIMEOUT}s"
    except Exception as exc:
        logger.exception("Error calling %s agent", name)
        return f"[{name}] Error: {exc}"


@tool
def ask_sap_erp_agent(question: str, session_id: str = "orchestrator") -> str:
    """
    Delegate a question or task to the Morrisons SAP ERP specialist agent.
    Use for: stock level checks, purchase orders, supplier information,
    goods movements, and demand forecasting via SAP S/4HANA.

    Examples:
    - "What is the stock level for SKU-BEEF-001?"
    - "Raise a PO for 200 units of SKU-SALM-004 from SUP-004"
    - "Get the 90-day demand forecast for SKU-CHIC-002"

    Args:
        question: The question or instruction for the SAP ERP agent
        session_id: Session ID for conversation continuity (default: orchestrator)
    """
    return _call_agent(settings.sap_agent_url, "SAP ERP", question, session_id)


@tool
def ask_oracle_erp_agent(question: str, session_id: str = "orchestrator") -> str:
    """
    Delegate a question or task to the Morrisons Oracle ERP financial agent.
    Use for: budget availability, purchase order approvals (AME), cost centre reports,
    invoice status, and General Ledger journal entries.

    Examples:
    - "Check budget availability for CC-FISH-003"
    - "Approve PO-004502 for £3,500 against CC-FRESH-001"
    - "Get the MTD spend report for CC-BAKERY-02"

    Args:
        question: The question or instruction for the Oracle ERP agent
        session_id: Session ID for conversation continuity
    """
    return _call_agent(settings.oracle_agent_url, "Oracle ERP", question, session_id)


@tool
def ask_salesforce_agent(question: str, session_id: str = "orchestrator") -> str:
    """
    Delegate a question or task to the Morrisons Salesforce CRM agent.
    Use for: loyalty customer profiles, personalised offer generation,
    customer segment updates, supplier account health, and service case logging.

    Examples:
    - "Get the profile for customer CUST-000303"
    - "Generate a personalised offer for CUST-002847 via app"
    - "Log a service case for CUST-001122 about a missing delivery"

    Args:
        question: The question or instruction for the Salesforce CRM agent
        session_id: Session ID for conversation continuity
    """
    return _call_agent(settings.salesforce_agent_url, "Salesforce", question, session_id)


@tool
def ask_aws_agent(question: str, session_id: str = "orchestrator") -> str:
    """
    Delegate a question or task to the Morrisons AWS Cloud agent.
    Use for: sales trend analysis (Redshift), Lambda workflow triggers,
    S3 analytics reports, SNS notifications, and DynamoDB online basket data.

    Examples:
    - "Analyse sales trends for SKU-BEEF-001 over the last 8 weeks"
    - "Trigger the morrisons-stock-reorder Lambda workflow"
    - "Send an SNS alert to morrisons-stock-alerts about low salmon stock"

    Args:
        question: The question or instruction for the AWS Cloud agent
        session_id: Session ID for conversation continuity
    """
    return _call_agent(settings.aws_agent_url, "AWS", question, session_id)


@tool
def ask_gcp_agent(question: str, session_id: str = "orchestrator") -> str:
    """
    Delegate a question or task to the Morrisons GCP Cloud agent.
    Use for: BigQuery analytics, Vertex AI ML predictions (demand forecast,
    churn, shelf vision, price elasticity), IoT sensor readings,
    Pub/Sub event publishing, and Document AI invoice parsing.

    Examples:
    - "Run the top_selling_skus BigQuery query"
    - "Get a demand forecast from Vertex AI for SKU-BEEF-001"
    - "Check the temperature reading for STORE-001-FRIDGE-12"
    - "Publish a LOW_STOCK_ALERT event to morrisons-stock-events"

    Args:
        question: The question or instruction for the GCP Cloud agent
        session_id: Session ID for conversation continuity
    """
    return _call_agent(settings.gcp_agent_url, "GCP", question, session_id)


TOOLS = [
    ask_sap_erp_agent,
    ask_oracle_erp_agent,
    ask_salesforce_agent,
    ask_aws_agent,
    ask_gcp_agent,
]
