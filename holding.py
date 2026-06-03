from login import init_kite


def print_holdings():
    kite = init_kite()
    holdings = kite.holdings()
    if not holdings:
        print("No portfolio holdings found.")
        return

    print("=" * 80)
    print("             ZERODHA PORTFOLIO HOLDINGS             ")
    print("=" * 80)
    print(f"{'Symbol':<20}{'Qty':>8}{'Avg Price':>15}{'LTP':>12}{'P&L':>15}")
    print("-" * 80)
    for item in holdings:
        print(f"{item.get('tradingsymbol', ''):<20}{item.get('quantity', 0):>8}{item.get('average_price', 0.0):>15.2f}{item.get('last_price', 0.0):>12.2f}{item.get('pnl', 0.0):>15.2f}")
    print("=" * 80)
    print()


if __name__ == "__main__":
    print_holdings()
