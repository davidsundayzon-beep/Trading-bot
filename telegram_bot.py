"""
telegram_bot.py
Sends formatted signal alerts to a Telegram chat/channel.

Setup:
1. Message @BotFather on Telegram, run /newbot, follow prompts.
2. Copy the token it gives you into .env as TELEGRAM_BOT_TOKEN.
3. Add your bot to your channel/group as admin, then get the chat ID:
   - For a public channel: use "@yourchannelname" directly as TELEGRAM_CHAT_ID.
   - For a private group: send a message in the group, then visit
     https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates
     and read the "chat":{"id": ...} value.
"""

import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from telegram import Bot
from telegram.constants import ParseMode

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Signals are shown in this timezone for readability. Change if your
# audience is elsewhere — this defaults to Lagos (WAT, UTC+1, no DST).
DISPLAY_TIMEZONE = ZoneInfo("Africa/Lagos")

CURRENCY_FLAGS = {
    "EUR": "🇪🇺", "USD": "🇺🇸", "GBP": "🇬🇧", "JPY": "🇯🇵",
    "CHF": "🇨🇭", "AUD": "🇦🇺", "CAD": "🇨🇦", "NZD": "🇳🇿",
}


def flagged_pair(pair_display: str) -> str:
    """Turn 'EUR/USD' into '🇪🇺 EUR / 🇺🇸 USD'."""
    if "/" not in pair_display:
        return pair_display
    base, quote = pair_display.split("/")
    base_flag = CURRENCY_FLAGS.get(base, "")
    quote_flag = CURRENCY_FLAGS.get(quote, "")
    return f"{base_flag} {base} / {quote_flag} {quote}".strip()


def format_signal_message(ticker: str, signal: dict, contract: dict, expiry: str) -> str:
    direction_emoji = "🟢 CALL" if signal["direction"] == "CALL" else "🔴 PUT"

    reasons_text = "\n".join(f"• {r}" for r in signal["reasons"])

    contract_text = ""
    if contract:
        contract_text = (
            f"\n\n*Suggested Contract*\n"
            f"Strike: {contract.get('strike')}\n"
            f"Expiry: {expiry}\n"
            f"Bid/Ask: {contract.get('bid')} / {contract.get('ask')}\n"
            f"Volume: {contract.get('volume')}  OI: {contract.get('openInterest')}\n"
            f"IV: {round(contract.get('impliedVolatility', 0) * 100, 1)}%"
        )

    return (
        f"*{ticker}* — {direction_emoji}\n"
        f"Confidence score: {signal['score']}/100 (heuristic, not a probability)\n"
        f"Underlying price: ${signal['price']}\n\n"
        f"*Reasoning*\n{reasons_text}"
        f"{contract_text}\n\n"
        f"_This is a technical-analysis heuristic, not a guarantee. "
        f"Always size positions to what you can afford to lose._"
    )


def format_forex_signal_message(pair_display: str, signal: dict) -> str:
    """
    Format a signal for a currency pair (no options contract attached).
    Meant for manual execution on a platform like Pocket Option — this bot
    does not place trades for you. Deliberately does NOT suggest Martingale
    (increasing stake after a loss) — that's a fast way to blow up an
    account, no matter how confident a signal looks.
    """
    direction_emoji = "🟢 BUY" if signal["direction"] == "CALL" else "🔴 SELL"
    reasons_text = "\n".join(f"• {r}" for r in signal["reasons"])

    now_local = datetime.now(timezone.utc).astimezone(DISPLAY_TIMEZONE)
    window_start = now_local + timedelta(minutes=2)
    window_end = now_local + timedelta(minutes=4)

    duration = signal.get("duration_minutes", 5)
    duration_reason = signal.get("duration_reason", "")
    exit_time = window_end + timedelta(minutes=duration)
    tz_label = now_local.tzname()  # e.g. "WAT"

    entry_window = f"{window_start.strftime('%H:%M')}–{window_end.strftime('%H:%M')} {tz_label}"
    exit_window = f"~{exit_time.strftime('%H:%M')} {tz_label}"

    return (
        f"📊 {flagged_pair(pair_display)} (real market, not OTC)\n"
        f"🕒 Entry window: {entry_window}\n"
        f"⏱️ Suggested duration: {duration} min (exit around {exit_window})\n"
        f"   _{duration_reason}_\n"
        f"🤖 Confidence: {signal['score']}/100 (heuristic, not a probability)\n"
        f"Direction: {direction_emoji}\n"
        f"Current price: {signal['price']}\n\n"
        f"*Reasoning*\n{reasons_text}\n\n"
        f"*Risk guidance*\n"
        f"Use a flat stake sized to what you can afford to lose "
        f"(e.g. 1–2% of your balance). Do not increase your stake after a "
        f"loss to try to catch up — that pattern (Martingale) turns one bad "
        f"streak into a wipeout, regardless of signal confidence.\n\n"
        f"_This is a technical-analysis heuristic, not a guarantee of outcome. "
        f"Manually place any trade yourself — this bot does not execute trades._"
    )


async def send_signal(ticker: str, signal: dict, contract: dict = None, expiry: str = ""):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        raise RuntimeError("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set in environment")

    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    message = format_signal_message(ticker, signal, contract, expiry)
    await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message, parse_mode=ParseMode.MARKDOWN)


async def send_forex_signal(pair_display: str, signal: dict):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        raise RuntimeError("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set in environment")

    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    message = format_forex_signal_message(pair_display, signal)
    await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message, parse_mode=ParseMode.MARKDOWN)


async def send_plain_message(text: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        raise RuntimeError("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set in environment")
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text)
