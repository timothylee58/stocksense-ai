from fastapi import APIRouter
from app.core.cache import get_redis
from app.db.models import db

router = APIRouter()

@router.get("/health")
def health_check():
    checks = {}

    # Redis
    r = get_redis()
    checks["redis"] = "ok" if r is not None else "unavailable"

    # Database
    try:
        db.connect(reuse_if_open=True)
        db.execute_sql("SELECT 1")
        checks["db"] = "ok"
    except Exception as e:
        checks["db"] = f"error: {str(e)}"

    overall = "healthy" if all(v == "ok" for v in checks.values()) else "degraded"
    return {"status": overall, "checks": checks}
