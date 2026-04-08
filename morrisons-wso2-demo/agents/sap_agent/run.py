"""
SAP ERP Agent – Continuous Server Entry Point
Run:  python agents/sap_agent/run.py
Stop: python manage_agents.py stop sap  (or Ctrl+C)
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from shared.agent_server import AgentServer
from shared.models import AgentID
from agents.sap_agent.agent import sap_agent

TOOLS = [
    {"name": "check_stock_level",    "description": "Query SAP MM for real-time stock level"},
    {"name": "raise_purchase_order", "description": "Create a Purchase Order in SAP MM"},
    {"name": "get_supplier_info",    "description": "Retrieve vendor master data from SAP BP"},
    {"name": "get_goods_movement",   "description": "Retrieve goods receipts/issues (MIGO)"},
    {"name": "run_demand_forecast",  "description": "Pull 90-day demand forecast from SAP IBP"},
]

class SAPAgentServer(AgentServer):
    def _tool_list(self): return TOOLS

server = SAPAgentServer(AgentID.SAP_ERP, sap_agent.handle_mcp_call)

if __name__ == "__main__":
    server.run()
