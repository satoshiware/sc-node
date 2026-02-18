# backend/src/api.py
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
import asyncio
import json
from orders import get_open_orders, get_best_bid, get_best_ask, place_order,get_all_user_orders
from pydantic import BaseModel

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