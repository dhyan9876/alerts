import csv
import os
import time
from decimal import Decimal, ROUND_FLOOR
from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv

load_dotenv()

IST = timezone(timedelta(hours=5, minutes=30))
ALERTS_DIR = "stockalerts"
STOCKS_START_DATE = os.getenv("STOCKS_START_DATE", "2026-06-01")


def alerts_file(symbol: str) -> str:
    os.makedirs(ALERTS_DIR, exist_ok=True)
    return os.path.join(ALERTS_DIR, f"{symbol}.csv")


def load_stocks_config(csv_path="stocks.csv") -> dict:
    stocks = {}
    with open(csv_path, newline="") as f:
        for row in csv.reader(f):
            if not row or len(row) < 3:
                continue
            symbol, base, step = row[0].strip(), row[1].strip(), row[2].strip()
            stocks[symbol] = {"base": Decimal(base), "step": Decimal(step)}
    return stocks


def price_to_level(price, base, step):
    return ((price - base) / step).to_integral_value(rounding=ROUND_FLOOR) * step + base


def _to_ist(dt):
    """Ensure datetime is IST-aware (Kite returns naive datetimes in IST)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=IST)
    return dt.astimezone(IST)


def get_last_entry(symbol):
    """Return (date, time, level, direction) of last entry in stockalerts/{symbol}.csv, or None."""
    path = alerts_file(symbol)
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


def reconstruct_alerts(candles, base, step, initial_display_level=None):
    """Walk 1-min candles using close price. Returns list of (datetime_ist, display_level, direction)."""
    alerts = []
    last_level = None
    last_display_level = initial_display_level
    for candle in candles:
        close_price = Decimal(str(candle["close"]))
        dt_ist = _to_ist(candle["date"])
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


def fill_gaps(kite, stocks) -> dict:
    """
    For each stock, fill gap between last stockalerts CSV entry (or STOCKS_START_DATE) and now.
    Writes to stockalerts/{SYMBOL}.csv.
    Returns {symbol: [formatted alert lines]} for only newly added alerts.
    """
    now_ist = datetime.now(IST)
    start_date_global = datetime.strptime(STOCKS_START_DATE, "%Y-%m-%d").date()

    instruments = [f"NSE:{symbol}" for symbol in stocks]
    try:
        ltp_data = kite.ltp(*instruments)
    except Exception as e:
        print(f"[fill_gaps] Failed to fetch LTP: {e}")
        return {symbol: [] for symbol in stocks}

    instrument_tokens = {
        symbol: ltp_data[f"NSE:{symbol}"]["instrument_token"]
        for symbol in stocks
        if f"NSE:{symbol}" in ltp_data
    }

    new_alerts = {symbol: [] for symbol in stocks}

    for symbol, cfg in stocks.items():
        token = instrument_tokens.get(symbol)
        if not token:
            print(f"[{symbol}] No instrument token, skipping.")
            continue

        last = get_last_entry(symbol)
        if last:
            last_dt = datetime.strptime(f"{last[0]} {last[1]}", "%Y-%m-%d %H:%M:%S").replace(tzinfo=IST)
            from_date = last_dt.date()
            initial_display_level = Decimal(last[2])
        else:
            from_date = start_date_global
            initial_display_level = None

        to_date = now_ist.date()

        if from_date > to_date:
            print(f"[{symbol}] Already up to date.")
            continue

        print(f"[{symbol}] Fetching 1-min candles from {from_date} ...")

        try:
            candles = kite.historical_data(token, from_date, to_date, "minute")

            if last and candles:
                candles = [c for c in candles if _to_ist(c["date"]) > last_dt]

            alerts = reconstruct_alerts(candles, cfg["base"], cfg["step"], initial_display_level)
            print(f"[{symbol}] {len(alerts)} alerts reconstructed.")

            if alerts:
                path = alerts_file(symbol)
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
                        new_alerts[symbol].append(f"{emoji}  {level}  {time_str}")

        except Exception as e:
            print(f"[{symbol}] Error: {e}")

        time.sleep(0.5)

    return new_alerts


if __name__ == "__main__":
    from login import get_kite_instance
    kite = get_kite_instance()
    stocks = load_stocks_config()
    fill_gaps(kite, stocks)
