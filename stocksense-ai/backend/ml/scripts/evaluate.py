#!/usr/bin/env python
"""
Evaluation script: backtest the 3-stage pipeline.
python evaluate.py --ticker NVDA
"""
import argparse
import asyncio
import logging
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def evaluate(ticker: str) -> None:
    from app.data.fetcher import fetch_stock_data
    from app.services.isolation_forest import predict_anomalies
    from app.services.feature_service import build_feature_matrix, build_target_series
    import xgboost as xgb
    from sklearn.metrics import accuracy_score, roc_auc_score, classification_report

    df = await fetch_stock_data(ticker)
    df_anomaly = predict_anomalies(df, ticker)

    X = build_feature_matrix(df_anomaly, include_anomaly=True).iloc[:-1]
    y = build_target_series(df_anomaly).iloc[:-1]

    # Walk-forward evaluation: train on 80%, evaluate on 20%
    split = int(len(X) * 0.8)
    X_train, X_test = X.values[:split], X.values[split:]
    y_train, y_test = y.values[:split], y.values[split:]

    model = xgb.XGBClassifier(n_estimators=300, random_state=42, verbosity=0)
    model.fit(X_train, y_train)
    proba = model.predict_proba(X_test)
    y_pred = (proba[:, 1] >= 0.5).astype(int)

    logger.info("=== Evaluation: %s ===", ticker)
    logger.info("Test samples: %d", len(y_test))
    logger.info("Directional Accuracy: %.3f", accuracy_score(y_test, y_pred))
    if len(set(y_test)) > 1:
        logger.info("ROC-AUC: %.3f", roc_auc_score(y_test, proba[:, 1]))
    logger.info("\n%s", classification_report(y_test, y_pred, target_names=["DOWN", "UP"]))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", required=True)
    args = parser.parse_args()
    asyncio.run(evaluate(args.ticker.upper()))


if __name__ == "__main__":
    main()
