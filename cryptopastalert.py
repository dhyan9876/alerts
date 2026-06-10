import csv
import os
import time
from decimal import Decimal, ROUND_FLOOR
from datetime import datetime, timezone, timedelta

import requests
from dotenv import load_dotenv

load_dotenv()

IST = timezone(timedelta(hours=5, minutes=30))
ALERTS_DIR = "sub_alerts"
CRYPTO_START_DATE = os.getenv("CRYPTO_START_DATE", "2026-06-01")


def alerts_file(ticker: str) -> str:
    os.makedirs(ALERTS_DIR, exist_ok=True)
    return os.path.join(ALERTS_DIR, f"{ticker}.csv")


def load_coins(csv_path="crypto.csv"):
    coins = {}
    with open(csv_path, newline="") as f:
        for row in csv.reader(f):
            symbol, base, step = row[0].strip(), row[1].strip(), row[2].strip()
            ticker = symbol.replace("USDT", "")
            coins[ticker] = {"symbol": symbol, "base": Decimal(base), "step": Decimal(step)}
    return coins


def price_to_level(price, base, step):
    return ((price - base) / step).to_integral_value(rounding=ROUND_FLOOR) * step + base


def fetch_klines(symbol, start_ms, end_ms):
    """Fetch 1-min klines from Binance with pagination. 0.3s delay between pages to avoid rate limit."""
    all_klines = []
    url = "https://api.binance.com/api/v3/klines"
    current_start = start_ms
    while current_start < end_ms:
        params = {
            "symbol": symbol,
            "interval": "1m",
            "startTime": current_start,
            "endTime": end_ms,
            "limit": 1000,
        }
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if not data:
            break
        all_klines.extend(data)
        current_start = data[-1][0] + 60000
        if len(data) < 1000:
            break
        time.sleep(0.3)
    return all_klines


def get_last_entry(ticker):
    """Return (date, time, level, direction) of last entry in sub_alerts/{ticker}.csv, or None."""
    path = alerts_file(ticker)
    if not os.path.exists(path):
        return None
    last_row = None
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            last_row = row
    if last_row is None:
        return None
    return (last_row["date"], last_row["time"], last_row["level"], last_row["direction"])


def reconstruct_alerts(klines, base, step, initial_display_level=None):
    """Walk klines using close price, return list of (datetime_ist, display_level, direction)."""
    alerts = []
    last_level = None
    last_display_level = initial_display_level
    for k in klines:
        close_price = Decimal(k[4])
        dt_ist = datetime.fromtimestamp(k[0] / 1000, tz=IST)
        current_level = price_to_level(close_price, base, step)
        if last_level is None:
            last_level = current_level
            if last_display_level is None:
                last_display_level = current_level
            continue
        if current_level != last_level:
            is_up = current_level > last_level
            display_level = current_level if is_up else current_level + step
            last_level = current_level
            if display_level == last_display_level:
                continue
            last_display_level = display_level
            direction = "up" if is_up else "down"
            alerts.append((dt_ist, display_level, direction))
    return alerts


def fill_gaps(coins) -> dict:
    """
    For each coin, fill the gap between last CSV entry (or CRYPTO_START_DATE) and now.
    Writes to sub_alerts/{ticker}.csv.
    Returns {ticker: [formatted alert lines]} for only the newly added alerts.
    """
    now_ms = int(datetime.now(IST).timestamp() * 1000)
    start_dt = datetime.strptime(CRYPTO_START_DATE, "%Y-%m-%d").replace(tzinfo=IST)
    start_ms_global = int(start_dt.timestamp() * 1000)

    new_alerts = {ticker: [] for ticker in coins}

    for ticker, cfg in coins.items():
        last = get_last_entry(ticker)
        if last:
            last_dt = datetime.strptime(f"{last[0]} {last[1]}", "%Y-%m-%d %H:%M:%S").replace(tzinfo=IST)
            start_ms = int(last_dt.timestamp() * 1000) + 60000
            initial_display_level = Decimal(last[2])
        else:
            start_ms = start_ms_global
            initial_display_level = None

        if start_ms >= now_ms:
            print(f"[{ticker}] Already up to date.")
            continue

        from_str = datetime.fromtimestamp(start_ms / 1000, tz=IST).strftime("%Y-%m-%d %H:%M IST")
        print(f"[{ticker}] Fetching klines from {from_str} ...")

        try:
            klines = fetch_klines(cfg["symbol"], start_ms, now_ms)
            alerts = reconstruct_alerts(klines, cfg["base"], cfg["step"], initial_display_level)
            print(f"[{ticker}] {len(alerts)} alerts reconstructed.")

            if alerts:
                path = alerts_file(ticker)
                file_exists = os.path.exists(path)
                with open(path, "a", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=["date", "time", "level", "direction"])
                    if not file_exists:
                        writer.writeheader()
                    for dt_ist, level, direction in alerts:
                        writer.writerow({
                            "date": dt_ist.strftime("%Y-%m-%d"),
                            "time": dt_ist.strftime("%H:%M:%S"),
                            "level": str(level),
                            "direction": direction,
                        })
                        emoji = "🟢" if direction == "up" else "🔴"
                        time_str = dt_ist.strftime("%H:%M IST %d %b")
                        new_alerts[ticker].append(f"{emoji}  {level}  {time_str}")

        except Exception as e:
            print(f"[{ticker}] Error: {e}")

        time.sleep(1)

    return new_alerts


if __name__ == "__main__":
    coins = load_coins()
    fill_gaps(coins)
