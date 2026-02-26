# backend/src/broadcast.py
"""
Shared broadcast system for real-time updates.
The matcher and API can both use this to notify connected clients.
Uses a file-based notification system for inter-process communication.
"""
import asyncio
import threading
import time
from datetime import datetime
from pathlib import Path
from orders import get_open_orders, get_all_user_orders
from candles import get_historical_candles

_manager         = None   # orders
_trades_manager  = None   # trades  ← ADD
_candles_manager = None   # candles
_stats_manager   = None   # stats   ← ADD
_event_loop      = None
_last_candle_time = None

TRADE_SIGNAL_FILE = Path(__file__).parent / ".trade_signal"

# ─── Setters ─────────────────────────────────────────────────────────────────

def set_manager(manager):
    global _manager
    _manager = manager
    print(f"[Broadcast] Orders manager registered")

def set_trades_manager(manager):       # ← ADD
    global _trades_manager
    _trades_manager = manager
    print(f"[Broadcast] Trades manager registered")

def set_candles_manager(manager):
    global _candles_manager
    _candles_manager = manager
    print("[Broadcast] Candles manager registered")

def set_stats_manager(manager):        # ← ADD
    global _stats_manager
    _stats_manager = manager
    print("[Broadcast] Stats manager registered")

def set_event_loop(loop):
    global _event_loop
    _event_loop = loop
    print("[Broadcast] Event loop registered")

# ─── Broadcast: Orders ───────────────────────────────────────────────────────

async def broadcast_orders_update():
    if _manager is None or not _manager.active_connections:
        return
    try:
        from api import format_order
        orders = get_all_user_orders()
        formatted = [format_order(o).dict() for o in orders]
        await _manager.broadcast({
            "type": "update",
            "orders": formatted
        })
        print(f"[Broadcast] ✓ Orders → {len(formatted)} orders to {len(_manager.active_connections)} clients")
    except Exception as e:
        print(f"[Broadcast] ✗ Orders error: {e}")

# ─── Broadcast: Trades ───────────────────────────────────────────────────────

async def broadcast_trades_update():
    if _trades_manager is None or not _trades_manager.active_connections:
        return
    try:
        from trades import get_all_trades
        from api import format_trade
        trades = get_all_trades()
        formatted = [format_trade(t).dict() for t in trades]
        await _trades_manager.broadcast({
            "type": "update",
            "trades": formatted
        })
        print(f"[Broadcast] ✓ Trades → {len(formatted)} trades to {len(_trades_manager.active_connections)} clients")
    except Exception as e:
        print(f"[Broadcast] ✗ Trades error: {e}")

# ─── Broadcast: Candles ──────────────────────────────────────────────────────

async def broadcast_candle_update():
    global _last_candle_time
    if _candles_manager is None or not _candles_manager.active_connections:
        return
    try:
        candles = get_historical_candles(limit=2)
        if not candles:
            return

        current  = candles[-1]
        previous = candles[-2] if len(candles) > 1 else None

        if _last_candle_time is None:
            _last_candle_time = current["time"]
            await _candles_manager.broadcast({"type": "candle_update", "candle": current})
            return

        if current["time"] != _last_candle_time:
            if previous and previous["time"] == _last_candle_time:
                await _candles_manager.broadcast({"type": "candle_close", "candle": previous})
            _last_candle_time = current["time"]
            await _candles_manager.broadcast({"type": "candle_update", "candle": current})
        else:
            await _candles_manager.broadcast({"type": "candle_update", "candle": current})

        print(f"[Broadcast] ✓ Candle → window: {current['time']}")
    except Exception as e:
        print(f"[Broadcast] ✗ Candle error: {e}")

# ─── Broadcast: All (called on every trade signal) ───────────────────────────

async def broadcast_all():
    """Single entry point — fires all broadcasts when a trade executes"""
    await asyncio.gather(
        broadcast_orders_update(),
        broadcast_trades_update(),
        broadcast_candle_update(),
        return_exceptions=True   # one failure won't kill the others
    )

# ─── Trade signal file (matcher → API) ───────────────────────────────────────

def broadcast_trade(trade_data):
    """Called by matcher — writes signal file for the API monitor to pick up"""
    try:
        with open(TRADE_SIGNAL_FILE, 'w') as f:
            f.write(str(time.time()))
        print(f"[Broadcast] Trade signal written: {trade_data}")
    except Exception as e:
        print(f"[Broadcast] Error writing trade signal: {e}")

async def monitor_trade_signals():
    """Watches signal file; fires broadcast_all() whenever matcher writes a trade"""
    last_modified = 0
    while True:
        try:
            if TRADE_SIGNAL_FILE.exists():
                mtime = TRADE_SIGNAL_FILE.stat().st_mtime
                if mtime > last_modified:
                    last_modified = mtime
                    print("[Broadcast] Trade signal detected → broadcasting all")
                    await broadcast_all()
        except Exception as e:
            print(f"[Broadcast] Monitor error: {e}")
        await asyncio.sleep(0.1)

def start_trade_signal_monitor():
    if _event_loop is None:
        print("[Broadcast] Warning: event loop not set")
        return
    asyncio.ensure_future(monitor_trade_signals())
    print("[Broadcast] Trade signal monitor started")