import uvicorn
from src.server import mcp

# Expose app for Uvicorn
app = mcp.sse_app

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
