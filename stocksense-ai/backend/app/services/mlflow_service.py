"""MLflow experiment tracking helpers."""
from __future__ import annotations
import logging
from typing import Optional, Any
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def _get_mlflow():
    try:
        import mlflow
        mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
        return mlflow
    except ImportError:
        logger.warning("MLflow not installed — experiment tracking disabled")
        return None


def log_training_run(
    ticker: str,
    params: dict[str, Any],
    metrics: dict[str, float],
    artifacts: Optional[dict[str, str]] = None,
) -> Optional[str]:
    """Log a training run to MLflow. Returns run_id or None."""
    mlflow = _get_mlflow()
    if mlflow is None:
        return None
    try:
        mlflow.set_experiment(f"stocksense_{ticker.lower()}")
        with mlflow.start_run(run_name=f"train_{ticker}") as run:
            mlflow.log_params(params)
            mlflow.log_metrics(metrics)
            if artifacts:
                for name, path in artifacts.items():
                    mlflow.log_artifact(path, artifact_path=name)
            return run.info.run_id
    except Exception as e:
        logger.error("MLflow logging failed: %s", e)
        return None


def compare_runs(run_id_a: str, run_id_b: str) -> dict:
    """Compare two MLflow runs. Returns metric delta dict."""
    mlflow = _get_mlflow()
    if mlflow is None:
        return {"error": "MLflow not available"}
    try:
        client = mlflow.tracking.MlflowClient()
        run_a = client.get_run(run_id_a)
        run_b = client.get_run(run_id_b)
        metrics_a = run_a.data.metrics
        metrics_b = run_b.data.metrics
        all_keys = set(metrics_a) | set(metrics_b)
        deltas = {}
        for k in all_keys:
            a_val = metrics_a.get(k, 0.0)
            b_val = metrics_b.get(k, 0.0)
            deltas[k] = {"run_a": a_val, "run_b": b_val, "delta": round(b_val - a_val, 4)}
        return {"run_id_a": run_id_a, "run_id_b": run_id_b, "metric_deltas": deltas}
    except Exception as e:
        return {"error": str(e)}
