import asyncio
import csv
import os
from decimal import Decimal, ROUND_FLOOR
from datetime import datetime, timezone, timedelta

import requests
from dotenv import load_dotenv
from telegram import Bot
from telegram.request import HTTPXRequest

from cryptopastalert import fill_gaps, alerts_file, get_last_entry

load_dotenv()

TELEGRAM_TOKEN = os.getenv("CRYPTO_TOKEN")
TELEGRAM_CHAT_ID = int(os.getenv("CRYPTO_CHAT_ID", "0"))

if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
    raise RuntimeError("CRYPTO_TOKEN and CRYPTO_CHAT_ID must be set in .env file")

POLL_INTERVAL = 30
ALERTS_PER_PART = 40
IST = timezone(timedelta(hours=5, minutes=30))


def load_coins(csv_path: str = "crypto.csv") -> dict:
    coins = {}
    with open(csv_path, newline="") as f:
        for row in csv.reader(f):
            symbol, base, step = row[0].strip(), row[1].strip(), row[2].strip()
            ticker = symbol.replace("USDT", "")
            coins[ticker] = {"symbol": symbol, "base": Decimal(base), "step": Decimal(step)}
    return coins


def fetch_prices(coins: dict) -> dict:
    response = requests.get(
        "https://api.binance.com/api/v3/ticker/price",
        timeout=10,
    )
    response.raise_for_status()
    data = response.json()
    symbols_needed = {cfg["symbol"] for cfg in coins.values()}
    return {item["symbol"]: Decimal(item["price"]) for item in data if item["symbol"] in symbols_needed}


def price_to_level(price: Decimal, base: Decimal, step: Decimal) -> Decimal:
    return ((price - base) / step).to_integral_value(rounding=ROUND_FLOOR) * step + base


def append_to_log(ticker: str, level: Decimal, direction: str, dt_ist: datetime) -> None:
    path = alerts_file(ticker)
    file_exists = os.path.exists(path)
    with open(path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["date", "time", "level", "direction"])
        if not file_exists:
            writer.writeheader()
        writer.writerow({
            "date": dt_ist.strftime("%Y-%m-%d"),
            "time": dt_ist.strftime("%H:%M:%S"),
            "level": str(level),
            "direction": direction,
        })


def load_all_alerts(ticker: str) -> tuple:
    """Read ALL alerts from CSV (all dates). Returns (current_part_alerts, part_number)."""
    path = alerts_file(ticker)
    if not os.path.exists(path):
        return [], 1
    all_alerts = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            emoji = "🟢" if row["direction"] == "up" else "🔴"
            time_str = datetime.strptime(row["time"], "%H:%M:%S").strftime("%H:%M IST")
            date_str = datetime.strptime(row["date"], "%Y-%m-%d").strftime("%d %b")
            all_alerts.append(f"{emoji}  {row['level']}  {time_str} {date_str}")
    if not all_alerts:
        return [], 1
    part = (len(all_alerts) - 1) // ALERTS_PER_PART + 1
    start_idx = (part - 1) * ALERTS_PER_PART
    return all_alerts[start_idx:], part


async def send_initial_alerts(bot: Bot, states: dict, tickers_with_new: set) -> None:
    """On startup, send full alert history for coins that had new gap-fill data."""
    for ticker in tickers_with_new:
        alerts = states[ticker]["alerts"]
        if not alerts:
            continue
        part = states[ticker]["part"]
        part_label = f" (Part {part})" if part > 1 else ""
        message = f"{ticker} ALERTS{part_label}\n" + "\n".join(alerts)
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        await asyncio.sleep(0.5)


async def check_and_alert(bot: Bot, states: dict, coins: dict) -> None:
    try:
        prices = fetch_prices(coins)
        now_ist = datetime.now(IST)
        time_str = now_ist.strftime("%H:%M IST %d %b")
        today_str = now_ist.strftime("%Y-%m-%d")

        for ticker, cfg in coins.items():
            price = prices.get(cfg["symbol"])
            if price is None:
                continue

            current_level = price_to_level(price, cfg["base"], cfg["step"])
            state = states[ticker]

            if state["today"] != today_str:
                state["today"] = today_str
                state["last_level"] = None
                state["last_display_level"] = None

            if state["last_level"] is None:
                state["last_level"] = current_level
                continue

            if current_level != state["last_level"]:
                is_up = current_level > state["last_level"]
                emoji = "🟢" if is_up else "🔴"
                direction = "up" if is_up else "down"
                display_level = current_level if is_up else current_level + cfg["step"]

                state["last_level"] = current_level
                if display_level == state["last_display_level"]:
                    continue
                state["last_display_level"] = display_level
                state["alerts"].append(f"{emoji}  {display_level}  {time_str}")

                append_to_log(ticker, display_level, direction, now_ist)

                if len(state["alerts"]) > ALERTS_PER_PART:
                    state["alerts"] = [f"{emoji}  {display_level}  {time_str}"]
                    state["part"] += 1

                part_label = f" (Part {state['part']})" if state["part"] > 1 else ""
                message = f"{ticker} ALERTS{part_label}\n" + "\n".join(state["alerts"])
                await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
                print(f"[ALERT] {ticker} {emoji} {display_level} at {time_str}")

    except Exception as e:
        print(f"[ERROR] {e}")


async def main():
    request = HTTPXRequest(connect_timeout=60, read_timeout=60, write_timeout=60, pool_timeout=60)

    while True:
        try:
            coins = load_coins()
            new_alerts = fill_gaps(coins)

            today_str = datetime.now(IST).strftime("%Y-%m-%d")
            states = {}
            for ticker in coins:
                all_alerts, all_part = load_all_alerts(ticker)
                states[ticker] = {
                    "last_level": None,
                    "last_display_level": None,
                    "alerts": all_alerts,
                    "part": all_part,
                    "today": today_str,
                }

            tickers_with_new = {ticker for ticker, lines in new_alerts.items() if lines}

            for ticker in coins:
                last = get_last_entry(ticker)
                if last:
                    states[ticker]["last_display_level"] = Decimal(last[2])

            async with Bot(token=TELEGRAM_TOKEN, request=request) as bot:
                await send_initial_alerts(bot, states, tickers_with_new)
                print("Crypto alert bot running. Polling every 30s... (Ctrl+C to stop)")

                while True:
                    await check_and_alert(bot, states, coins)
                    await asyncio.sleep(POLL_INTERVAL)

        except KeyboardInterrupt:
            print("Bot stopped.")
            break
        except Exception as e:
            print(f"[RECONNECTING] {e} — retrying in 10s...")
            await asyncio.sleep(10)


if __name__ == "__main__":
    asyncio.run(main())
