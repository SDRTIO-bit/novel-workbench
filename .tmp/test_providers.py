import asyncio
import httpx

BASE_URL = "http://127.0.0.1:8766"

async def main():
    async with httpx.AsyncClient(timeout=30) as client:
        # Test opencode
        r = await client.post(f"{BASE_URL}/api/providers/1fdf6268-7d82-4b2c-8c0c-41cf8e9d9b0b/test")
        print("opencode:", r.json())
        # Test DeepSeek
        r = await client.post(f"{BASE_URL}/api/providers/34c14b6b-7231-432a-96b2-8272329b828d/test")
        print("DeepSeek:", r.json())

asyncio.run(main())
