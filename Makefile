# BursaSense / StockSense AI — project automation
# Run `make help` to see all targets.

BACKEND_DIR  := stocksense-ai/backend
FRONTEND_DIR := stocksense-ai/frontend
COMPOSE      := docker compose

.PHONY: help dev build stop logs test lint train train-live check-env migrate rag

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# ── Docker ────────────────────────────────────────────────────────────────────

dev: ## Start all services (Redis + FastAPI + Next.js) — DEMO_MODE=true by default
	$(COMPOSE) up

build: ## Rebuild images and start all services
	$(COMPOSE) up --build

stop: ## Stop all services
	$(COMPOSE) down

logs: ## Tail logs from all services
	$(COMPOSE) logs -f

# ── Tests ─────────────────────────────────────────────────────────────────────

test: ## Run backend tests (DEMO_MODE=true, no external services needed)
	cd $(BACKEND_DIR) && \
	  DEMO_MODE=true pytest tests/ -v --tb=short

lint: ## Run ruff linter on backend
	cd $(BACKEND_DIR) && ruff check app/

# ── ML training ───────────────────────────────────────────────────────────────

train: ## Train XGBoost model in demo mode (synthetic data, no moomoo needed)
	cd $(BACKEND_DIR) && \
	  DEMO_MODE=true python -m scripts.train_model

train-live: ## Train XGBoost model with live moomoo data (requires OpenD running)
	cd $(BACKEND_DIR) && \
	  DEMO_MODE=false python -m scripts.train_model

train-mlflow: ## Train with MLflow experiment tracking
	cd $(BACKEND_DIR) && \
	  DEMO_MODE=true MLFLOW_TRACKING_URI=http://localhost:5000 python -m scripts.train_model --mlflow

# ── Data pipeline ─────────────────────────────────────────────────────────────

ingest-news: ## Ingest KLSE headlines and run FinBERT (one-shot)
	cd $(BACKEND_DIR) && python -m scripts.ingest_news

ingest-demo: ## Ingest demo headlines (no NEWS_API_KEY needed)
	cd $(BACKEND_DIR) && python -m scripts.ingest_news --demo

migrate: ## Print Supabase migration SQL (copy-paste into dashboard)
	cd $(BACKEND_DIR) && python -m scripts.migrations.run_migrations --dry-run

rag: ## Seed pgvector knowledge base with company profiles
	cd $(BACKEND_DIR) && python -m scripts.seed_rag

# ── Environment validation ────────────────────────────────────────────────────

check-env: ## Validate that required environment variables are set
	@echo "Checking backend environment…"
	@cd $(BACKEND_DIR) && python -c "\
from app.core.config import get_settings; s = get_settings(); \
issues = []; \
(issues.append('SECRET_KEY is default — change it!') if s.secret_key == 'changeme-use-openssl-rand-hex-32' else None); \
(issues.append('REDIS_URL not set') if not s.redis_url else None); \
(print('⚠ ' + i) for i in issues) if issues else print('✓ Environment looks good'); \
"
