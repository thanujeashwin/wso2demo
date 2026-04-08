"""AWS Cloud Agent – Continuous Server Entry Point"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from shared.agent_server import AgentServer
from shared.models import AgentID
from agents.aws_agent.agent import aws_agent

TOOLS = [
    {"name": "analyse_sales_trends",    "description": "Run ML query on Amazon Redshift"},
    {"name": "trigger_lambda_workflow", "description": "Invoke an AWS Lambda Step Functions workflow"},
    {"name": "get_s3_report",           "description": "Retrieve a pre-generated report from S3"},
    {"name": "send_sns_notification",   "description": "Publish a notification to AWS SNS"},
    {"name": "query_dynamodb_session",  "description": "Look up real-time basket data in DynamoDB"},
]

class AWSAgentServer(AgentServer):
    def _tool_list(self): return TOOLS

server = AWSAgentServer(AgentID.AWS_CLOUD, aws_agent.handle_mcp_call)

if __name__ == "__main__":
    server.run()
