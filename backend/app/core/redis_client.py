import json
import os

import redis.asyncio as aioredis

_pool: aioredis.Redis | None = None


def _redis_url() -> str:
    return os.getenv("REDIS_URL", "redis://localhost:6379")


def get_redis() -> aioredis.Redis:
    global _pool
    if _pool is None:
        _pool = aioredis.from_url(_redis_url(), decode_responses=True)
    return _pool


async def cache_get(key: str) -> dict | None:
    try:
        r = get_redis()
        val = await r.get(key)
        return json.loads(val) if val else None
    except Exception:
        return None


async def cache_set(key: str, value: dict, ttl: int) -> None:
    try:
        r = get_redis()
        await r.setex(key, ttl, json.dumps(value))
    except Exception:
        pass
