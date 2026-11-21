"""Offline packaging contracts: never import the application or unpickle host models."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


BACKEND = Path(__file__).resolve().parents[1]
SCRIPT = BACKEND / "scripts" / "validate_models.py"


def validator():
    # Keep the initial red failure explicit rather than a collection/import error.
    assert SCRIPT.is_file(), "Model packaging validator has not been implemented"
    spec = importlib.util.spec_from_file_location("packaging_validator", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ModelPackagingTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.models = Path(self.directory.name)

    def bundle(self, ticker="NVDA"):
        for name in (
            f"{ticker}_lstm.pt", f"{ticker}_lstm_scaler.pkl",
            f"{ticker}_xgb.pkl", f"xgb_{ticker}.json",
        ):
            (self.models / name).write_bytes(b"inventory fixture; never deserialize")

    def test_missing_scaler_is_rejected(self):
        gate = validator()
        self.bundle()
        (self.models / "NVDA_lstm_scaler.pkl").unlink()
        with self.assertRaisesRegex(ValueError, "NVDA_lstm_scaler.pkl"):
            gate.validate_files(self.models, ("NVDA",))

    def test_missing_pipeline_model_is_rejected(self):
        gate = validator()
        self.bundle()
        (self.models / "xgb_NVDA.json").unlink()
        with self.assertRaisesRegex(ValueError, "xgb_NVDA.json"):
            gate.validate_files(self.models, ("NVDA",))

    def test_complete_bundle_passes_inventory_only(self):
        gate = validator()
        self.bundle()
        files = gate.validate_files(self.models, ("NVDA",))
        self.assertEqual({path.name for path in files}, {
            "NVDA_lstm.pt", "NVDA_lstm_scaler.pkl", "NVDA_xgb.pkl", "xgb_NVDA.json",
        })

    def test_every_configured_ticker_is_checked(self):
        gate = validator()
        self.bundle()
        with self.assertRaisesRegex(ValueError, "AAPL_lstm.pt"):
            gate.validate_files(self.models, ("NVDA", "AAPL"))

    def test_zero_byte_artifacts_are_rejected(self):
        gate = validator()
        self.bundle()
        (self.models / "NVDA_xgb.pkl").write_bytes(b"")
        with self.assertRaisesRegex(ValueError, "NVDA_xgb.pkl"):
            gate.validate_files(self.models, ("NVDA",))

    def test_symlink_artifacts_are_rejected(self):
        gate = validator()
        self.bundle()
        path = self.models / "NVDA_lstm.pt"
        path.unlink()
        path.symlink_to(self.models / "NVDA_xgb.pkl")
        with self.assertRaisesRegex(ValueError, "NVDA_lstm.pt"):
            gate.validate_files(self.models, ("NVDA",))

    def test_empty_and_invalid_ticker_input_is_rejected(self):
        gate = validator()
        for raw in ("", " ", ",", "NVDA,", "NVDA,,AAPL", "../NVDA", "A/B", "A;B", ".NVDA"):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                gate.parse_tickers(raw)
        with self.assertRaises(ValueError):
            gate.validate_files(self.models, ())
        with self.assertRaises(ValueError):
            gate.validate_files(self.models, ("../NVDA",))

    def test_ticker_normalization_keeps_exchange_suffixes(self):
        gate = validator()
        self.assertEqual(gate.parse_tickers(" nvda,brk-b,maybank.kl,NVDA "),
                         ("NVDA", "BRK-B", "MAYBANK.KL"))

    def test_default_manifest_covers_dashboard_agents_and_services(self):
        gate = validator()
        tickers = gate.advertised_tickers(BACKEND)
        self.assertEqual(set(tickers), {
            "AAPL", "NVDA", "MSFT", "AMD", "GOOGL", "META", "AMZN", "TSLA",
            "WMT", "NFLX", "BRK-B", "JPM", "V", "LLY", "XOM", "MAYBANK.KL", "PBBANK.KL",
        })

    def test_custom_manifest_cannot_silently_drop_advertised_tickers(self):
        gate = validator()
        with self.assertRaisesRegex(ValueError, "advertised"):
            gate.resolve_tickers("NVDA", BACKEND)
        defaults = gate.advertised_tickers(BACKEND)
        resolved = gate.resolve_tickers(",".join((*defaults, "TEST")), BACKEND)
        self.assertIn("TEST", resolved)
        self.assertTrue(set(defaults).issubset(resolved))

    def test_runtime_versions_match_verified_training_environment(self):
        gate = validator()
        versions = {
            "torch": "2.15.0+cpu", "xgboost-cpu": "3.4.1", "scikit-learn": "1.9.1",
            "numpy": "2.2.6", "pandas": "2.3.3", "pandas-ta": "0.4.71b0", "joblib": "1.6.0",
        }
        gate.validate_versions("3.12.15", versions)
        for name, wrong in (("numpy", "1.26.4"), ("torch", "2.15.0+cu128")):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, name):
                gate.validate_versions("3.12.15", {**versions, name: wrong})
        with self.assertRaisesRegex(ValueError, "Python"):
            gate.validate_versions("3.11.9", versions)
        with self.assertRaisesRegex(ValueError, "CUDA"):
            gate.validate_versions("3.12.15", {**versions, "nvidia-cublas-cu12": "12.0"})

    def test_cli_rejects_invalid_input_without_loading_application(self):
        validator()
        result = self.run_cli("--tickers", "", "--check-files-only")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ticker", result.stderr.lower())
        self.assertNotIn("Traceback", result.stderr)

    def test_cli_reports_complete_inventory_but_not_loading_success(self):
        gate = validator()
        for ticker in gate.advertised_tickers(BACKEND):
            self.bundle(ticker)
        result = self.run_cli("--check-files-only")
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["validation"], "files-only")
        self.assertEqual(report["artifact_count"], 68)

    def test_loading_requires_explicit_trust(self):
        gate = validator()
        for ticker in gate.advertised_tickers(BACKEND):
            self.bundle(ticker)
        result = self.run_cli()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("trusted", result.stderr.lower())

    def run_cli(self, *arguments):
        # Empty environment and an empty cwd prevent accidental dotenv/settings use.
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "--models-dir", str(self.models), *arguments],
            cwd=self.models,
            env={"PATH": os.defpath, "PYTHONDONTWRITEBYTECODE": "1"},
            capture_output=True, text=True, check=False,
        )


if __name__ == "__main__":
    unittest.main()
