# backend/src/api.py
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
import asyncio
import json
from orders import get_open_orders, get_best_bid, get_best_ask, place_order, get_all_user_orders, get_order_by_id
from pydantic import BaseModel
from market_stats import get_market_stats  # This should return a dict of stats

app = FastAPI()

# Enable CORS for frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Store active WebSocket connections
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"Client connected. Total clients: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        print(f"Client disconnected. Total clients: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        """Send message to all connected clients"""
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                print(f"Error sending message to client: {e}")
                disconnected.append(connection)
        
        # Remove disconnected clients
        for connection in disconnected:
            self.disconnect(connection)

manager = ConnectionManager()

# Register the manager and event loop with broadcast system
from broadcast import set_manager, set_event_loop, start_trade_signal_monitor
set_manager(manager)

@app.on_event("startup")
async def startup_event():
    """Set the event loop and start monitoring for trades"""
    loop = asyncio.get_event_loop()
    set_event_loop(loop)
    print("[API] Event loop registered, starting trade signal monitor...")
    start_trade_signal_monitor()

# Pydantic models for request/response

from orders import get_open_orders, get_all_user_orders, get_best_bid, get_best_ask, place_order

# Add this new function (create it in orders.py first, see step 2)
from trades import get_all_trades

# Add this Pydantic model
class TradeResponse(BaseModel):
    id: int
    time: str
    buy_order_id: int
    sell_order_id: int
    price: str
    quantity: str
    side: str

class OrderResponse(BaseModel):
    id: int
    time: str
    type: str
    side: str
    priceSats: str
    amount: str
    total: str
    status: str
    remaining_quantity: float
    quantity: float

class PlaceOrderRequest(BaseModel):
    side: str
    type: str
    price: float
    quantity: float

def format_order(order_dict):
    """Convert database order to frontend format"""
    status = order_dict['status'].lower()
    if status == 'open':
        if order_dict['quantity'] > order_dict['remaining_quantity']:
            status = 'partial'
    
    price_sats = f"{order_dict['price']:,.0f}" if order_dict['price'] else "0"
    quantity = order_dict['remaining_quantity']
    amount = f"{quantity:.8f} AZC"
    total = f"{(order_dict['price'] * quantity):,.0f}" if order_dict['price'] else "0"
    
    created_at = order_dict['created_at']
    if isinstance(created_at, str):
        dt = datetime.fromisoformat(created_at)
    else:
        dt = created_at
    time_str = dt.strftime('%m/%d/%y %H:%M:%S')
    
    return OrderResponse(
        id=order_dict['id'],
        time=time_str,
        type=order_dict['type'].capitalize(),
        side=order_dict['side'].capitalize(),
        priceSats=price_sats,
        amount=amount,
        total=total,
        status=status.capitalize(),
        remaining_quantity=order_dict['remaining_quantity'],  # Add this
        quantity=order_dict['quantity'] 
    )

def format_trade(trade_dict):
    """Convert database trade to frontend format"""
    price_sats = f"{trade_dict['price']:,.0f}" if trade_dict['price'] else "0"
    quantity = f"{trade_dict['quantity']:.8f} AZC"
    
    # Use executed_at instead of created_at
    executed_at = trade_dict.get('executed_at')
    if isinstance(executed_at, str):
        dt = datetime.fromisoformat(executed_at)
    else:
        dt = executed_at
    time_str = dt.strftime('%m/%d/%y %H:%M:%S')
    
    # Determine side (taker) by comparing order creation times
    # The order created later (closer to trade execution) is the taker
    side = 'buy'  # default
    try:
        buy_order = get_order_by_id(trade_dict.get('buy_order_id'))
        sell_order = get_order_by_id(trade_dict.get('sell_order_id'))
        
        if buy_order and sell_order:
            # Parse created_at timestamps
            def parse_datetime(val):
                if val is None:
                    return None
                if isinstance(val, str):
                    try:
                        return datetime.fromisoformat(val)
                    except Exception:
                        return None
                return val
            
            buy_created = parse_datetime(buy_order.get('created_at'))
            sell_created = parse_datetime(sell_order.get('created_at'))
            
            if buy_created and sell_created:
                # The order created later is the taker
                side = 'buy' if buy_created > sell_created else 'sell'
            else:
                side = 'buy'
        elif buy_order:
            side = 'buy'
        elif sell_order:
            side = 'sell'
    except Exception:
        side = 'buy'
    
    return TradeResponse(
        id=trade_dict['id'],
        time=time_str,
        buy_order_id=trade_dict['buy_order_id'],
        sell_order_id=trade_dict['sell_order_id'],
        price=price_sats,
        quantity=quantity,
        side=side
    )


# Add this WebSocket endpoint
@app.websocket("/ws/trades")
async def websocket_trades(websocket: WebSocket):
    """WebSocket connection for real-time trade updates"""
    await manager.connect(websocket)
    try:
        # Send initial trades to the client
        trades = get_all_trades()
        formatted_trades = [format_trade(t).dict() for t in trades]
        await websocket.send_json({
            "type": "initial",
            "trades": formatted_trades
        })
        print(f"Sent {len(formatted_trades)} initial trades")
        
        # Keep connection alive
        while True:
            data = await websocket.receive_text()
            if data == "refresh":
                trades = get_all_trades()
                formatted_trades = [format_trade(t).dict() for t in trades]
                await websocket.send_json({
                    "type": "update",
                    "trades": formatted_trades
                })
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        manager.disconnect(websocket)
        print(f"WebSocket error: {e}")

# Add this REST endpoint
@app.get("/api/trades")
def get_trades():
    """Get all trades"""
    try:
        trades = get_all_trades()
        formatted_trades = [format_trade(t) for t in trades]
        return {"trades": formatted_trades}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Add this polling endpoint
@app.get("/api/trades/poll")
def poll_trades():
    """Poll endpoint for trades (alternative to WebSocket)"""
    try:
        trades = get_all_trades()
        formatted_trades = [format_trade(t) for t in trades]
        return {"trades": formatted_trades}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# WebSocket endpoint for real-time updates
@app.websocket("/ws/orders")
async def websocket_orders(websocket: WebSocket):
    """WebSocket connection for real-time order updates"""
    await manager.connect(websocket)
    try:
        # Send initial orders to the client (all orders, not just open)
        orders = get_all_user_orders()
        formatted_orders = [format_order(o).dict() for o in orders]
        await websocket.send_json({
            "type": "initial",
            "orders": formatted_orders
        })
        print(f"Sent {len(formatted_orders)} initial orders")
        
        # Keep connection alive and listen for client messages
        while True:
            data = await websocket.receive_text()
            if data == "refresh":
                orders = get_all_user_orders()
                formatted_orders = [format_order(o).dict() for o in orders]
                await websocket.send_json({
                    "type": "update",
                    "orders": formatted_orders
                })
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        manager.disconnect(websocket)
        print(f"WebSocket error: {e}")

# Polling alternative endpoint (fallback)
# In backend/src/api.py
@app.get("/api/orders/poll")
def poll_orders():
    """Poll endpoint for orders (alternative to WebSocket)"""
    try:
        orders = get_all_user_orders()
        formatted_orders = [format_order(o) for o in orders]
        return {"orders": formatted_orders}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# REST API Endpoints
@app.get("/api/orders")
def get_orders():
    """Get all open and partial orders"""
    try:
        orders = get_open_orders()
        formatted_orders = [format_order(o) for o in orders]
        return {"orders": formatted_orders}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/orders/bid")
def get_bid():
    """Get best bid (highest buy order)"""
    try:
        bid = get_best_bid()
        if not bid:
            raise HTTPException(status_code=404, detail="No open buy orders found")
        return format_order(bid)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/orders/ask")
def get_ask():
    """Get best ask (lowest sell order)"""
    try:
        ask = get_best_ask()
        if not ask:
            raise HTTPException(status_code=404, detail="No open sell orders found")
        return format_order(ask)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/orders")
async def create_order(order: PlaceOrderRequest):
    """Place a new order"""
    try:
        order_id = place_order(
            side=order.side.lower(),
            order_type=order.type.lower(),
            price=order.price,
            quantity=order.quantity
        )
        
        # Broadcast updated orders to all clients
        from broadcast import broadcast_orders_update
        await broadcast_orders_update()
        
        return {"order_id": order_id, "message": "Order placed successfully"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/health")
def health_check():
    """Health check endpoint"""
    return {"status": "ok"}

# Add a connection manager for stats
class StatsConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, stats):
        for ws in self.active_connections:
            try:
                await ws.send_json({"type": "market_stats", "stats": stats})
            except Exception:
                self.disconnect(ws)

stats_manager = StatsConnectionManager()

@app.websocket("/ws/market_stats")
async def websocket_market_stats(websocket: WebSocket):
    await stats_manager.connect(websocket)
    try:
        # Send initial stats
        stats = get_market_stats()
        await websocket.send_json({"type": "market_stats", "stats": stats})
        # Keep connection alive and send updates every 2 seconds
        while True:
            await asyncio.sleep(2)
            stats = get_market_stats()
            await websocket.send_json({"type": "market_stats", "stats": stats})
    except WebSocketDisconnect:
        stats_manager.disconnect(websocket)