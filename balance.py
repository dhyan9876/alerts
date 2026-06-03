from login import init_kite


def print_balance():
    kite = init_kite()
    margins = kite.margins()
    equity = margins.get("equity", {})

    opening_bal = equity.get('opening_balance') or 0.0
    payin = equity.get('intraday_payin') or 0.0
    collateral = equity.get('collateral') or 0.0
    utilised = equity.get('utilised', {}).get('debits') or 0.0
    live_bal = equity.get('live_balance') or 0.0

    print("=" * 45)
    print("          ZERODHA EQUITY MARGINS            ")
    print("=" * 45)
    print(f" Opening Balance    : ₹{opening_bal:,.2f}")
    print(f" Intraday Pay-ins   : ₹{payin:,.2f}")
    print(f" Collateral/Leverage: ₹{collateral:,.2f}")
    print(f" Funds Blocked/Used : ₹{utilised:,.2f}")
    print("-" * 45)
    print(f" NET LIVE BALANCE   : ₹{live_bal:,.2f}")
    print("=" * 45)


if __name__ == "__main__":
    print_balance()
