import asyncio
import os
from datetime import datetime, timedelta, time

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, ContextTypes

from price import get_quote

# Load environment variables from .env file
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if not TELEGRAM_TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN must be set in .env file")

if not TELEGRAM_CHAT_ID:
    raise RuntimeError("TELEGRAM_CHAT_ID must be set in .env file")


async def send_nifty_price(bot_application: Application) -> None:
    """Fetch Nifty 50 and send the price to the configured Telegram chat."""
    symbol_code, data = get_quote("NIFTY 50")

    if not data:
        message = "❌ Unable to fetch Nifty 50 price at this time."
    else:
        last_price = data.get("last_price")
        close_price = data.get("ohlc", {}).get("close")
        high_price = data.get("ohlc", {}).get("high")
        low_price = data.get("ohlc", {}).get("low")

        last_price_str = f"₹{last_price:,.2f}" if last_price is not None else "N/A"
        close_price_str = f"₹{close_price:,.2f}" if close_price is not None else "N/A"
        high_price_str = f"₹{high_price:,.2f}" if high_price is not None else "N/A"
        low_price_str = f"₹{low_price:,.2f}" if low_price is not None else "N/A"

        message = (
            f"📈 Nifty 50 price update at 7:00 PM\n"
            f"Symbol: {symbol_code}\n"
            f"Last Price: {last_price_str}\n"
            f"Previous Close: {close_price_str}\n"
            f"High: {high_price_str}\n"
            f"Low: {low_price_str}"
        )

    await bot_application.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)


async def daily_alert_scheduler(application: Application) -> None:
    """Run the Nifty 50 alert every day at 7:00 PM local time."""
    while True:
        now = datetime.now()
        target = datetime.combine(now.date(), time(hour=19, minute=0))
        if now >= target:
            target += timedelta(days=1)

        delay = (target - now).total_seconds()
        await asyncio.sleep(delay)
        await send_nifty_price(application)


async def post_init(application: Application) -> None:
    """Schedule the daily alert after the bot has started."""
    application.create_task(daily_alert_scheduler(application))


def main() -> None:
    """Start the Telegram bot and schedule the daily 7:00 PM price alert."""
    application = (
        Application.builder()
        .token(TELEGRAM_TOKEN)
        .post_init(post_init)
        .build()
    )

    print("🚀 Alert bot started. Scheduled Nifty 50 price alert at 19:00 local time.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
