"""WSO2 Agent Manager Start Command: python main.py | Port: 8005"""
from app import app
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8005)
