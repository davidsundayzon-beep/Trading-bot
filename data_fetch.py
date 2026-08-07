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
from datetime import datetime


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
    If expiry is None, uses the nearest available expiration date.
    Returns (calls_df, puts_df, expiry_used).
    """
    tk = yf.Ticker(ticker)
    expirations = tk.options
    if not expirations:
        raise ValueError(f"No options expirations found for {ticker}")

    if expiry is None:
        expiry = expirations[0]  # nearest expiry
    elif expiry not in expirations:
        raise ValueError(f"Expiry {expiry} not available for {ticker}. Options: {expirations}")

    chain = tk.option_chain(expiry)
    return chain.calls, chain.puts, expiry


def get_current_price(ticker: str) -> float:
    """Fast lookup of the latest price."""
    tk = yf.Ticker(ticker)
    fast = tk.fast_info
    return float(fast["lastPrice"])


if __name__ == "__main__":
    # quick manual test
    df = get_price_history("AAPL")
    print(df.tail())
    calls, puts, expiry = get_options_chain("AAPL")
    print(f"Nearest expiry: {expiry}")
    print(calls.head())
