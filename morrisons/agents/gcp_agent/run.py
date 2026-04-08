"""GCP Cloud Agent – Continuous Server Entry Point"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from shared.agent_server import AgentServer
from shared.models import AgentID
from agents.gcp_agent.agent import gcp_agent

TOOLS = [
    {"name": "run_bigquery_analytics",    "description": "Run analytics on Google BigQuery"},
    {"name": "call_vertex_ai_prediction", "description": "Run ML inference via Vertex AI"},
    {"name": "publish_pubsub_event",      "description": "Publish a real-time event to Pub/Sub"},
    {"name": "get_store_iot_data",        "description": "Retrieve IoT sensor data from stores"},
    {"name": "run_document_ai",           "description": "Parse supplier invoices via Document AI"},
]

class GCPAgentServer(AgentServer):
    def _tool_list(self): return TOOLS

server = GCPAgentServer(AgentID.GCP_CLOUD, gcp_agent.handle_mcp_call)

if __name__ == "__main__":
    server.run()
