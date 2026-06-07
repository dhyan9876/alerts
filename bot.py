import asyncio
import csv
import math
import os
import logging
from datetime import datetime, timedelta, time
from pathlib import Path
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from price import get_quote, format_quote_symbol


# Load environment variables from .env file
load_dotenv()

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = None
chat_id_value = os.getenv("TELEGRAM_CHAT_ID")
if chat_id_value:
    try:
        TELEGRAM_CHAT_ID = int(chat_id_value)
    except ValueError:
        raise RuntimeError("TELEGRAM_CHAT_ID must be a numeric chat ID")

if not TELEGRAM_TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN must be set in .env file")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    chat_id = update.effective_chat.id if update.effective_chat else None
    if chat_id:
        context.application.bot_data["alert_chat_id"] = chat_id

    welcome_text = """
🤖 Welcome to Stock Price Bot!

Send me any stock symbol to get the current price. Examples:
• HDFCBANK
• TCS
• INFY
• RELIANCE
• NIFTY 50

Format: NSE:SYMBOL (or just SYMBOL, I'll add NSE: for you)
    """
    await update.message.reply_text(welcome_text)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    help_text = """
📋 Commands:
/start - Show welcome message
/help - Show this help message

Just send any stock symbol (e.g., HDFCBANK) and I'll fetch the price for you!
    """
    await update.message.reply_text(help_text)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming messages with stock symbols."""
    if update.effective_chat:
        context.application.bot_data["alert_chat_id"] = update.effective_chat.id

    user_message = update.message.text.strip()
    
    if not user_message:
        return

    try:
        # Get the quote using the price module
        symbol_code, data = get_quote(user_message)
        
        if not data:
            await update.message.reply_text(f"❌ No quote data found for {symbol_code}")
            return

        # Extract price information
        close_price = data.get("ohlc", {}).get("close")
        last_price = data.get("last_price")
        high = data.get("ohlc", {}).get("high")
        low = data.get("ohlc", {}).get("low")
        net_change = data.get("net_change")
        
        # Calculate change percentage if we have close price
        change_percent = None
        if close_price and close_price != 0:
            change_percent = (last_price - close_price) / close_price * 100 if last_price else None

        # Format response with safe None handling
        last_price_str = f"₹{last_price:,.2f}" if last_price is not None else "N/A"
        close_price_str = f"₹{close_price:,.2f}" if close_price is not None else "N/A"
        high_str = f"₹{high:,.2f}" if high is not None else "N/A"
        low_str = f"₹{low:,.2f}" if low is not None else "N/A"
        change_str = f"₹{net_change:,.2f}" if net_change is not None else "N/A"
        change_percent_str = f"{change_percent:.2f}%" if change_percent is not None else "N/A"

        response = f"""
💹 {symbol_code}

📊 Price Information:
• Last Price: {last_price_str}
• Previous Close: {close_price_str}
• High: {high_str}
• Low: {low_str}
• Net Change: {change_str} ({change_percent_str})
        """
        
        await update.message.reply_text(response)
        
    except Exception as e:
        logger.error(f"Error fetching quote for {user_message}: {str(e)}")
        await update.message.reply_text(f"❌ Error fetching price: {str(e)}")


def get_alert_chat_id(application: Application) -> int | None:
    return application.bot_data.get("alert_chat_id") or TELEGRAM_CHAT_ID


def load_stock_symbols(csv_path: str = "stocks.csv") -> list[str]:
    path = Path(csv_path)
    if not path.exists():
        logger.warning("stocks.csv not found at %s; defaulting to NIFTY 50", path)
        return ["NIFTY 50"]

    symbols: list[str] = []
    with path.open(newline="", encoding="utf-8") as csvfile:
        reader = csv.reader(csvfile)
        for row in reader:
            if not row:
                continue
            symbol = row[0].strip()
            if symbol and not symbol.startswith("#"):
                symbols.append(symbol)

    return symbols or ["NIFTY 50"]


async def check_and_send_threshold_alerts(application: Application) -> None:
    """Check stock prices and alert when crossing 1% threshold levels."""
    chat_id = get_alert_chat_id(application)
    if not chat_id:
        logger.warning("No alert chat ID available yet. Skipping threshold alert check.")
        return

    # Initialize threshold tracking state if not present
    if "stock_thresholds" not in application.bot_data:
        application.bot_data["stock_thresholds"] = {}
    if "stock_initialized" not in application.bot_data:
        application.bot_data["stock_initialized"] = set()

    symbols = application.bot_data.get("stock_symbols", ["NIFTY 50"])
    threshold_state = application.bot_data["stock_thresholds"]
    initialized_stocks = application.bot_data["stock_initialized"]

    for symbol in symbols:
        try:
            symbol_code, data = get_quote(symbol)
            
            if not data:
                logger.warning("No data for %s", symbol)
                continue

            last_price = data.get("last_price")
            close_price = data.get("ohlc", {}).get("close")

            if last_price is None or close_price is None or close_price == 0:
                logger.warning("Incomplete price data for %s", symbol)
                continue

            # Calculate 1% threshold step
            step = close_price * 0.01

            # Calculate how many 1% steps the price has moved from close
            price_diff = last_price - close_price
            if price_diff >= 0:
                steps_moved = math.floor(price_diff / step)
            else:
                steps_moved = math.ceil(price_diff / step)

            # Initialize state on first run, but do not alert on initialization
            if symbol not in initialized_stocks:
                threshold_state[symbol] = {
                    "positive": max(steps_moved, 0),
                    "negative": min(steps_moved, 0),
                }
                initialized_stocks.add(symbol)
                logger.info(f"Initialized {symbol_code} at {steps_moved} steps")
                continue

            if symbol not in threshold_state:
                threshold_state[symbol] = {"positive": 0, "negative": 0}

            stock_state = threshold_state[symbol]
            last_positive = stock_state["positive"]
            last_negative = stock_state["negative"]

            should_alert = False
            direction = ""

            if steps_moved > 0 and steps_moved > last_positive:
                should_alert = True
                direction = "⬆️ UP"
                stock_state["positive"] = steps_moved
            elif steps_moved < 0 and steps_moved < last_negative:
                should_alert = True
                direction = "⬇️ DOWN"
                stock_state["negative"] = steps_moved

            if should_alert:
                threshold_price = close_price + (steps_moved * step)
                change_amount = abs(price_diff)
                change_percent = (abs(price_diff) / close_price) * 100

                alert_message = (
                    f"🚨 THRESHOLD ALERT\n"
                    f"📊 {symbol_code}\n"
                    f"Direction: {direction}\n"
                    f"Current Price: ₹{last_price:,.2f}\n"
                    f"Prev Close: ₹{close_price:,.2f}\n"
                    f"Move: ₹{change_amount:,.2f} ({change_percent:.1f}%)\n"
                    f"Threshold Price: ₹{threshold_price:,.2f}\n"
                    f"Threshold Level: {abs(steps_moved)} × 1%\n"
                    f"Time: {datetime.now():%H:%M:%S}"
                )

                await application.bot.send_message(chat_id=chat_id, text=alert_message)
                logger.info(f"Alert sent for {symbol_code}: {steps_moved} steps at ₹{last_price:,.2f}")

        except Exception as e:
            logger.warning("Error checking threshold for %s: %s", symbol, e)


async def price_scheduler(application: Application) -> None:
    """Check stock thresholds every 5 minutes, aligned to 5-minute marks."""
    now = datetime.now()
    minutes_to_add = (5 - (now.minute % 5)) % 5
    if minutes_to_add == 0 and now.second > 0:
        minutes_to_add = 5

    target = now.replace(second=0, microsecond=0) + timedelta(minutes=minutes_to_add)
    delay = (target - now).total_seconds()
    await asyncio.sleep(delay)

    while True:
        try:
            await check_and_send_threshold_alerts(application)
        except Exception as e:
            logger.exception("Error while checking stock thresholds: %s", e)
        await asyncio.sleep(5 * 60)


async def post_init(application: Application) -> None:
    application.bot_data["stock_symbols"] = load_stock_symbols()
    application.create_task(price_scheduler(application))


def main() -> None:
    """Start the bot."""
    # Create the Application
    application = (
        Application.builder()
        .token(TELEGRAM_TOKEN)
        .post_init(post_init)
        .build()
    )

    # on different commands - answer in Telegram
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))

    # on non command i.e message - echo the message
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Run the bot until the user presses Ctrl-C
    print("🚀 Bot started! Press Ctrl-C to stop.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
