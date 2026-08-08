# Options Signal Bot (Telegram)

A starter bot that scans a watchlist, scores technical signals, and pushes
CALL/PUT alerts with a suggested near-the-money contract to a Telegram
chat or channel — every signal is logged so you can measure your **real**
win rate over time.

## Honest limits (read this first)

- No bot hits 80–100% accuracy on trading signals, ever. This one uses
  technical indicators (RSI, MACD, moving averages, Bollinger Bands,
  volume) to produce a 0–100 *confidence heuristic* — not a probability.
- Data comes from `yfinance`, which is free and unofficial. It's fine for
  building and testing. For a paid product or real-money use, swap in a
  paid provider — the rest of the code doesn't need to change if you keep
  the same function signatures in `data_fetch.py`.
- **This bot only sends signals — it never places trades for you.**
  For currency pairs, you manually execute the trade yourself on whatever
  platform you use (e.g. Pocket Option). This is intentional: platforms
  like Pocket Option don't offer an official API, and unofficial
  reverse-engineered ones risk your account being frozen or banned since
  they violate the platform's terms of service.
- **Weekend/OTC pairs aren't covered.** Pocket Option offers synthetic
  "OTC" versions of currency pairs that trade on weekends when real forex
  markets are closed. `yfinance` only has real market data, so this bot
  only produces signals when the actual underlying market is open
  (forex: Sunday evening–Friday evening UTC, roughly). Don't expect
  signals outside those hours.
- Binary-style trades (fixed short duration, fixed payout) have a
  different payout structure than traditional options — a payout under
  100% means you need a win rate meaningfully above 50% just to break
  even. Keep that math in mind before trusting any signal with real money.
- `tracker.py` logs every signal to a local SQLite database (`signals.db`).
  `check_outcomes.py` resolves them automatically — that's how you get an
  honest accuracy number to trust, instead of a marketing claim.

## Setup

1. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

2. Create your Telegram bot:
   - Message `@BotFather` on Telegram → `/newbot` → follow the prompts
   - Copy the token it gives you

3. Get your chat ID:
   - Public channel: use `@yourchannelname` directly
   - Private group: add the bot as admin, send a message in the group,
     then visit `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`
     and read the `chat.id` field

4. Copy `.env.example` to `.env` and fill in your values:
   ```
   cp .env.example .env
   ```

5. Run it:
   ```
   python main.py
   ```

## Files

| File | Purpose |
|---|---|
| `data_fetch.py` | Pulls price history + options chains |
| `signals.py` | Scores signals from technical indicators |
| `tracker.py` | Logs signals to SQLite for real accuracy tracking |
| `telegram_bot.py` | Formats and sends Telegram alerts |
| `check_outcomes.py` | Resolves pending signals as WIN/LOSS/FLAT once enough time has passed |
| `stats.py` | Prints (and can send to Telegram) your real accuracy report |
| `main.py` | Scheduler loop that ties it all together, including auto-resolving outcomes |

## How outcome tracking works

Every signal sent gets logged as `PENDING`. Every 10 minutes, `main.py`
automatically runs `check_outcomes.py`, which looks for signals older than
`OUTCOME_CHECK_MINUTES` (default 30) and checks the current price:

- CALL signal, price rose at least `OUTCOME_THRESHOLD_PCT` -> **WIN**
- CALL signal, price fell at least that much -> **LOSS**
- PUT signal, same logic reversed
- Move smaller than the threshold either way -> **FLAT** (no clear result)

Run `python stats.py` any time to see your real, resolved win rate --
add `--telegram` to also push the report to your channel:
```
python stats.py --telegram
```

Don't trust the percentage until you have at least 20-30 resolved
signals -- anything less is too small a sample to mean much.

## Next steps to make this production-ready

- Swap `yfinance` for a paid, rate-limit-friendly data provider
- Add per-user subscription logic if you plan to sell access
- Add backtesting against historical data before trusting any live signal
- Consider position sizing / risk rules if you extend this beyond alerts
  into actual order placement (not included here -- this bot only signals)
