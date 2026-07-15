"""
Singleton ClickHouse client.
Returns None gracefully when ClickHouse is unavailable so callers
can fall back to yfinance / Redis without crashing.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_client = None          # cached after first successful connect
_unavailable = False    # set True only after a failed attempt


def get_ch_client():
    global _client, _unavailable
    if _client is not None:
        return _client
    if _unavailable:
        return None
    try:
        import clickhouse_connect
        from app.core.config import get_settings

        s = get_settings()
        if not s.clickhouse_enabled:
            _unavailable = True
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
        logger.warning("ClickHouse unavailable — falling back to yfinance/Redis: %s", exc)
        _unavailable = True
        return None


def reset_ch_client() -> None:
    """Force reconnect on next call — useful after a ClickHouse restart."""
    global _client, _unavailable
    _client = None
    _unavailable = False
