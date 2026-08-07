"""
tracker.py
Logs every signal the bot sends, so you can measure REAL accuracy over time
instead of claiming a number. This is the single most important file if
you ever plan to sell access to this bot — it's your proof.
"""

import sqlite3
from datetime import datetime

DB_PATH = "signals.db"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT,
            direction TEXT,
            score INTEGER,
            price_at_signal REAL,
            contract_symbol TEXT,
            strike REAL,
            timestamp TEXT,
            outcome TEXT DEFAULT 'PENDING',
            price_after REAL,
            checked_at TEXT
        )
    """)
    conn.commit()
    conn.close()


def log_signal(ticker, direction, score, price_at_signal, contract=None):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """INSERT INTO signals
           (ticker, direction, score, price_at_signal, contract_symbol, strike, timestamp)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            ticker,
            direction,
            score,
            price_at_signal,
            contract.get("contractSymbol") if contract else None,
            contract.get("strike") if contract else None,
            datetime.utcnow().isoformat(),
        ),
    )
    conn.commit()
    conn.close()


def update_outcome(signal_id, outcome, price_after):
    """outcome should be 'WIN', 'LOSS', or 'FLAT'."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "UPDATE signals SET outcome=?, price_after=?, checked_at=? WHERE id=?",
        (outcome, price_after, datetime.utcnow().isoformat(), signal_id),
    )
    conn.commit()
    conn.close()


def get_accuracy_stats():
    """Returns real historical win rate from logged, resolved signals."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute(
        "SELECT outcome, COUNT(*) FROM signals WHERE outcome != 'PENDING' GROUP BY outcome"
    )
    rows = dict(cur.fetchall())
    conn.close()

    total = sum(rows.values())
    wins = rows.get("WIN", 0)
    accuracy = (wins / total * 100) if total else 0
    return {"total_resolved": total, "wins": wins, "accuracy_pct": round(accuracy, 1)}


if __name__ == "__main__":
    init_db()
    print("Database initialized:", DB_PATH)
    print(get_accuracy_stats())
