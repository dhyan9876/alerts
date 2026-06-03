# placeorder.py
# Usage: python placeorder.py nhpc q1 p75

import sys
from datetime import datetime, time
import pytz
from login import get_kite_instance
from price import get_quote

def is_market_open():
    ist = pytz.timezone("Asia/Kolkata")
    now = datetime.now(ist)

    # Market closed on weekends
    if now.weekday() >= 5:  # 5 = Saturday, 6 = Sunday
        return False

    market_open = time(9, 15)
    market_close = time(15, 30)

    return market_open <= now.time() <= market_close

def parse_args():
    if len(sys.argv) != 4:
        print("❌ Usage: python placeorder.py <symbol> q<quantity> p<price>")
        print("   Example: python placeorder.py nhpc q1 p75")
        sys.exit(1)

    symbol = sys.argv[1].upper()
    quantity_arg = sys.argv[2]
    price_arg = sys.argv[3]

    # Parse quantity
    if not quantity_arg.lower().startswith("q"):
        print("❌ Quantity must start with 'q', e.g. q1 or q10")
        sys.exit(1)
    try:
        quantity = int(quantity_arg[1:])
        if quantity <= 0:
            raise ValueError
    except ValueError:
        print(f"❌ Invalid quantity: '{quantity_arg}'. Example: q1, q10")
        sys.exit(1)

    # Parse price
    if not price_arg.lower().startswith("p"):
        print("❌ Price must start with 'p', e.g. p75 or p85.50")
        sys.exit(1)
    try:
        price = float(price_arg[1:])
        if price <= 0:
            raise ValueError
    except ValueError:
        print(f"❌ Invalid price: '{price_arg}'. Example: p75, p85.50")
        sys.exit(1)

    return symbol, quantity, price

def place_limit_order(symbol, quantity, limit_price):
    kite = get_kite_instance()

    symbol_code, data = get_quote(symbol)
    trading_symbol = symbol_code.split(":")[1]  # strip "NSE:" prefix

    if not data:
        print(f"❌ Could not fetch price for {symbol_code}. Aborting.")
        sys.exit(1)

    market_open = is_market_open()
    variety = kite.VARIETY_REGULAR if market_open else kite.VARIETY_AMO
    order_label = "REGULAR (CNC)" if market_open else "AMO - After Market Order (CNC)"

    ist = pytz.timezone("Asia/Kolkata")
    now = datetime.now(ist).strftime("%I:%M %p")

    print("=" * 60)
    print(f"  ORDER PREVIEW")
    print("=" * 60)
    print(f"  Stock    : {symbol_code}")
    print(f"  Action   : BUY")
    print(f"  Quantity : {quantity}")
    print(f"  Type     : LIMIT")
    print(f"  Price    : ₹{limit_price:,.2f}")
    print(f"  Exchange : NSE")
    print(f"  Product  : CNC (Delivery)")
    print(f"  Variety  : {order_label}")
    print(f"  Time     : {now} IST")
    print("=" * 60)

    if not market_open:
        print("⚠️  Market is currently CLOSED. This will be placed as an AMO.")
        print("   AMO orders execute when market opens next trading day at 9:15 AM.")

    confirm = input("\nConfirm order? (yes/no): ").strip().lower()
    if confirm != "yes":
        print("❌ Order cancelled.")
        sys.exit(0)

    try:
        order_id = kite.place_order(
            tradingsymbol=trading_symbol,
            exchange=kite.EXCHANGE_NSE,
            transaction_type=kite.TRANSACTION_TYPE_BUY,
            quantity=quantity,
            order_type=kite.ORDER_TYPE_LIMIT,
            price=limit_price,
            product=kite.PRODUCT_CNC,
            variety=variety,
        )
        if market_open:
            print(f"\n✅ Regular order placed successfully!")
        else:
            print(f"\n✅ AMO placed successfully! Will execute at market open (9:15 AM).")
        print(f"   Order ID  : {order_id}")
        print(f"   Symbol    : {symbol_code}")
        print(f"   Quantity  : {quantity}")
        print(f"   Price     : ₹{limit_price:,.2f}")
        print(f"   Variety   : {order_label}")
    except Exception as e:
        print(f"\n❌ Order failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    symbol, quantity, limit_price = parse_args()
    place_limit_order(symbol, quantity, limit_price)