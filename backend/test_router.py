import asyncio
from app.ai_gateway.router import route_task

async def main():
    route = await route_task("Describe the image")
    print(f"Routed to: {route}")

if __name__ == "__main__":
    asyncio.run(main())
