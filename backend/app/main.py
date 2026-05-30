import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from dotenv import load_dotenv
from app.api.routes import predict, train, watchlist, ws, auth, metrics, health, stocks
from app.core.middleware import log_requests
from app.db.models import init_tables

load_dotenv()

def _get_origins() -> list[str]:
    # Dev-only CORS defaults. Keep production origins explicit via ALLOWED_ORIGINS.
    raw = os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:8888,http://127.0.0.1:8888,http://localhost:3000"
    )
    return [o.strip() for o in raw.split(",") if o.strip()]

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_tables()
    yield

app = FastAPI(title="StockSense AI", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_get_origins(),
    allow_credentials=False,  # Safer default for token-in-header local dev
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(BaseHTTPMiddleware, dispatch=log_requests)

@app.get("/")
def read_root():
    return {"status": "StockSense AI API is running"}

app.include_router(predict.router, prefix="/api")
app.include_router(train.router, prefix="/api")
app.include_router(stocks.router, prefix="/api")
app.include_router(watchlist.router, prefix="/api")
app.include_router(ws.router)
app.include_router(metrics.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(health.router)
