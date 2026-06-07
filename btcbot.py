import asyncio
import os
from decimal import Decimal, ROUND_DOWN
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv
from telegram import Bot
from telegram.request import HTTPXRequest

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = int(os.getenv("TELEGRAM_CHAT_ID", "0"))

if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
    raise RuntimeError("TELEGRAM_TOKEN and TELEGRAM_CHAT_ID must be set in .env file")

POLL_INTERVAL = 30

COINS = {
    "BTC":  {"symbol": "BTCUSDT",  "step": Decimal("100"),  "name": "Bitcoin"},
    "ETH":  {"symbol": "ETHUSDT",  "step": Decimal("3"),    "name": "Ethereum"},
    "BNB":  {"symbol": "BNBUSDT",  "step": Decimal("1"),    "name": "Binance Coin"},
    "SOL":  {"symbol": "SOLUSDT",  "step": Decimal("0.5"),  "name": "Solana"},
    "UNI":  {"symbol": "UNIUSDT",  "step": Decimal("0.1"),  "name": "Uniswap"},
    "AAVE": {"symbol": "AAVEUSDT", "step": Decimal("0.1"),  "name": "AAVE"},
}


def fetch_prices() -> dict:
    response = requests.get(
        "https://api.binance.com/api/v3/ticker/price",
        timeout=10,
    )
    response.raise_for_status()
    data = response.json()
    symbols_needed = {cfg["symbol"] for cfg in COINS.values()}
    return {item["symbol"]: Decimal(item["price"]) for item in data if item["symbol"] in symbols_needed}


def price_to_level(price: Decimal, step: Decimal) -> Decimal:
    return (price / step).to_integral_value(rounding=ROUND_DOWN) * step


async def check_and_alert(bot: Bot, states: dict) -> None:
    try:
        prices = fetch_prices()
        now_utc = datetime.now(timezone.utc)
        time_str = now_utc.strftime("%H:%M UTC")
        today_str = now_utc.strftime("%Y-%m-%d")

        for ticker, cfg in COINS.items():
            price = prices.get(cfg["symbol"])
            if price is None:
                continue

            current_level = price_to_level(price, cfg["step"])
            state = states[ticker]

            # Reset list at midnight for new day
            if state["today"] != today_str:
                state["today"] = today_str
                state["alerts"] = []
                state["last_level"] = None

            if state["last_level"] is None:
                state["last_level"] = current_level
                continue

            if current_level != state["last_level"]:
                is_up = current_level > state["last_level"]
                emoji = "🟢" if is_up else "🔴"

                state["alerts"].append(f"{emoji}  {current_level}  {time_str}")
                state["last_level"] = current_level

                message = f"{ticker} ALERTS — {today_str}\n" + "\n".join(state["alerts"])
                await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
                print(f"[ALERT] {ticker} {emoji} {current_level} at {time_str}")

    except Exception as e:
        print(f"[ERROR] {e}")


async def main():
    request = HTTPXRequest(connect_timeout=30, read_timeout=30, write_timeout=30)
    async with Bot(token=TELEGRAM_TOKEN, request=request) as bot:
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        states = {
            ticker: {"last_level": None, "alerts": [], "today": today_str}
            for ticker in COINS
        }
        print("Crypto alert bot running. Polling every 30s... (Ctrl+C to stop)")

        while True:
            await check_and_alert(bot, states)
            await asyncio.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    asyncio.run(main())
