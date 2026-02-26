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
from candles import get_historical_candles  # ADD THIS

# Global reference to the API manager (set by api.py)
_manager = None
_event_loop = None
_candles_manager = None          # ADD THIS
_last_candle_time = None         # ADD THIS

# Path for trade notification file (matcher writes, API reads)
TRADE_SIGNAL_FILE = Path(__file__).parent / ".trade_signal"

def set_manager(manager):
    """Called by api.py to set the connection manager"""
    global _manager
    _manager = manager
    print(f"Broadcast manager set with {len(manager.active_connections)} connections")

def set_event_loop(loop):
    """Called by api.py to set the event loop"""
    global _event_loop
    _event_loop = loop
    print("Event loop registered for broadcast")

def set_candles_manager(manager):   # ADD THIS WHOLE FUNCTION
    """Called by api.py to register the candles connection manager"""
    global _candles_manager
    _candles_manager = manager
    print("[Broadcast] Candles manager registered")

async def broadcast_orders_and_trades():
    """Broadcast both orders and trades to all connected clients"""
    if _manager is None:
        return
    
    try:
        orders = get_all_user_orders()
        from api import format_order
        formatted_orders = [format_order(o).dict() for o in orders]
        
        from trades import get_recent_trades
        from api import format_trade
        trades = get_recent_trades(limit=100)
        formatted_trades = [format_trade(t).dict() for t in trades]
        
        if _manager.active_connections:
            await _manager.broadcast({
                "type": "update",
                "orders": formatted_orders,
                "trades": formatted_trades
            })
            print(f"[Broadcast] ✓ Sent {len(formatted_orders)} orders and {len(formatted_trades)} trades")

        # ADD THIS — broadcast candles on every trade signal too
        await broadcast_candle_update()

    except Exception as e:
        print(f"[Broadcast] ✗ Error broadcasting: {e}")

async def broadcast_orders_update():
    """Broadcast current orders to all connected clients"""
    await broadcast_orders_and_trades()

def broadcast_trade(trade_data):
    """
    Called by matcher to notify about a trade execution.
    Works across processes by writing a signal file.
    """
    try:
        # Write signal file to notify API of trade
        with open(TRADE_SIGNAL_FILE, 'w') as f:
            f.write(str(time.time()))
        print(f"Trade signal written: {trade_data}")
    except Exception as e:
        print(f"Error writing trade signal: {e}")

async def monitor_trade_signals():
    """
    Runs in the API process and watches for trade signals from matcher.
    Broadcasts updates when trades occur.
    """
    last_modified = 0
    while True:
        try:
            if TRADE_SIGNAL_FILE.exists():
                current_modified = TRADE_SIGNAL_FILE.stat().st_mtime
                if current_modified > last_modified:
                    print("Trade signal detected, broadcasting update...")
                    last_modified = current_modified
                    await broadcast_orders_update()
        except Exception as e:
            print(f"Error monitoring trade signals: {e}")
        
        # Check every 100ms for new trade signals
        await asyncio.sleep(0.1)

async def broadcast_candle_update():
    """
    Derives latest 2 candles from trades and pushes:
      candle_update  → mutate current open candle
      candle_close   → previous candle closed, new window started
    """
    global _last_candle_time
    if _candles_manager is None:
        return
    if not _candles_manager.active_connections:
        return

    try:
        candles = get_historical_candles(limit=2)   # ascending order
        if not candles:
            return

        current  = candles[-1]
        previous = candles[-2] if len(candles) > 1 else None

        if _last_candle_time is None:
            # first tick ever
            _last_candle_time = current["time"]
            await _candles_manager.broadcast({"type": "candle_update", "candle": current})
            return

        if current["time"] != _last_candle_time:
            # window rolled: close the previous candle first
            if previous and previous["time"] == _last_candle_time:
                await _candles_manager.broadcast({"type": "candle_close", "candle": previous})
            _last_candle_time = current["time"]
            await _candles_manager.broadcast({"type": "candle_update", "candle": current})
        else:
            # same window: mutate last candle in place
            await _candles_manager.broadcast({"type": "candle_update", "candle": current})

        print(f"[Broadcast] ✓ Candle broadcast — window: {current['time']}")
    except Exception as e:
        print(f"[Broadcast] ✗ Candle broadcast error: {e}")

def start_trade_signal_monitor():
    """Start the trade signal monitor in the background"""
    if _event_loop is None:
        print("Warning: Event loop not set, cannot start trade signal monitor")
        return
    
    try:
        asyncio.ensure_future(monitor_trade_signals())
        print("Trade signal monitor started")
    except Exception as e:
        print(f"Error starting trade signal monitor: {e}")