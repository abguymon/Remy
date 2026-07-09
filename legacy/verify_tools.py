import asyncio
from mcp.client.sse import sse_client
from mcp.client.session import ClientSession

async def check_server(name, url):
    print(f"Checking {name} at {url}...")
    try:
        async with sse_client(url) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                print(f"✅ {name} Tools found: {[t.name for t in tools.tools]}")
                return True
    except Exception as e:
        print(f"❌ {name} Failed: {e}")
        return False

async def main():
    results = await asyncio.gather(
        check_server("Mealie MCP", "http://localhost:8000/sse"),
        check_server("Kroger MCP", "http://localhost:8001/sse")
    )
    
    if all(results):
        print("\nAll MCP servers verified successfully!")
    else:
        print("\nSome MCP servers failed.")
        exit(1)

if __name__ == "__main__":
    asyncio.run(main())
