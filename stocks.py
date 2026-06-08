import asyncio
import csv
import os
from decimal import Decimal, ROUND_FLOOR
from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv
from telegram import Bot
from telegram.request import HTTPXRequest

from login import get_kite_instance

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = int(os.getenv("TELEGRAM_CHAT_ID", "0"))

if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
    raise RuntimeError("TELEGRAM_TOKEN and TELEGRAM_CHAT_ID must be set in .env file")

print(f"Using TELEGRAM_CHAT_ID: {TELEGRAM_CHAT_ID}")

POLL_INTERVAL = 60
ALERTS_PER_PART = 20
IST = timezone(timedelta(hours=5, minutes=30))


def load_stocks() -> dict:
    if not os.path.exists("last_base.csv"):
        print("last_base.csv not found — generating from previous day's data...")
        from lastalert import generate_last_base
        generate_last_base()

    stocks = {}
    with open("last_base.csv", newline="") as f:
        for row in csv.reader(f):
            if not row or len(row) < 3:
                continue
            symbol, base, step = row[0].strip(), row[1].strip(), row[2].strip()
            stocks[symbol] = {
                "instrument": f"NSE:{symbol}",
                "base": Decimal(base),
                "step": Decimal(step),
            }
    return stocks


STOCKS = load_stocks()


def fetch_prices(kite) -> dict:
    instruments = [cfg["instrument"] for cfg in STOCKS.values()]
    ltp_data = kite.ltp(instruments)
    return {
        symbol: Decimal(str(ltp_data[cfg["instrument"]]["last_price"]))
        for symbol, cfg in STOCKS.items()
        if cfg["instrument"] in ltp_data
    }


def price_to_level(price: Decimal, base: Decimal, step: Decimal) -> Decimal:
    return ((price - base) / step).to_integral_value(rounding=ROUND_FLOOR) * step + base


async def check_and_alert(bot: Bot, kite, states: dict) -> None:
    try:
        prices = fetch_prices(kite)
        now_ist = datetime.now(IST)
        time_str = now_ist.strftime("%H:%M IST")
        today_str = now_ist.strftime("%Y-%m-%d")

        for symbol, cfg in STOCKS.items():
            price = prices.get(symbol)
            if price is None:
                continue

            current_level = price_to_level(price, cfg["base"], cfg["step"])
            state = states[symbol]

            if state["today"] != today_str:
                state["today"] = today_str
                state["alerts"] = []
                state["part"] = 1
                state["last_level"] = None
                state["last_display_level"] = cfg["base"]

            if state["last_level"] is None:
                state["last_level"] = current_level
                continue

            if current_level != state["last_level"]:
                is_up = current_level > state["last_level"]
                emoji = "🟢" if is_up else "🔴"

                display_level = current_level if is_up else current_level + cfg["step"]
                state["last_level"] = current_level

                if display_level == state["last_display_level"]:
                    continue

                state["last_display_level"] = display_level
                state["alerts"].append(f"{emoji}  {display_level}  {time_str}")

                if len(state["alerts"]) > ALERTS_PER_PART:
                    state["alerts"] = [f"{emoji}  {display_level}  {time_str}"]
                    state["part"] += 1

                part_label = f" (Part {state['part']})" if state["part"] > 1 else ""
                header = f"{symbol} ALERTS — {today_str}{part_label}\nLast Base: {cfg['base']} | Alert Diff: {cfg['step']}"
                message = header + "\n" + "\n".join(state["alerts"])
                await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
                print(f"[ALERT] {symbol} {emoji} {display_level} at {time_str}")

    except Exception as e:
        print(f"[ERROR] {e}")


async def main():
    kite = get_kite_instance()
    request = HTTPXRequest(connect_timeout=60, read_timeout=60, write_timeout=60, pool_timeout=60)
    today_str = datetime.now(IST).strftime("%Y-%m-%d")
    states = {
        symbol: {"last_level": None, "last_display_level": cfg["base"], "alerts": [], "part": 1, "today": today_str}
        for symbol, cfg in STOCKS.items()
    }

    while True:
        try:
            async with Bot(token=TELEGRAM_TOKEN, request=request) as bot:
                print("Stock alert bot running. Polling every 60s... (Ctrl+C to stop)")

                while True:
                    await check_and_alert(bot, kite, states)
                    await asyncio.sleep(POLL_INTERVAL)

        except KeyboardInterrupt:
            print("Bot stopped.")
            break
        except Exception as e:
            print(f"[RECONNECTING] {e} — retrying in 10s...")
            await asyncio.sleep(10)


if __name__ == "__main__":
    asyncio.run(main())
