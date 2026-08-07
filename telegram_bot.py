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
from telegram import Bot
from telegram.constants import ParseMode

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


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


async def send_signal(ticker: str, signal: dict, contract: dict = None, expiry: str = ""):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        raise RuntimeError("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set in environment")

    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    message = format_signal_message(ticker, signal, contract, expiry)
    await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message, parse_mode=ParseMode.MARKDOWN)


async def send_plain_message(text: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        raise RuntimeError("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set in environment")
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text)
