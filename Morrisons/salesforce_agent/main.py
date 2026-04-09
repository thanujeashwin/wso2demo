"""
WSO2 Agent Manager entry point — Salesforce Agent
Chat Agent type always routes to port 8000 inside the container.
PORT env var is respected if set; defaults to 8000.
"""
import os
from app import app

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
