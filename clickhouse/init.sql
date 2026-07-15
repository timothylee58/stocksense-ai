-- ClickHouse DDL for StockSense AI
-- Engine: ReplacingMergeTree so re-ingestion is idempotent.
-- ORDER BY puts the physical sort key first so per-ticker range scans are O(log n).

CREATE DATABASE IF NOT EXISTS stocksense;

-- ── OHLCV + indicators ────────────────────────────────────────────────────────
-- Column names match fetcher.py add_indicators() output exactly.
CREATE TABLE IF NOT EXISTS stocksense.ohlcv (
    ticker          LowCardinality(String),
    market          LowCardinality(String),      -- US | MY | HK
    date            Date,
    open            Float64,
    high            Float64,
    low             Float64,
    close           Float64,
    volume          UInt64,
    adj_close       Float64,
    -- technical indicators (all Nullable — absent during warm-up period)
    rsi             Nullable(Float64),
    macd            Nullable(Float64),
    macd_signal     Nullable(Float64),
    macd_hist       Nullable(Float64),
    sma_20          Nullable(Float64),
    sma_50          Nullable(Float64),
    bb_upper        Nullable(Float64),
    bb_mid          Nullable(Float64),
    bb_lower        Nullable(Float64),
    bb_width        Nullable(Float64),
    bb_pct_b        Nullable(Float64),
    ema_9           Nullable(Float64),
    ema_12          Nullable(Float64),
    ema_26          Nullable(Float64),
    atr_14          Nullable(Float64),
    roc_5           Nullable(Float64),
    roc_20          Nullable(Float64),
    volume_zscore   Nullable(Float64),
    daily_return    Nullable(Float64),
    return_5d       Nullable(Float64),
    price_vs_sma20  Nullable(Float64),
    golden_cross    Nullable(Int8),
    ingested_at     DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYYYYMM(date)
ORDER BY (market, ticker, date);

-- ── News sentiment ────────────────────────────────────────────────────────────
-- One row per headline. Aggregate score is stored per-row for easy GROUP BY queries.
CREATE TABLE IF NOT EXISTS stocksense.news_sentiment (
    ticker          LowCardinality(String),
    published_at    DateTime,
    headline        String,
    source          LowCardinality(String),
    sentiment       LowCardinality(String),      -- positive | neutral | negative
    score           Float64,                     -- signed: pos - neg probability
    ingested_at     DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYYYYMM(published_at)
ORDER BY (ticker, published_at, headline);

-- ── Backtest results ──────────────────────────────────────────────────────────
-- Append-only run history — lets you track model improvement over time.
CREATE TABLE IF NOT EXISTS stocksense.backtest_results (
    ticker              LowCardinality(String),
    run_at              DateTime,
    test_start          Date,
    test_end            Date,
    total_return        Float64,
    benchmark_return    Float64,
    alpha               Float64,
    sharpe_ratio        Float64,
    sortino_ratio       Float64,
    calmar_ratio        Float64,
    max_drawdown        Float64,
    win_rate            Float64,
    n_trades            UInt32,
    annualised_return   Float64
) ENGINE = ReplacingMergeTree(run_at)
ORDER BY (ticker, run_at);

-- ── Useful cross-ticker views ────────────────────────────────────────────────
-- Rolling 30-day volatility (annualised) across all tickers.
-- Usage: SELECT * FROM stocksense.vol_30d WHERE date = today() ORDER BY ann_vol DESC
CREATE VIEW IF NOT EXISTS stocksense.vol_30d AS
SELECT
    ticker,
    market,
    date,
    round(
        stddevSamp(daily_return) OVER (
            PARTITION BY ticker ORDER BY date
            ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
        ) * sqrt(252) * 100, 2
    ) AS ann_vol
FROM stocksense.ohlcv FINAL
WHERE daily_return IS NOT NULL;

-- Top momentum movers (20-day return).
-- Usage: SELECT * FROM stocksense.momentum_20d ORDER BY return_20d DESC LIMIT 50
CREATE VIEW IF NOT EXISTS stocksense.momentum_20d AS
SELECT
    ticker,
    market,
    round(
        (argMax(close, date) - argMin(close, date)) / argMin(close, date) * 100, 2
    ) AS return_20d,
    argMax(close, date)   AS last_price,
    argMax(volume, date)  AS last_volume
FROM stocksense.ohlcv FINAL
WHERE date >= today() - 21
GROUP BY ticker, market;
