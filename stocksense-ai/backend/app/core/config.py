from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    app_name: str = "StockSense AI"
    api_prefix: str = "/api"
    debug: bool = False

    # Redis
    redis_url: str = "redis://localhost:6379"
    cache_dataset_ttl: int = 900    # 15 min
    cache_predict_ttl: int = 300    # 5 min
    cache_realtime_ttl: int = 10    # 10 seconds for real-time quotes

    # Demo / offline mode — no paid accounts needed, serves synthetic KLSE data
    demo_mode: bool = False

    # Read-only deployment (READ_ONLY_MODE): public demo serving predictions +
    # ledger display. Write paths (orders, kill switch, agent runs) are refused.
    read_only_mode: bool = False

    # Moomoo API (real-time quotes + tick data)
    moomoo_host: str = "127.0.0.1"
    moomoo_port: int = 11111
    moomoo_enabled: bool = True

    # Moomoo paper trading — SIMULATE only, never live
    moomoo_trade_enabled: bool = False
    moomoo_trd_env: str = "SIMULATE"
    moomoo_paper_account_id: str = ""
    moomoo_trd_market: str = "US"
    moomoo_security_firm: str = "FUTUSECURITIES"

    # Pre-trade risk limits
    risk_max_position_pct: float = 0.25
    risk_max_gross_exposure_pct: float = 0.90
    risk_max_order_notional: float = 50_000.0
    risk_max_daily_loss_pct: float = 0.03
    risk_max_drawdown_pct: float = 0.15
    risk_min_cash_buffer_pct: float = 0.10
    risk_limit_orders_only: bool = True
    risk_max_quote_age_s: int = 60  # 0 disables the freshness check
    risk_us_only: bool = True
    risk_max_open_positions: int = 5
    # PRD v0.2: 0.5 % of equity risked per trade (stop-distance sizing).
    risk_per_trade_pct: float = 0.005

    # Challenge agent run loop (paper/SIMULATE only)
    challenge_universe: list[str] = [
        "NVDA", "AAPL", "MSFT", "AMD", "GOOGL", "META", "AMZN", "TSLA",
    ]
    challenge_strategy_version: str = "s1.1"
    # 0.30: the 3-class XGB confidence (empirically <= ~0.52) plus LSTM caps the
    # achievable net near 0.42, so the original 0.60 gate never traded.
    challenge_signal_threshold: float = 0.30
    agent_journal_jsonl: str = "data/agent_journal.jsonl"

    # Decision ledger + equity history
    decision_ledger_jsonl: str = "data/decision_ledger.jsonl"
    portfolio_history_jsonl: str = "data/portfolio_history.jsonl"
    admin_api_token: str = ""

    # Auth
    secret_key: str = "changeme-use-openssl-rand-hex-32"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440  # 24h

    # ML
    seq_len: int = 60               # days of history per LSTM window
    forecast_days: int = 30         # days to forecast into future
    lstm_hidden: int = 64
    lstm_layers: int = 2
    lstm_epochs: int = 80
    lstm_lr: float = 0.001
    models_dir: str = "./models"

    # ClickHouse — OHLCV / indicators / sentiment / backtest history
    clickhouse_host: str = "localhost"
    clickhouse_port: int = 8123
    clickhouse_user: str = "stocksense"
    clickhouse_password: str = "stocksense_ch"
    clickhouse_db: str = "stocksense"
    clickhouse_enabled: bool = True

    # Supabase — auth / user data / training jobs / watchlists
    supabase_url: str = ""
    supabase_service_key: str = ""

    # MLflow
    mlflow_tracking_uri: str = "http://localhost:5000"

    # AI / LLM
    anthropic_api_key: str = ""

    # Data sources
    news_api_key: str = ""
    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    reddit_user_agent: str = "StockSense AI v1.0"

    # ML pipeline
    anomaly_contamination: float = 0.08
    direction_threshold: float = 0.60
    default_tickers: list[str] = ["NVDA", "MAYBANK.KL", "PBBANK.KL"]

    # CORS (restrict in production)
    allowed_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:8081",  # Expo dev server / web
        "http://localhost:8888",  # Next.js dev server
        "http://127.0.0.1:8888",
        "https://your-app.vercel.app",
    ]

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()
