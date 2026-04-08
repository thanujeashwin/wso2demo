"""
WSO2 Agent Manager Start Command: python main.py
WSO2 Agent Manager Port:         8001
WSO2 Agent Manager Base Path:    /
WSO2 OpenAPI Spec Path:          /openapi.yaml  (or use the file openapi.yaml)
"""
from app import app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
