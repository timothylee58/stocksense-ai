#!/usr/bin/env python
"""
CLI training script: python train.py --ticker NVDA
Runs all 3 stages and logs to MLflow.
"""
import argparse
import asyncio
import logging
import sys
import os

# Add backend root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def train_all_stages(ticker: str, days: int = 365) -> None:
    from app.data.fetcher import fetch_stock_data
    from app.services.isolation_forest import train_isolation_forest
    from app.services.xgboost_service import train_xgboost
    from app.services.mlflow_service import log_training_run
    from sklearn.metrics import roc_auc_score, accuracy_score

    logger.info("=== Training pipeline for %s ===", ticker)

    df = await fetch_stock_data(ticker, period_years=max(2, days // 365))
    logger.info("Fetched %d rows for %s", len(df), ticker)

    # Stage 1: Isolation Forest
    logger.info("Stage 1: Training Isolation Forest...")
    if_model, if_scaler = train_isolation_forest(df, ticker)
    logger.info("Isolation Forest trained")

    # Stage 2: XGBoost
    logger.info("Stage 2: Training XGBoost...")
    from app.services.isolation_forest import predict_anomalies
    df_with_anomaly = predict_anomalies(df, ticker)
    xgb_model = train_xgboost(df_with_anomaly, ticker)
    logger.info("XGBoost trained")

    # Evaluate on last 20% of data
    from app.services.feature_service import build_feature_matrix, build_target_series
    X = build_feature_matrix(df_with_anomaly, include_anomaly=True).iloc[:-1]
    y = build_target_series(df_with_anomaly).iloc[:-1]
    n_eval = max(20, len(X) // 5)
    X_eval, y_eval = X.values[-n_eval:], y.values[-n_eval:]
    proba = xgb_model.predict_proba(X_eval)
    y_pred = (proba[:, 1] >= 0.5).astype(int)
    dir_acc = accuracy_score(y_eval, y_pred)
    roc_auc = roc_auc_score(y_eval, proba[:, 1]) if len(set(y_eval)) > 1 else 0.5
    logger.info("XGBoost eval — Directional Accuracy: %.3f, ROC-AUC: %.3f", dir_acc, roc_auc)

    # Log to MLflow
    run_id = log_training_run(
        ticker=ticker,
        params={
            "if_contamination": 0.08,
            "xgb_n_estimators": 500,
            "train_rows": len(X),
            "eval_rows": n_eval,
        },
        metrics={
            "directional_accuracy": dir_acc,
            "roc_auc": roc_auc,
        },
    )
    logger.info("MLflow run_id: %s", run_id)
    logger.info("=== Training complete for %s ===", ticker)


def main():
    parser = argparse.ArgumentParser(description="Train StockSense AI models")
    parser.add_argument("--ticker", required=True, help="Stock ticker, e.g. NVDA")
    parser.add_argument("--days", type=int, default=365, help="Training period in days")
    args = parser.parse_args()
    asyncio.run(train_all_stages(args.ticker.upper(), args.days))


if __name__ == "__main__":
    main()
