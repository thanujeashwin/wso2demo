"""
WSO2 Agent Manager entry point – Oracle ERP Agent
Port is read from the PORT environment variable (set by Agent Manager).
Falls back to 8002 for local development.
"""
import os
from app import app

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8002))
    uvicorn.run(app, host="0.0.0.0", port=port)
