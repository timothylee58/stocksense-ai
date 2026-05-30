import os
import json
import pickle
import redis
import pandas as pd
from typing import Optional

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

_client: Optional[redis.Redis] = None

def get_redis() -> Optional[redis.Redis]:
    """Return Redis client, or None if Redis is unavailable."""
    global _client
    if _client is None:
        try:
            _client = redis.from_url(REDIS_URL, decode_responses=False, socket_connect_timeout=2)
            _client.ping()
        except Exception:
            _client = None
    return _client

def cache_get_df(key: str) -> Optional[pd.DataFrame]:
    r = get_redis()
    if r is None:
        return None
    try:
        raw = r.get(key)
        if raw:
            return pickle.loads(raw)
    except Exception:
        pass
    return None

def cache_set_df(key: str, df: pd.DataFrame, ttl: int) -> None:
    r = get_redis()
    if r is None:
        return
    try:
        r.setex(key, ttl, pickle.dumps(df))
    except Exception:
        pass

def cache_get_json(key: str) -> Optional[dict]:
    r = get_redis()
    if r is None:
        return None
    try:
        raw = r.get(key)
        if raw:
            return json.loads(raw)
    except Exception:
        pass
    return None

def cache_set_json(key: str, data: dict, ttl: int) -> None:
    r = get_redis()
    if r is None:
        return
    try:
        r.setex(key, ttl, json.dumps(data))
    except Exception:
        pass
