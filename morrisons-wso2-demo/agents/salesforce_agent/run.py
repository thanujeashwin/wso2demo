"""Salesforce CRM Agent – Continuous Server Entry Point"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from shared.agent_server import AgentServer
from shared.models import AgentID
from agents.salesforce_agent.agent import salesforce_agent

TOOLS = [
    {"name": "get_customer_profile",        "description": "Look up Morrisons loyalty customer profile"},
    {"name": "generate_personalised_offer", "description": "Generate a targeted promotional offer"},
    {"name": "update_customer_segment",     "description": "Assign customer to a marketing segment"},
    {"name": "get_supplier_account",        "description": "Retrieve supplier account from Salesforce CRM"},
    {"name": "log_service_case",            "description": "Create a Salesforce Service Cloud case"},
]

class SalesforceAgentServer(AgentServer):
    def _tool_list(self): return TOOLS

server = SalesforceAgentServer(AgentID.SALESFORCE, salesforce_agent.handle_mcp_call)

if __name__ == "__main__":
    server.run()
