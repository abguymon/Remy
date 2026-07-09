from kroger_mcp.server import create_server

if __name__ == "__main__":
    mcp = create_server()
    # Explicitly run with SSE transport for Docker
    mcp.run(transport="sse", host="0.0.0.0", port=8000)
