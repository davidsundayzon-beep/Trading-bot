"""
stats.py
Prints a readable accuracy report from logged signals. Run any time you
want to check how the bot is actually performing.

    python stats.py

Optional: pass --telegram to also push the report to your Telegram chat.
"""

import sys
import asyncio
import sqlite3
import tracker
import telegram_bot
from dotenv import load_dotenv

load_dotenv()


def build_report() -> str:
    tracker.init_db()
    overall = tracker.get_accuracy_stats()

    conn = sqlite3.connect(tracker.DB_PATH)
    cur = conn.execute(
        """SELECT ticker,
                  SUM(CASE WHEN outcome='WIN' THEN 1 ELSE 0 END) as wins,
                  SUM(CASE WHEN outcome IN ('WIN','LOSS') THEN 1 ELSE 0 END) as resolved
           FROM signals
           GROUP BY ticker"""
    )
    per_ticker = cur.fetchall()

    pending = conn.execute(
        "SELECT COUNT(*) FROM signals WHERE outcome='PENDING'"
    ).fetchone()[0]
    conn.close()

    lines = [
        "📊 Signal Bot Accuracy Report",
        "",
        f"Resolved signals: {overall['total_resolved']}",
        f"Wins: {overall['wins']}",
        f"Real accuracy: {overall['accuracy_pct']}%",
        f"Still pending (not yet resolved): {pending}",
        "",
        "By ticker:",
    ]

    for tkr, wins, resolved in per_ticker:
        if resolved:
            pct = round(wins / resolved * 100, 1)
            lines.append(f"  {tkr}: {wins}/{resolved} ({pct}%)")
        else:
            lines.append(f"  {tkr}: no resolved signals yet")

    if overall["total_resolved"] < 20:
        lines.append("")
        lines.append(
            "⚠️ Sample size is small — treat this number as noisy until "
            "you have at least 20-30 resolved signals."
        )

    return "\n".join(lines)


if __name__ == "__main__":
    report = build_report()
    print(report)

    if "--telegram" in sys.argv:
        asyncio.run(telegram_bot.send_plain_message(report))
        print("\n(Report also sent to Telegram.)")
