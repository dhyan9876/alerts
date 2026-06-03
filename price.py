import argparse
from login import get_kite_instance


def format_quote_symbol(symbol):
    symbol = symbol.strip().upper()
    if ":" in symbol:
        return symbol
    return f"NSE:{symbol}"


def get_quote(symbol):
    kite = get_kite_instance()
    symbol_code = format_quote_symbol(symbol)
    quote = kite.quote(symbol_code)
    data = quote.get(symbol_code, {})
    return symbol_code, data


def print_quote(symbol):
    symbol_code, data = get_quote(symbol)
    if not data:
        print(f"No quote data returned for {symbol_code}\n")
        return

    close_price = data.get("ohlc", {}).get("close")
    last_price = data.get("last_price")

    print("=" * 80)
    print(f"               {symbol_code} PRICE                  ")
    print("=" * 80)
    if close_price is not None:
        print(f" Previous Close : ₹{close_price:,.2f}")
    else:
        print(" Previous Close : N/A")
    if last_price is not None:
        print(f" Last Price     : ₹{last_price:,.2f}")
    else:
        print(" Last Price     : N/A")
    print("=" * 80)
    print()


def parse_args():
    parser = argparse.ArgumentParser(description="Fetch a Zerodha quote for a given symbol")
    parser.add_argument("symbol", nargs="?", default="NIFTY 50",
                        help="Symbol to fetch quote for, e.g. HDFCBANK or 'NIFTY 50'")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    print_quote(args.symbol)
