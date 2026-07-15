"""
Singleton ClickHouse client.
Returns None gracefully when ClickHouse is unavailable so callers
can fall back to yfinance / Redis without crashing.
Uses a 60-second cooldown after failure so the process can recover
automatically without blocking every request.
"""
from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)

_client = None          # cached after first successful connect
_unavailable_until = 0.0  # epoch time; 0 means "try now"


def get_ch_client():
    global _client, _unavailable_until
    if _client is not None:
        return _client
    now = time.time()
    if now < _unavailable_until:
        return None
    try:
        import clickhouse_connect
        from app.core.config import get_settings

        s = get_settings()
        if not s.clickhouse_enabled:
            _unavailable_until = float("inf")  # disabled in config — never retry
            return None

        _client = clickhouse_connect.get_client(
            host=s.clickhouse_host,
            port=s.clickhouse_port,
            username=s.clickhouse_user,
            password=s.clickhouse_password,
            database=s.clickhouse_db,
            compress=True,
            connect_timeout=5,
            send_receive_timeout=30,
        )
        _client.ping()
        logger.info("ClickHouse connected at %s:%s", s.clickhouse_host, s.clickhouse_port)
        return _client
    except Exception as exc:
        logger.warning("ClickHouse unavailable — retrying in 60s: %s", exc)
        _unavailable_until = time.time() + 60.0
        return None


def reset_ch_client() -> None:
    """Force reconnect on next call — useful after a ClickHouse restart."""
    global _client, _unavailable_until
    _client = None
    _unavailable_until = 0.0
