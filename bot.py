import asyncio
import csv
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


def build_compact_price_lines(symbols: list[str]) -> list[str]:
    lines: list[str] = []
    for symbol in symbols:
        try:
            symbol_code, data = get_quote(symbol)
            last_price = data.get("last_price")
            close_price = data.get("ohlc", {}).get("close")
            if last_price is not None and close_price:
                change_percent = (last_price - close_price) / close_price * 100
                arrow = "↑" if change_percent >= 0 else "↓"
                lines.append(f"{symbol_code.ljust(12)} ₹{last_price:,.2f} {arrow}{abs(change_percent):.2f}%")
            elif last_price is not None:
                lines.append(f"{symbol_code.ljust(12)} ₹{last_price:,.2f}")
            else:
                lines.append(f"{symbol_code.ljust(12)} N/A")
        except Exception as e:
            logger.warning("Failed to fetch quote for %s: %s", symbol, e)
            normalized = symbol.strip().upper()
            lines.append(f"{normalized.ljust(12)} ERR")
    return lines


def chunk_messages(header: str, lines: list[str], max_chars: int = 3900) -> list[str]:
    messages: list[str] = []
    current = header
    for line in lines:
        candidate = f"{current}{line}\n"
        if len(candidate) > max_chars:
            messages.append(current.rstrip())
            current = f"{header}{line}\n"
        else:
            current = candidate
    if current.strip():
        messages.append(current.rstrip())
    return messages


async def send_stock_prices(application: Application) -> None:
    """Send compact price updates for all symbols loaded from stocks.csv."""
    chat_id = get_alert_chat_id(application)
    if not chat_id:
        logger.warning("No alert chat ID available yet. Skipping scheduled price alert.")
        return

    symbols = application.bot_data.get("stock_symbols", ["NIFTY 50"])
    lines = build_compact_price_lines(symbols)
    header = f"📈 Stock price update\n{datetime.now():%Y-%m-%d %H:%M:%S}\n\n"
    messages = chunk_messages(header, lines)

    for message in messages:
        await application.bot.send_message(chat_id=chat_id, text=message)


async def price_scheduler(application: Application) -> None:
    """Send stock prices every 5 minutes, aligned to 5-minute marks."""
    now = datetime.now()
    minutes_to_add = (5 - (now.minute % 5)) % 5
    if minutes_to_add == 0 and now.second > 0:
        minutes_to_add = 5

    target = now.replace(second=0, microsecond=0) + timedelta(minutes=minutes_to_add)
    delay = (target - now).total_seconds()
    await asyncio.sleep(delay)

    while True:
        try:
            await send_stock_prices(application)
        except Exception as e:
            logger.exception("Error while sending scheduled stock prices: %s", e)
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
