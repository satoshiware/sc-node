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
from orders import get_open_orders,get_all_user_orders

# Global reference to the API manager (set by api.py)
_manager = None
_event_loop = None

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

async def broadcast_orders_update():
    """Broadcast current orders to all connected clients"""
    if _manager is None:
        print("Warning: Manager not set, cannot broadcast")
        return
    
    try:
        # Fetch all orders (including filled/partial ones)
        orders = get_all_user_orders()
        # Import here to avoid circular imports
        from api import format_order
        formatted_orders = [format_order(o).dict() for o in orders]
        
        if _manager.active_connections:
            await _manager.broadcast({
                "type": "update",
                "orders": formatted_orders
            })
            print(f"✓ Broadcast: {len(formatted_orders)} orders to {len(_manager.active_connections)} clients")
        else:
            print(f"No active connections to broadcast to")
    except Exception as e:
        print(f"✗ Error broadcasting orders: {e}")

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