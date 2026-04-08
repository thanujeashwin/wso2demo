"""Oracle ERP Agent – Continuous Server Entry Point"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from shared.agent_server import AgentServer
from shared.models import AgentID
from agents.oracle_agent.agent import oracle_agent

TOOLS = [
    {"name": "get_budget_availability",  "description": "Query Oracle GL for remaining budget"},
    {"name": "approve_purchase_order",   "description": "Submit PO to Oracle AME for approval"},
    {"name": "get_cost_centre_report",   "description": "Retrieve spend report for a cost centre"},
    {"name": "get_invoice_status",       "description": "Check Oracle AP invoice payment status"},
    {"name": "create_journal_entry",     "description": "Post a journal entry to Oracle GL"},
]

class OracleAgentServer(AgentServer):
    def _tool_list(self): return TOOLS

server = OracleAgentServer(AgentID.ORACLE_ERP, oracle_agent.handle_mcp_call)

if __name__ == "__main__":
    server.run()
