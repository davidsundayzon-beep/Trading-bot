"""
check_outcomes.py
Goes through PENDING signals in the database that are old enough to
evaluate, checks the current price, and marks each one WIN / LOSS / FLAT.
This is what turns the bot's internal "confidence score" into a real,
provable accuracy number over time.

Logic:
- CALL signal is a WIN if price rose by at least OUTCOME_THRESHOLD_PCT
- PUT signal is a WIN if price fell by at least OUTCOME_THRESHOLD_PCT
- Otherwise LOSS, unless the move was smaller than the threshold in either
  direction, in which case it's marked FLAT (no clear win or loss)

Run this periodically (main.py already schedules it automatically, or you
can run it manually / via cron):
    python check_outcomes.py
"""

import os
import sqlite3
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv

import data_fetch
import tracker

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

OUTCOME_CHECK_MINUTES = int(os.getenv("OUTCOME_CHECK_MINUTES", "30"))
OUTCOME_THRESHOLD_PCT = float(os.getenv("OUTCOME_THRESHOLD_PCT", "0.3"))  # percent move


def get_resolvable_signals():
    """Return pending signals old enough to check (older than OUTCOME_CHECK_MINUTES)."""
    conn = sqlite3.connect(tracker.DB_PATH)
    cutoff = (datetime.utcnow() - timedelta(minutes=OUTCOME_CHECK_MINUTES)).isoformat()
    cur = conn.execute(
        """SELECT id, ticker, direction, price_at_signal, timestamp
           FROM signals
           WHERE outcome = 'PENDING' AND timestamp <= ?""",
        (cutoff,),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def evaluate_outcome(direction, price_at_signal, price_now):
    pct_move = (price_now - price_at_signal) / price_at_signal * 100

    if direction == "CALL":
        if pct_move >= OUTCOME_THRESHOLD_PCT:
            return "WIN"
        elif pct_move <= -OUTCOME_THRESHOLD_PCT:
            return "LOSS"
        else:
            return "FLAT"
    else:  # PUT
        if pct_move <= -OUTCOME_THRESHOLD_PCT:
            return "WIN"
        elif pct_move >= OUTCOME_THRESHOLD_PCT:
            return "LOSS"
        else:
            return "FLAT"


def run_check():
    tracker.init_db()
    resolvable = get_resolvable_signals()

    if not resolvable:
        log.info("No signals ready to resolve yet.")
        return

    log.info(f"Resolving {len(resolvable)} pending signal(s)...")

    for signal_id, ticker_symbol, direction, price_at_signal, timestamp in resolvable:
        try:
            df = data_fetch.get_intraday_history(ticker_symbol, period="1d", interval="1m")

            if data_fetch.is_data_stale(df, max_age_minutes=20):
                log.info(f"#{signal_id} {ticker_symbol}: price data is stale — leaving PENDING, will retry later")
                continue

            price_now = float(df["close"].iloc[-1])
            outcome = evaluate_outcome(direction, price_at_signal, price_now)
            tracker.update_outcome(signal_id, outcome, price_now)
            log.info(
                f"#{signal_id} {ticker_symbol} {direction}: "
                f"{price_at_signal} -> {price_now} = {outcome}"
            )
        except Exception as e:
            log.error(f"#{signal_id} {ticker_symbol}: failed to resolve — {e}")


if __name__ == "__main__":
    run_check()
