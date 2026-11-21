"""Fail closed on incomplete/incompatible *trusted* serving bundles. Never trains.

The default manifest is the US prediction dashboard universe (core/stocks.py),
agent challenge universe, and service default_tickers (core/config.py), read via
AST, without importing settings or dotenv. Quote-only MY/SG lists are not claims
of trained prediction coverage. MODEL_TICKERS can add coverage, not silently drop
advertised predictions; narrowing coverage requires changing the product first.

--check-files-only is an offline inventory, NOT a release gate. Deserialization
requires --trusted-artifacts and must run in the target Linux CPU image. Pickles
can execute code: the caller must authenticate the artifact source beforehand.
"""
from __future__ import annotations

import argparse
import ast
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import sys
import warnings


BACKEND = Path(__file__).resolve().parents[1]
VERSIONS = {
    "torch": "2.15.0",
    "xgboost": "3.4.1",
    "scikit-learn": "1.9.1",
    "numpy": "2.2.6",
    "pandas": "2.3.3",
    "pandas-ta": "0.4.71b0",
    "joblib": "1.6.0",
}


def parse_tickers(raw: str) -> tuple[str, ...]:
    tickers = tuple(dict.fromkeys(item.strip().upper() for item in raw.split(",")))
    if not tickers or any(not re.fullmatch(r"[A-Z0-9]+(?:[.-][A-Z0-9]+)*", t) for t in tickers):
        raise ValueError("ticker manifest must be non-empty, comma-separated symbols (no empty entries)")
    return tickers


def _literal(path: Path, name: str):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == name:
            return ast.literal_eval(node.value)
    raise ValueError(f"Cannot discover advertised manifest: {path}:{name}")


def advertised_tickers(backend: Path = BACKEND) -> tuple[str, ...]:
    stocks = _literal(backend / "app/core/stocks.py", "STOCK_UNIVERSE")
    tickers = [symbol.removeprefix("US.") for symbol, info in stocks.items() if info["market"] == "US"]
    for setting in ("challenge_universe", "default_tickers"):
        tickers.extend(_literal(backend / "app/core/config.py", setting))
    return parse_tickers(",".join(tickers))


def resolve_tickers(raw: str, backend: Path = BACKEND) -> tuple[str, ...]:
    advertised = advertised_tickers(backend)
    if raw == "advertised":
        return advertised
    tickers = parse_tickers(raw)
    missing = sorted(set(advertised) - set(tickers))
    if missing:
        raise ValueError("Manifest omits advertised tickers: " + ", ".join(missing))
    return tickers


def validate_files(models_dir: Path, tickers: tuple[str, ...]) -> tuple[Path, ...]:
    tickers = parse_tickers(",".join(tickers))
    files = tuple(
        models_dir / name
        for ticker in tickers
        for name in (f"{ticker}_lstm.pt", f"{ticker}_lstm_scaler.pkl", f"{ticker}_xgb.pkl", f"xgb_{ticker}.json")
    )
    invalid = [str(p) for p in files if p.is_symlink() or not p.is_file() or p.stat().st_size == 0]
    if invalid:
        raise ValueError("Missing, empty or symlink model artifacts:\n" + "\n".join(invalid))
    return files


def validate_versions(python_version: str, versions: dict[str, str]) -> None:
    errors = []
    if python_version != "3.12.15":
        errors.append(f"Python expected 3.12.15, got {python_version}")
    for name, expected in VERSIONS.items():
        actual = versions.get(name)
        if name == "xgboost":
            actual = versions.get("xgboost-cpu", actual)
        allowed = {expected, f"{expected}+cpu"} if name == "torch" else {expected}
        if actual not in allowed:
            errors.append(f"{name} expected {expected}, got {actual}")
    cuda = [name for name in versions if name.startswith("nvidia-") or name in {"triton", "pytorch-triton"}]
    if cuda:
        errors.append("CUDA/GPU packages forbidden in CPU serving: " + ", ".join(sorted(cuda)))
    if errors:
        raise ValueError("Runtime compatibility failed:\n" + "\n".join(errors))


def validate_runtime() -> dict[str, str]:
    if sys.platform != "linux":
        raise ValueError("Artifact loading must run in the target Linux CPU image, not the host")
    versions = {dist.metadata["Name"].lower().replace("_", "-"): dist.version
                for dist in importlib.metadata.distributions()}
    validate_versions(platform.python_version(), versions)
    if "xgboost-cpu" not in versions or "xgboost" in versions:
        raise ValueError("Linux serving requires xgboost-cpu only, not the GPU-capable xgboost distribution")
    import torch
    if torch.version.cuda is not None:
        raise ValueError("CUDA torch build forbidden in CPU serving")
    # Import the indicator implementation too: ABI/import errors are release blockers.
    import pandas_ta  # noqa: F401
    return {name: versions.get("xgboost-cpu" if name == "xgboost" else name) for name in VERSIONS}


def load_bundle(models_dir: Path, tickers: tuple[str, ...]) -> None:
    """Use the serving classes and feature schemas; no data fetch, app startup or fit."""
    import joblib
    import numpy as np
    import torch
    import xgboost as xgb
    from sklearn.exceptions import InconsistentVersionWarning

    # Import model modules only after replacing the settings factory with explicit,
    # isolated settings. No dotenv, broker, Redis, FinBERT downloads or app.main.
    sys.path.insert(0, str(BACKEND))
    from app.core import config
    settings = config.Settings(
        _env_file=None, models_dir=str(models_dir), seq_len=60, lstm_hidden=64,
        lstm_layers=2, moomoo_enabled=False, moomoo_trade_enabled=False,
        moomoo_trd_env="SIMULATE", clickhouse_enabled=False,
    )

    def isolated_settings():
        return settings

    config.get_settings = isolated_settings
    from app.ml.models import lstm, xgb_model
    from app.services.feature_service import DIRECTION_FEATURES

    torch.set_num_threads(1)
    with warnings.catch_warnings():
        warnings.simplefilter("error", InconsistentVersionWarning)
        for ticker in tickers:
            try:
                checkpoint = torch.load(models_dir / f"{ticker}_lstm.pt", map_location="cpu", weights_only=True)
                cols = checkpoint["cols"]
                if cols != lstm.FEATURE_COLS or checkpoint["n_features"] != len(cols):
                    raise ValueError("LSTM feature schema differs from serving code")
                net = lstm._LSTMNet(len(cols), hidden=settings.lstm_hidden, layers=settings.lstm_layers)
                net.load_state_dict(checkpoint["state"], strict=True)
                net.eval()
                scaler = joblib.load(models_dir / f"{ticker}_lstm_scaler.pkl")
                # Financial preprocessing uses float64; the saved network itself uses
                # float32, matching the existing loader (no retraining/conversion).
                scaled = scaler.transform(np.zeros((60, len(cols)), dtype=np.float64))
                if scaled.shape != (60, len(cols)) or not np.isfinite(scaled).all():
                    raise ValueError("Invalid LSTM scaler output")
                with torch.no_grad():
                    prediction = net(torch.as_tensor(scaled[None], dtype=torch.float32)).item()
                restored = scaler.inverse_transform(np.full((1, len(cols)), prediction, dtype=np.float64))
                if not np.isfinite(restored).all():
                    raise ValueError("Non-finite LSTM prediction")

                checkpoint = joblib.load(models_dir / f"{ticker}_xgb.pkl")
                model, encoder = checkpoint["model"], checkpoint["label_encoder"]
                probabilities = model.predict_proba(np.zeros((1, len(xgb_model.FEATURE_COLS)), dtype=np.float64))
                labels = encoder.inverse_transform(np.arange(probabilities.shape[1]))
                if set(labels) != {"BUY", "HOLD", "SELL"}:
                    raise ValueError("Invalid /predict XGB label encoder")
                _probabilities(probabilities, 3)

                pipeline = xgb.XGBClassifier()
                pipeline.load_model(models_dir / f"xgb_{ticker}.json")
                probabilities = pipeline.predict_proba(np.zeros((1, len(DIRECTION_FEATURES)), dtype=np.float64))
                _probabilities(probabilities, 2)
            except Exception as exc:
                raise ValueError(f"{ticker}: artifact loading/inference failed: {exc}") from exc


def _probabilities(values, classes: int) -> None:
    import numpy as np
    if (values.shape != (1, classes) or not np.isfinite(values).all()
            or (values < 0).any() or (values > 1).any() or not np.allclose(values.sum(axis=1), 1.0)):
        raise ValueError("Invalid XGBoost probability output")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models-dir", type=Path, default=BACKEND / "models")
    parser.add_argument("--tickers", default=os.environ.get("MODEL_TICKERS", "advertised"))
    parser.add_argument("--check-files-only", action="store_true", help="Inventory only; not proof of loadability")
    parser.add_argument("--trusted-artifacts", action="store_true", help="Authorize loading trusted pre-trained pickles")
    args = parser.parse_args(argv)
    try:
        tickers = resolve_tickers(args.tickers)
        files = validate_files(args.models_dir, tickers)
        report = {"tickers": tickers, "artifact_count": len(files), "validation": "files-only"}
        if not args.check_files_only:
            if not args.trusted_artifacts:
                raise ValueError("Loading requires --trusted-artifacts; never deserialize an untrusted bundle")
            report["versions"] = validate_runtime()
            load_bundle(args.models_dir.resolve(), tickers)
            report["validation"] = "loaded-cpu"
        print(json.dumps(report, sort_keys=True))
        return 0
    except Exception as exc:
        print(f"Model packaging validation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
