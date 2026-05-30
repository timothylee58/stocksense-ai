"""GET /health — health check with Redis + Supabase status."""
from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health_check():
    status = {"status": "ok", "version": "2.0.0", "services": {}}

    # Redis check
    try:
        from app.core.redis_client import cache_get
        await cache_get("__health__")
        status["services"]["redis"] = "ok"
    except Exception:
        status["services"]["redis"] = "unavailable"

    # Supabase check
    try:
        from app.core.database import get_supabase_client
        client = get_supabase_client()
        status["services"]["supabase"] = "ok" if client else "not_configured"
    except Exception:
        status["services"]["supabase"] = "error"

    return status
