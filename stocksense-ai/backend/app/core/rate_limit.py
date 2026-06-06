"""Simple sliding-window in-memory rate limiter middleware.

Limits each client IP to `calls` requests per `period` seconds.
Health/docs endpoints are exempt.

Usage in main.py:
    from app.core.rate_limit import RateLimitMiddleware
    app.add_middleware(RateLimitMiddleware, calls=60, period=60)
"""
from __future__ import annotations

import json
from collections import defaultdict
from time import time

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

_EXEMPT = {"/", "/health", "/docs", "/openapi.json", "/redoc"}


class RateLimitMiddleware(BaseHTTPMiddleware):
    """60 req/min per IP, sliding window, no external dependencies."""

    def __init__(self, app, calls: int = 60, period: int = 60):
        super().__init__(app)
        self.calls = calls
        self.period = period
        self._windows: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path in _EXEMPT:
            return await call_next(request)

        ip = request.client.host if request.client else "0.0.0.0"
        now = time()

        window = self._windows[ip]
        self._windows[ip] = [t for t in window if now - t < self.period]

        if len(self._windows[ip]) >= self.calls:
            return Response(
                content=json.dumps({"detail": f"Rate limit exceeded — max {self.calls} req/{self.period}s per IP"}),
                status_code=429,
                media_type="application/json",
            )

        self._windows[ip].append(now)
        return await call_next(request)
