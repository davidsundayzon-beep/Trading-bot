"""
main.py
Orchestrates the whole bot: on a schedule, scans the watchlist, scores
signals, and pushes qualifying ones to Telegram. Logs every signal sent
so you can measure real accuracy later with tracker.py.

Run:
    python main.py
"""

import os
import asyncio
import logging
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import data_fetch
import signals
import tracker
import telegram_bot
import check_outcomes

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

WATCHLIST = [t.strip() for t in os.getenv("WATCHLIST", "AAPL,TSLA,SPY").split(",")]
SCAN_INTERVAL_MINUTES = int(os.getenv("SCAN_INTERVAL_MINUTES", "5"))
MIN_SIGNAL_SCORE = int(os.getenv("MIN_SIGNAL_SCORE", "65"))


async def scan_ticker(ticker: str):
    try:
        df = data_fetch.get_intraday_history(ticker, period="5d", interval="5m")
        signal = signals.score_signal(df)

        if signal["direction"] == "NO_TRADE":
            log.info(f"{ticker}: no qualifying signal (score={signal['score']})")
            return

        # Only act on strong-enough signals in either direction
        if signal["score"] < MIN_SIGNAL_SCORE and signal["score"] > (100 - MIN_SIGNAL_SCORE):
            log.info(f"{ticker}: signal too weak (score={signal['score']})")
            return

        calls, puts, expiry = data_fetch.get_options_chain(ticker)
        contract = signals.pick_option_contract(calls, puts, signal["direction"], signal["price"])

        tracker.log_signal(
            ticker=ticker,
            direction=signal["direction"],
            score=signal["score"],
            price_at_signal=signal["price"],
            contract=contract,
        )

        await telegram_bot.send_signal(ticker, signal, contract, expiry)
        log.info(f"{ticker}: signal sent — {signal['direction']} score={signal['score']}")

    except Exception as e:
        log.error(f"{ticker}: error during scan — {e}")


async def scan_all():
    log.info(f"Scanning watchlist: {WATCHLIST}")
    for ticker in WATCHLIST:
        await scan_ticker(ticker)


async def main():
    tracker.init_db()
    log.info("Options signal bot starting up.")
    log.info(f"Watchlist: {WATCHLIST} | Interval: {SCAN_INTERVAL_MINUTES}m | Min score: {MIN_SIGNAL_SCORE}")

    scheduler = AsyncIOScheduler()
    scheduler.add_job(scan_all, "interval", minutes=SCAN_INTERVAL_MINUTES)
    # Check pending signals for resolution every 10 minutes
    scheduler.add_job(check_outcomes.run_check, "interval", minutes=10)
    scheduler.start()

    # Run one scan immediately on startup
    await scan_all()
    check_outcomes.run_check()

    # Keep the event loop alive
    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.run(main())
