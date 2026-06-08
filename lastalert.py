import csv
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

from login import get_kite_instance

IST = timezone(timedelta(hours=5, minutes=30))
STOCKS_CSV = "stocks.csv"
LAST_BASE_CSV = "last_base.csv"


def load_stocks_config() -> dict:
    stocks = {}
    with open(STOCKS_CSV, newline="") as f:
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


def nearest_level(close: Decimal, base: Decimal, step: Decimal) -> Decimal:
    return ((close - base) / step).to_integral_value(rounding=ROUND_HALF_UP) * step + base


def generate_last_base():
    kite = get_kite_instance()
    stocks = load_stocks_config()

    instruments = [cfg["instrument"] for cfg in stocks.values()]
    ltp_data = kite.ltp(instruments)

    today = datetime.now(IST).date()
    from_date = today - timedelta(days=7)
    to_date = today - timedelta(days=1)

    results = []
    for symbol, cfg in stocks.items():
        instrument_key = cfg["instrument"]
        if instrument_key not in ltp_data:
            print(f"[SKIP] {symbol} — not found in ltp data")
            continue

        token = ltp_data[instrument_key]["instrument_token"]

        try:
            candles = kite.historical_data(token, from_date, to_date, "day")
            if not candles:
                print(f"[SKIP] {symbol} — no historical data returned")
                continue

            close = Decimal(str(candles[-1]["close"]))
            new_base = nearest_level(close, cfg["base"], cfg["step"])
            results.append((symbol, new_base, cfg["step"]))
            print(f"{symbol}: close={close}  →  new base={new_base}")

        except Exception as e:
            print(f"[ERROR] {symbol}: {e}")

    with open(LAST_BASE_CSV, "w", newline="") as f:
        writer = csv.writer(f)
        for symbol, base, step in results:
            writer.writerow([symbol, base, step])

    print(f"\nSaved {len(results)} stocks to {LAST_BASE_CSV}")


if __name__ == "__main__":
    generate_last_base()
