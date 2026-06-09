"""
WSO2 Agent Manager entry point — Sap Agent
Chat Agent type always routes to port 8001 inside the container.
PORT env var is respected if set; defaults to 8001.
"""
import os
from app import app

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8001))
    uvicorn.run(app, host="0.0.0.0", port=port)
