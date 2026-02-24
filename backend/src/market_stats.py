# backend/src/market_stats.py
from db import get_connection
from datetime import datetime, timedelta

def get_market_stats():
    """
    Compute market statistics from trades table:
    - last_price: price of most recent trade
    - change_24h: % change from 24h open to last price
    - volume_24h: sum of quantities in last 24h
    - high_24h: max price in last 24h
    - low_24h: min price in last 24h
    """
    conn = get_connection()
    cur = conn.cursor()
    
    now = datetime.now()
    twenty_four_h_ago = now - timedelta(hours=24)
    
    # Get all trades in last 24h
    cur.execute(
        """
        SELECT id, price, quantity, executed_at
        FROM trades
        WHERE executed_at >= ?
        ORDER BY executed_at ASC
        """,
        (twenty_four_h_ago.isoformat(),)
    )
    
    trades = [dict(row) for row in cur.fetchall()]
    conn.close()
    
    if not trades:
        return {
            "last_price": 0,
            "change_24h": 0,
            "volume_24h": 0,
            "high_24h": 0,
            "low_24h": 0
        }
    
    # Extract data
    prices = [float(t['price']) for t in trades]
    quantities = [float(t['quantity']) for t in trades]
    
    # Compute stats
    last_price = prices[-1]  # most recent trade price
    open_price = prices[0]   # first trade price in 24h window
    high_24h = max(prices)
    low_24h = min(prices)
    volume_24h = sum(quantities)
    
    # Change percentage
    change_24h = ((last_price - open_price) / open_price * 100) if open_price > 0 else 0
    
    return {
        "last_price": round(last_price, 2),
        "change_24h": round(change_24h, 2),
        "volume_24h": round(volume_24h, 8),
        "high_24h": round(high_24h, 2),
        "low_24h": round(low_24h, 2)
    }