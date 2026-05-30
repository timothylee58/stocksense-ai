import yfinance as yf
import pandas as pd
import pandas_ta as ta
from app.core.cache import cache_get_df, cache_set_df

DATASET_TTL = 15 * 60  # 15 minutes

def get_full_dataset(ticker: str):
    cache_key = f"cache:dataset:{ticker}"
    cached = cache_get_df(cache_key)
    if cached is not None:
        return cached

    df = yf.download(ticker, period="2y", interval="1d", auto_adjust=True)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df['RSI'] = ta.rsi(df['Close'], length=14)
    df['SMA_20'] = ta.sma(df['Close'], length=20)
    df['SMA_50'] = ta.sma(df['Close'], length=50)
    df['MACD'] = ta.macd(df['Close'])['MACD_12_26_9']
    df['MACD_Signal'] = ta.macd(df['Close'])['MACDs_12_26_9']
    df['Target'] = (df['Close'].shift(-1) > df['Close']).astype(int)
    result = df.dropna()

    cache_set_df(cache_key, result, DATASET_TTL)
    return result

def get_chart_data(df, ticker: str):
    """Returns last 30 days as chart_data list."""
    recent = df.tail(30).copy()
    chart = []
    for idx, row in recent.iterrows():
        chart.append({"time": str(idx.date()), "price": round(float(row['Close']), 2)})
    return chart
