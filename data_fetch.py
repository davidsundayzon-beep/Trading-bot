"""
data_fetch.py
Pulls underlying price history and options chain data.

Uses yfinance because it's free and requires no API key, which makes this
starter runnable immediately. yfinance is unofficial and can be rate-limited
or occasionally unreliable — for a production/paid product, swap this module
out for a paid data provider (Tradier, Polygon.io, or your broker's API).
The rest of the bot doesn't need to change if you keep the same function
signatures.
"""

import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta


def get_price_history(ticker: str, period: str = "3mo", interval: str = "1d") -> pd.DataFrame:
    """Fetch OHLCV price history for a ticker."""
    df = yf.Ticker(ticker).history(period=period, interval=interval)
    if df.empty:
        raise ValueError(f"No price data returned for {ticker}")
    df = df.rename(columns=str.lower)
    return df


def get_intraday_history(ticker: str, period: str = "5d", interval: str = "5m") -> pd.DataFrame:
    """Fetch shorter-interval data, used for the 'minutes' timeframe signals."""
    df = yf.Ticker(ticker).history(period=period, interval=interval)
    if df.empty:
        raise ValueError(f"No intraday data returned for {ticker}")
    df = df.rename(columns=str.lower)
    return df


def get_options_chain(ticker: str, expiry: str = None):
    """
    Fetch the options chain for a ticker.
    If expiry is None, uses the nearest available FUTURE expiration date
    (skips any expiries that have already passed, which yfinance can still
    list briefly after they occur).
    Returns (calls_df, puts_df, expiry_used).
    """
    tk = yf.Ticker(ticker)
    expirations = tk.options
    if not expirations:
        raise ValueError(f"No options expirations found for {ticker}")

    if expiry is None:
        today = datetime.now().strftime("%Y-%m-%d")
        future_expirations = [e for e in expirations if e >= today]
        if not future_expirations:
            raise ValueError(f"No future expirations found for {ticker} (all listed dates have passed)")
        expiry = future_expirations[0]  # nearest FUTURE expiry
    elif expiry not in expirations:
        raise ValueError(f"Expiry {expiry} not available for {ticker}. Options: {expirations}")

    chain = tk.option_chain(expiry)
    return chain.calls, chain.puts, expiry


def get_current_price(ticker: str) -> float:
    """
    Get the latest price using the same intraday-history method used for
    scanning, rather than yfinance's fast_info endpoint.

    fast_info pulls from a separate Yahoo endpoint that has been observed
    to return stale/cached values for extended periods (sometimes 15+
    minutes unchanged even during active trading). Since get_intraday_history
    is already proven to update reliably (it's what the staleness check
    relies on), reusing it here for outcome-checking avoids silently
    resolving signals against a frozen price.
    """
    df = get_intraday_history(ticker, period="1d", interval="1m")
    if df.empty:
        raise ValueError(f"No recent price data available for {ticker}")
    return float(df["close"].iloc[-1])


def is_data_stale(df: pd.DataFrame, max_age_minutes: int = 20) -> bool:
    """
    Check whether the most recent candle is actually recent, or whether
    it's leftover data from before a market closure (e.g. a weekend).
    If the newest timestamp in the data is older than max_age_minutes,
    treat it as stale — the market is very likely closed, and any signal
    generated from this data would just be re-scoring the same old candle
    repeatedly rather than reacting to real price movement.
    """
    if df.empty:
        return True

    last_timestamp = df.index[-1]
    if last_timestamp.tzinfo is None:
        last_timestamp = last_timestamp.tz_localize("UTC")

    now = datetime.now(last_timestamp.tzinfo) if last_timestamp.tzinfo else datetime.utcnow()
    age = now - last_timestamp

    return age > timedelta(minutes=max_age_minutes)


def get_higher_timeframe_trend(ticker: str) -> str:
    """
    Determine the broader trend direction using 4-hour candles, so a
    short-term scalp signal can be checked against the bigger picture
    before firing — trading against the higher-timeframe trend is a
    common way a technically-valid short-term signal still loses.

    yfinance doesn't offer a native 4h interval, so this fetches 1h
    candles and resamples them into 4h bars.

    Returns 'bullish', 'bearish', or 'neutral' (not enough data, or the
    trend isn't clearly in either direction).
    """
    df = yf.Ticker(ticker).history(period="60d", interval="1h")
    if df.empty or len(df) < 60:
        return "neutral"

    df = df.rename(columns=str.lower)
    resampled = df.resample("4h").agg({
        "open": "first", "high": "max", "low": "min",
        "close": "last", "volume": "sum",
    }).dropna()

    if len(resampled) < 55:
        return "neutral"

    sma20 = resampled["close"].rolling(20).mean().iloc[-1]
    sma50 = resampled["close"].rolling(50).mean().iloc[-1]

    if pd.isna(sma20) or pd.isna(sma50):
        return "neutral"

    if sma20 > sma50:
        return "bullish"
    elif sma20 < sma50:
        return "bearish"
    return "neutral"


if __name__ == "__main__":
    # quick manual test
    df = get_price_history("AAPL")
    print(df.tail())
    calls, puts, expiry = get_options_chain("AAPL")
    print(f"Nearest expiry: {expiry}")
    print(calls.head())
