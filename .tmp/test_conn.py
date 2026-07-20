import asyncio
import subprocess
import time
import httpx

API_DIR = r"E:\3\novel-workbench\apps\api"
DATA_DIR = r"E:\3\novel-workbench\data"
PYTHON = r"E:\3\novel-workbench\apps\api\venv\Scripts\python.exe"
BASE_URL = "http://127.0.0.1:8766"


def start_server():
    env = {**dict(subprocess.os.environ), "DATA_DIR": DATA_DIR, "PYTHONPATH": API_DIR}
    return subprocess.Popen(
        [PYTHON, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8766"],
        cwd=API_DIR, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )


async def main():
    proc = start_server()
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            for _ in range(20):
                try:
                    r = await client.get(f"{BASE_URL}/api/health", timeout=2)
                    if r.status_code == 200:
                        break
                except Exception:
                    pass
                await asyncio.sleep(0.5)

            r = await client.post(f"{BASE_URL}/api/providers/1fdf6268-7d82-4b2c-8c0c-41cf8e9d9b0b/test")
            print("opencode:", r.json())

            r = await client.post(f"{BASE_URL}/api/providers/34c14b6b-7231-432a-96b2-8272329b828d/test")
            print("DeepSeek:", r.json())
    finally:
        proc.terminate()
        proc.wait(timeout=5)


asyncio.run(main())
