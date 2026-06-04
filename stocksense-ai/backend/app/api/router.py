from fastapi import APIRouter
from app.api.routes import predict, train, stocks, websocket, anomalies, sentiment, stream, health, briefing

api_router = APIRouter()
api_router.include_router(predict.router,    tags=["Predictions"])
api_router.include_router(train.router,      tags=["Training"])
api_router.include_router(stocks.router,     tags=["Stocks"])
api_router.include_router(websocket.router,  tags=["WebSocket"])
api_router.include_router(anomalies.router,  tags=["Anomalies"])
api_router.include_router(sentiment.router,  tags=["Sentiment"])
api_router.include_router(stream.router,     tags=["Stream"])
api_router.include_router(health.router,     tags=["Health"])
api_router.include_router(briefing.router,   tags=["Briefing"])
