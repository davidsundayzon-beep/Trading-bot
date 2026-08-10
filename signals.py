"""
signals.py
Turns price/volume data into a scored trade signal (0-100) plus a
CALL / PUT / NO-TRADE recommendation.

IMPORTANT HONESTY NOTE:
This score is a confidence heuristic based on technical indicators, not a
guarantee. Do not present this score to end users as an "accuracy" figure.
Track real outcomes (see tracker.py) and report the actual historical hit
rate instead of this internal score.
"""

import pandas as pd
import ta


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add RSI, MACD, moving averages, and Bollinger Bands to a price df."""
    df = df.copy()
    df["rsi"] = ta.momentum.RSIIndicator(df["close"], window=14).rsi()

    macd = ta.trend.MACD(df["close"])
    df["macd"] = macd.macd()
    df["macd_signal"] = macd.macd_signal()
    df["macd_hist"] = macd.macd_diff()

    df["sma20"] = df["close"].rolling(20).mean()
    df["sma50"] = df["close"].rolling(50).mean()

    bb = ta.volatility.BollingerBands(df["close"], window=20)
    df["bb_high"] = bb.bollinger_hband()
    df["bb_low"] = bb.bollinger_lband()

    atr = ta.volatility.AverageTrueRange(df["high"], df["low"], df["close"], window=14)
    df["atr"] = atr.average_true_range()

    df["volume_avg20"] = df["volume"].rolling(20).mean()

    return df


def suggest_duration_minutes(latest_row) -> tuple:
    """
    Estimate how long a trade should run, based on how fast the pair is
    currently moving (ATR relative to price). Faster-moving pairs reach a
    given move sooner, so they get a shorter suggested duration.
    Capped at 3 minutes and below, matching short-expiry trading style —
    these are quick, decisive windows, not longer holds.
    Returns (minutes, reason_text).
    """
    atr_pct = (latest_row["atr"] / latest_row["close"]) * 100

    if atr_pct >= 0.15:
        return 1, f"High volatility (ATR {atr_pct:.2f}% of price) — fast mover, very short window"
    elif atr_pct <= 0.05:
        return 3, f"Lower volatility (ATR {atr_pct:.2f}% of price) — needs the fuller window"
    else:
        return 2, f"Moderate volatility (ATR {atr_pct:.2f}% of price) — standard short window"


def score_signal(df: pd.DataFrame) -> dict:
    """
    Look at the latest row of indicators and produce a directional score.
    Returns a dict: {direction, score, reasons}
    Score is 0-100, purely a weighted heuristic — not a probability.
    """
    df = compute_indicators(df).dropna()
    if df.empty:
        return {"direction": "NO_TRADE", "score": 0, "reasons": ["Not enough data"]}

    latest = df.iloc[-1]
    score = 50  # neutral baseline
    reasons = []

    # RSI momentum
    if latest["rsi"] < 30:
        score += 15
        reasons.append(f"RSI oversold ({latest['rsi']:.1f}) — bullish bias")
    elif latest["rsi"] > 70:
        score -= 15
        reasons.append(f"RSI overbought ({latest['rsi']:.1f}) — bearish bias")

    # MACD crossover
    if latest["macd"] > latest["macd_signal"]:
        score += 10
        reasons.append("MACD above signal line — bullish momentum")
    else:
        score -= 10
        reasons.append("MACD below signal line — bearish momentum")

    # Trend via moving averages
    if latest["sma20"] > latest["sma50"]:
        score += 10
        reasons.append("Short-term trend above long-term trend — bullish")
    else:
        score -= 10
        reasons.append("Short-term trend below long-term trend — bearish")

    # Bollinger Band position
    if latest["close"] <= latest["bb_low"]:
        score += 10
        reasons.append("Price at lower Bollinger Band — potential bounce")
    elif latest["close"] >= latest["bb_high"]:
        score -= 10
        reasons.append("Price at upper Bollinger Band — potential pullback")

    # Volume confirmation
    if latest["volume"] > latest["volume_avg20"] * 1.5:
        boost = 10 if score >= 50 else -10
        score += boost
        reasons.append("Volume surge — confirms current move strength")

    score = max(0, min(100, score))

    # Volatility floor: even a technically-qualifying signal isn't
    # meaningful for a short-duration trade if the market is nearly flat.
    # Below this ATR%, there's not enough real price movement happening
    # for a 1-3 minute directional bet to be a fair test of the signal —
    # it's closer to a coin flip regardless of confidence score.
    MIN_VOLATILITY_PCT = 0.03
    atr_pct = (latest["atr"] / latest["close"]) * 100

    if atr_pct < MIN_VOLATILITY_PCT:
        return {
            "direction": "NO_TRADE",
            "score": score,
            "confidence": 0,
            "reasons": [f"Market too flat to trade (ATR {atr_pct:.3f}% of price, below {MIN_VOLATILITY_PCT}% floor)"],
            "price": round(float(latest["close"]), 2),
            "duration_minutes": 0,
            "duration_reason": "",
        }

    if score >= 70:
        direction = "CALL"
    elif score <= 30:
        direction = "PUT"
    else:
        direction = "NO_TRADE"

    # 'score' is on a bullish scale (100=strong buy, 0=strong sell, 50=neutral).
    # 'confidence' mirrors it so it always reads as "how strong is the signal
    # in the direction shown" — a strong sell (score=20) should display as
    # high confidence (80), not a misleadingly low 20.
    confidence = score if direction == "CALL" else (100 - score)

    duration_minutes, duration_reason = suggest_duration_minutes(latest)

    return {
        "direction": direction,
        "score": score,
        "confidence": confidence,
        "reasons": reasons,
        "price": round(float(latest["close"]), 2),
        "duration_minutes": duration_minutes,
        "duration_reason": duration_reason,
    }


def pick_option_contract(calls_df, puts_df, direction: str, current_price: float):
    """
    Given a direction, pick a near-the-money contract as a simple default
    (near-the-money tends to have tighter spreads and clearer liquidity
    than deep OTM lottery-ticket strikes).
    """
    df = calls_df if direction == "CALL" else puts_df
    if df is None or df.empty:
        return None

    df = df.copy()
    df["distance"] = (df["strike"] - current_price).abs()
    contract = df.sort_values("distance").iloc[0]

    return {
        "contractSymbol": contract.get("contractSymbol"),
        "strike": contract.get("strike"),
        "lastPrice": contract.get("lastPrice"),
        "bid": contract.get("bid"),
        "ask": contract.get("ask"),
        "volume": contract.get("volume"),
        "openInterest": contract.get("openInterest"),
        "impliedVolatility": contract.get("impliedVolatility"),
    }
