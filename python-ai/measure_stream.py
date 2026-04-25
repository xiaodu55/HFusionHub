import asyncio
import time

import httpx

TOKEN = "***REMOVED-BY-REWRITE***"


async def measure(url, body):
    start = time.monotonic()
    headers = {"X-Internal-Token": TOKEN, "X-Tenant-Id": "1"}
    first_content_at = None
    done_at = None
    n = 0
    async with httpx.AsyncClient(timeout=180) as client:
        async with client.stream("POST", url, json=body, headers=headers) as resp:
            hs = time.monotonic() - start
            print(f"[{url.split('/')[-1]}] status={resp.status_code} headers_at={hs:.1f}s")
            async for line in resp.aiter_lines():
                if not line:
                    continue
                if '"content"' in line and first_content_at is None:
                    first_content_at = time.monotonic() - start
                    print(f"  first content at {first_content_at:.1f}s")
                if '"content"' in line:
                    n += 1
                if "[DONE]" in line:
                    done_at = time.monotonic() - start
                    print(f"  [DONE] at {done_at:.1f}s")
    print(f"  chunks={n} total={time.monotonic() - start:.1f}s")


async def main():
    v1 = {
        "message": "什么是虚拟线程？",
        "knowledge_base_id": 52,
        "user_id": 1,
        "style": "detailed",
        "history": [],
        "max_tool_steps": 5,
    }
    await measure("http://127.0.0.1:9000/api/agent/v1/chat/stream", v1)


asyncio.run(main())
