import json
import redis.asyncio as aioredis
from app.core.config import get_settings

_pool: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    global _pool
    if _pool is None:
        settings = get_settings()
        _pool = aioredis.from_url(settings.redis_url, decode_responses=True)
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


async def cache_delete(key: str) -> None:
    try:
        r = get_redis()
        await r.delete(key)
    except Exception:
        pass


async def cache_set_typed(key: str, value: dict | list | float | int, ttl: int) -> None:
    """Cache any JSON-serializable value with TTL."""
    try:
        r = get_redis()
        import json
        await r.setex(key, ttl, json.dumps(value))
    except Exception:
        pass


async def cache_get_raw(key: str) -> str | None:
    """Get raw string value from cache (no JSON parsing)."""
    try:
        r = get_redis()
        return await r.get(key)
    except Exception:
        return None
