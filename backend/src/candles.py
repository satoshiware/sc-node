import math
from datetime import datetime, timedelta
from db import get_connection

CANDLE_INTERVAL = 10  # seconds (10-second candles)

def get_candle_timestamp(dt):
    """Round datetime down to nearest 10-second bucket"""
    ts = dt.timestamp()
    bucket = math.floor(ts / CANDLE_INTERVAL) * CANDLE_INTERVAL
    return datetime.fromtimestamp(bucket)

def aggregate_trades_to_candles(trades):
    """
    Convert a list of trade dicts to OHLCV candles (10-second windows).
    Open  = first trade price in window
    High  = max trade price
    Low   = min trade price
    Close = last trade price
    Volume= sum of quantities
    Returns list sorted ascending by time.
    """
    if not trades:
        return []

    candles_map = {}

    for trade in trades:
        executed_at = trade.get("executed_at")
        if not executed_at:
            continue
        if isinstance(executed_at, str):
            dt = datetime.fromisoformat(executed_at)
        else:
            dt = executed_at

        bucket_time = get_candle_timestamp(dt)
        bucket_key  = bucket_time.isoformat()

        price    = float(trade["price"])
        quantity = float(trade["quantity"])

        if bucket_key not in candles_map:
            candles_map[bucket_key] = {
                "time":   bucket_time,
                "open":   price,
                "high":   price,
                "low":    price,
                "close":  price,
                "volume": quantity,
            }
        else:
            c = candles_map[bucket_key]
            c["high"]   = max(c["high"],  price)
            c["low"]    = min(c["low"],   price)
            c["close"]  = price           # last price in window
            c["volume"] += quantity

    candles = sorted(candles_map.values(), key=lambda c: c["time"])

    return [
        {
            "time":   c["time"].isoformat(),
            "open":   round(c["open"],   2),
            "high":   round(c["high"],   2),
            "low":    round(c["low"],    2),
            "close":  round(c["close"],  2),
            "volume": round(c["volume"], 8),
        }
        for c in candles
    ]

def get_historical_candles(limit=25920):
    """Fetch all trades and return last `limit` OHLCV candles (ascending)."""
    conn = get_connection()
    cur  = conn.cursor()
    cur.execute(
        """
        SELECT price, quantity, executed_at
        FROM trades
        ORDER BY executed_at ASC
        """
    )
    trades = [dict(row) for row in cur.fetchall()]
    conn.close()

    candles = aggregate_trades_to_candles(trades)
    # return last N candles
    return candles[-limit:] if len(candles) > limit else candles

def get_current_candle():
    """Return the candle for the current 10-second window (may be incomplete)."""
    conn = get_connection()
    cur  = conn.cursor()
    now  = datetime.now()
    since = (now - timedelta(seconds=CANDLE_INTERVAL + 1)).isoformat()
    cur.execute(
        """
        SELECT price, quantity, executed_at
        FROM trades
        WHERE executed_at >= ?
        ORDER BY executed_at ASC
        """,
        (since,)
    )
    trades = [dict(row) for row in cur.fetchall()]
    conn.close()

    candles = aggregate_trades_to_candles(trades)
    return candles[-1] if candles else None