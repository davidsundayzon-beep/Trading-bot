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
    df["atr_pct"] = (df["atr"] / df["close"]) * 100
    # Rolling median of this pair's own recent ATR%, used as an adaptive
    # baseline instead of one fixed number for all 7 pairs. Different
    # pairs (and different times of day) naturally move by different
    # amounts — comparing "right now" to "this pair's own recent normal"
    # calibrates automatically instead of guessing a single percentage.
    df["atr_pct_median"] = df["atr_pct"].rolling(50, min_periods=20).median()

    df["volume_avg20"] = df["volume"].rolling(20).mean()

    return df


def suggest_duration_minutes(latest_row) -> tuple:
    """
    Estimate how long a trade should run, based on how fast the pair is
    currently moving (ATR relative to price). Faster-moving pairs reach a
    given move sooner, so they get a shorter suggested duration.
    Widened to 5 tiers (1-5 min) instead of 3, since most real ATR readings
    were clustering in the middle bucket and always producing "2 min" —
    this spreads the range out for more genuine variation.
    Returns (minutes, reason_text).
    """
    atr_pct = (latest_row["atr"] / latest_row["close"]) * 100

    if atr_pct >= 0.20:
        return 1, f"Very high volatility (ATR {atr_pct:.2f}% of price) — fast mover, shortest window"
    elif atr_pct >= 0.12:
        return 2, f"High volatility (ATR {atr_pct:.2f}% of price) — quick mover"
    elif atr_pct >= 0.08:
        return 3, f"Moderate volatility (ATR {atr_pct:.2f}% of price) — standard window"
    elif atr_pct >= 0.055:
        return 4, f"Lower volatility (ATR {atr_pct:.2f}% of price) — needs a fuller window"
    else:
        return 5, f"Low volatility (ATR {atr_pct:.2f}% of price) — needs the longest window to develop"


def score_signal(df: pd.DataFrame, htf_trend: str = "neutral") -> dict:
    """
    Look at the latest row of indicators and produce a directional score.
    Returns a dict: {direction, score, reasons}
    Score is 0-100, purely a weighted heuristic — not a probability.

    htf_trend: the higher-timeframe (4H) trend bias — 'bullish', 'bearish',
    or 'neutral'. When provided and not neutral, a signal is only allowed
    to fire if its direction agrees with the broader trend. Trading a
    short-term scalp against the bigger picture is a common way a
    technically-valid signal still loses.
    """
    df = compute_indicators(df).dropna()
    if df.empty:
        return {"direction": "NO_TRADE", "score": 0, "reasons": ["Not enough data"]}

    latest = df.iloc[-1]
    score = 50  # neutral baseline
    reasons = []
    bullish_votes = 0
    bearish_votes = 0

    # RSI momentum
    if latest["rsi"] < 30:
        score += 15
        bullish_votes += 1
        reasons.append(f"RSI oversold ({latest['rsi']:.1f}) — bullish bias")
    elif latest["rsi"] > 70:
        score -= 15
        bearish_votes += 1
        reasons.append(f"RSI overbought ({latest['rsi']:.1f}) — bearish bias")

    # MACD crossover
    if latest["macd"] > latest["macd_signal"]:
        score += 10
        bullish_votes += 1
        reasons.append("MACD above signal line — bullish momentum")
    else:
        score -= 10
        bearish_votes += 1
        reasons.append("MACD below signal line — bearish momentum")

    # Trend via moving averages
    if latest["sma20"] > latest["sma50"]:
        score += 10
        bullish_votes += 1
        reasons.append("Short-term trend above long-term trend — bullish")
    else:
        score -= 10
        bearish_votes += 1
        reasons.append("Short-term trend below long-term trend — bearish")

    # Bollinger Band position
    if latest["close"] <= latest["bb_low"]:
        score += 10
        bullish_votes += 1
        reasons.append("Price at lower Bollinger Band — potential bounce")
    elif latest["close"] >= latest["bb_high"]:
        score -= 10
        bearish_votes += 1
        reasons.append("Price at upper Bollinger Band — potential pullback")

    # Volume confirmation
    if latest["volume"] > latest["volume_avg20"] * 1.5:
        boost = 10 if score >= 50 else -10
        score += boost
        if boost > 0:
            bullish_votes += 1
        else:
            bearish_votes += 1
        reasons.append("Volume surge — confirms current move strength")

    score = max(0, min(100, score))

    # Volatility floor: even a technically-qualifying signal isn't
    # meaningful for a short-duration trade if the market is nearly flat.
    # If there's not enough real price movement happening right now, a
    # 1-5 minute directional bet is closer to a coin flip regardless of
    # confidence score.
    #
    # History: this used to be one fixed percentage for all 7 pairs
    # (tried 0.03, 0.08, 0.055) — but different pairs naturally move by
    # different amounts, so no single number worked well for all of them
    # at all times of day. Now it's adaptive: current volatility is
    # compared to THIS pair's own recent typical volatility (rolling
    # median), so each pair calibrates to its own normal instead of an
    # arbitrary shared threshold.
    atr_pct = latest["atr_pct"]
    atr_pct_median = latest["atr_pct_median"]

    # Fallback to a conservative absolute floor if there's not yet enough
    # history to compute a reliable median (e.g. right after startup).
    if pd.isna(atr_pct_median):
        MIN_VOLATILITY_PCT = 0.05
        is_too_flat = atr_pct < MIN_VOLATILITY_PCT
        flat_reason = f"Market too flat to trade (ATR {atr_pct:.3f}% of price, below {MIN_VOLATILITY_PCT}% fallback floor — not enough history yet for adaptive comparison)"
    else:
        # Require current volatility to be at least 70% of this pair's own
        # recent normal — i.e. not dramatically quieter than usual.
        VOLATILITY_RATIO_FLOOR = 0.70
        is_too_flat = atr_pct < (atr_pct_median * VOLATILITY_RATIO_FLOOR)
        flat_reason = (
            f"Market too flat to trade (ATR {atr_pct:.3f}% vs this pair's "
            f"recent normal of {atr_pct_median:.3f}% — currently only "
            f"{(atr_pct / atr_pct_median * 100):.0f}% of typical)"
        )

    if is_too_flat:
        return {
            "direction": "NO_TRADE",
            "score": score,
            "confidence": 0,
            "strength": "WEAK",
            "reasons": [flat_reason],
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

    # Real-agreement check: a score can clear 70/30 from just two factors
    # (e.g. MACD + trend agreeing = 50+10+10 = 70) — technically past the
    # threshold, but not a genuinely strong, multi-confirmed signal. This
    # was found directly from real trades: confidence kept showing exactly
    # 70/100 every time, meaning only the bare-minimum combination was ever
    # firing. Requiring at least 3 of 5 indicators to agree in the same
    # direction filters out that weak, repetitive pattern.
    dominant_votes = bullish_votes if direction == "CALL" else bearish_votes
    if direction != "NO_TRADE" and dominant_votes < 3:
        return {
            "direction": "NO_TRADE",
            "score": score,
            "confidence": 0,
            "strength": "WEAK",
            "reasons": [f"Only {dominant_votes} of 5 indicators agree — too weak, needs at least 3 for real confluence"],
            "price": round(float(latest["close"]), 2),
            "duration_minutes": 0,
            "duration_reason": "",
        }

    # Higher-timeframe check: this is now advisory, not blocking. It's a
    # newer, less-tested filter than the volatility floor above (which was
    # confirmed against real losses) — so instead of silently killing a
    # signal, it's flagged in the reasoning so the trade can still be
    # taken with that context in mind, rather than skipped automatically.
    htf_note = None
    if direction == "CALL" and htf_trend == "bearish":
        htf_note = "⚠️ Caution: this signal is against the 4H trend (which is bearish)"
    elif direction == "PUT" and htf_trend == "bullish":
        htf_note = "⚠️ Caution: this signal is against the 4H trend (which is bullish)"

    # 'score' is on a bullish scale (100=strong buy, 0=strong sell, 50=neutral).
    # 'confidence' mirrors it so it always reads as "how strong is the signal
    # in the direction shown" — a strong sell (score=20) should display as
    # high confidence (80), not a misleadingly low 20.
    confidence = score if direction == "CALL" else (100 - score)

    # Strength label: a clearer, single read than a 0-100 number, based on
    # how many of the 5 indicators genuinely agree (minimum 3 to fire at all).
    if dominant_votes >= 5:
        strength = "VERY STRONG"
    elif dominant_votes == 4:
        strength = "STRONG"
    else:
        strength = "MODERATE"

    if htf_note:
        reasons.append(htf_note)
    elif htf_trend in ("bullish", "bearish"):
        reasons.append(f"4H trend is {htf_trend} — agrees with this signal")

    duration_minutes, duration_reason = suggest_duration_minutes(latest)

    return {
        "direction": direction,
        "score": score,
        "confidence": confidence,
        "strength": strength,
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
