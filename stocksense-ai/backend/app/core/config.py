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

    # Moomoo API (real-time quotes + tick data)
    moomoo_host: str = "127.0.0.1"
    moomoo_port: int = 11111
    moomoo_enabled: bool = True

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

    # Supabase
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
    allowed_origins: list[str] = ["http://localhost:3000", "https://main.your-app-id.amplifyapp.com"]

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()
