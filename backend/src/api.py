from fastapi import FastAPI, HTTPException, Path, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
import asyncio
from orders import get_open_orders, get_best_bid, get_best_ask, place_order, get_all_user_orders, get_order_by_id
from trades import get_all_trades
from candles import get_historical_candles
from market_stats import get_market_stats
from pydantic import BaseModel
from dotenv import load_dotenv
from pathlib import Path
load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env")
from fastapi import Request
from auth import hash_password, verify_password, create_jwt, get_current_user, get_user_by_email, create_user
from wallets import get_wallet, create_wallet, check_balance

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Connection Managers ──────────────────────────────────────────────────────

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"[Orders WS] Client connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        print(f"[Orders WS] Client disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        dead = []
        for ws in self.active_connections:
            try:
                await ws.send_json(message)
            except Exception as e:
                print(f"[Orders WS] Send error: {e}")
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


class TradesConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"[Trades WS] Client connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        print(f"[Trades WS] Client disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        dead = []
        for ws in self.active_connections:
            try:
                await ws.send_json(message)
            except Exception as e:
                print(f"[Trades WS] Send error: {e}")
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


class CandlesConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"[Candles WS] Client connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        print(f"[Candles WS] Client disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        dead = []
        for ws in self.active_connections:
            try:
                await ws.send_json(message)
            except Exception as e:
                print(f"[Candles WS] Send error: {e}")
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


class StatsConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"[Stats WS] Client connected. Total: {len(self.active_connections)}")
    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        print(f"[Stats WS] Client disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        dead = []
        for ws in self.active_connections:
            try:
                await ws.send_json(message)
            except Exception as e:
                print(f"[Stats WS] Send error: {e}")
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


# Instantiate all managers BEFORE importing broadcast
manager         = ConnectionManager()
trades_manager  = TradesConnectionManager()
candles_manager = CandlesConnectionManager()
stats_manager   = StatsConnectionManager()

# NOW import broadcast and register managers
from broadcast import set_manager, set_event_loop, start_trade_signal_monitor, set_candles_manager, set_stats_manager, set_trades_manager
set_manager(manager)
set_trades_manager(trades_manager)   # ← ADD
set_candles_manager(candles_manager)
set_stats_manager(stats_manager)    

# ─── Startup ──────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup_event():
    loop = asyncio.get_event_loop()
    set_event_loop(loop)
    print("[API] Event loop registered, starting trade signal monitor...")
    start_trade_signal_monitor()

# ─── Pydantic Models ──────────────────────────────────────────────────────────

class PlaceOrderRequest(BaseModel):
    side: str
    type: str
    price: float | None = None
    quantity: float

class RegisterRequest(BaseModel):
    email: str
    name: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str

class OrderResponse(BaseModel):
    id: int
    time: str
    type: str
    side: str
    priceSats: str | None = None   # None is valid for market orders
    amount: str
    total: str
    status: str
    remaining_quantity: float
    quantity: float

class TradeResponse(BaseModel):
    id: int
    time: str
    buy_order_id: int
    sell_order_id: int
    price: str
    quantity: str
    side: str

# ─── Formatters ───────────────────────────────────────────────────────────────

def format_order(order_dict):
    status = order_dict['status'].lower()
    if status == 'open':
        if order_dict['quantity'] > order_dict['remaining_quantity']:
            status = 'partial'

    price_val  = order_dict.get('price')                                      # None for market orders
    price_sats = f"{price_val:,.0f}" if price_val is not None else None       # keep None, don't crash
    quantity   = order_dict['remaining_quantity']
    amount     = f"{quantity:.8f} AZC"
    total      = f"{(price_val * quantity):,.0f}" if price_val is not None else "—"

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
        remaining_quantity=order_dict['remaining_quantity'],
        quantity=order_dict['quantity']
    )

def format_trade(trade_dict):
    price_sats = f"{trade_dict['price']:,.0f}" if trade_dict['price'] else "0"
    quantity   = f"{trade_dict['quantity']:.8f} AZC"

    executed_at = trade_dict.get('executed_at')
    if isinstance(executed_at, str):
        dt = datetime.fromisoformat(executed_at)
    else:
        dt = executed_at
    time_str = dt.strftime('%m/%d/%y %H:%M:%S')

    side = 'buy'
    try:
        buy_order  = get_order_by_id(trade_dict.get('buy_order_id'))
        sell_order = get_order_by_id(trade_dict.get('sell_order_id'))
        if buy_order and sell_order:
            def parse_dt(val):
                if val is None: return None
                return datetime.fromisoformat(val) if isinstance(val, str) else val
            buy_created  = parse_dt(buy_order.get('created_at'))
            sell_created = parse_dt(sell_order.get('created_at'))
            if buy_created and sell_created:
                side = 'buy' if buy_created > sell_created else 'sell'
    except Exception:
        pass

    return TradeResponse(
        id=trade_dict['id'],
        time=time_str,
        buy_order_id=trade_dict['buy_order_id'],
        sell_order_id=trade_dict['sell_order_id'],
        price=price_sats,
        quantity=quantity,
        side=side
    )

# ─── WebSocket Endpoints ──────────────────────────────────────────────────────

@app.websocket("/ws/orders")
async def websocket_orders(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        orders = get_all_user_orders()
        await websocket.send_json({
            "type": "initial",
            "orders": [format_order(o).dict() for o in orders]
        })
        while True:
            data = await websocket.receive_text()
            if data == "refresh":
                orders = get_all_user_orders()
                await websocket.send_json({
                    "type": "update",
                    "orders": [format_order(o).dict() for o in orders]
                })
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        manager.disconnect(websocket)
        print(f"[Orders WS] Error: {e}")


@app.websocket("/ws/trades")
async def websocket_trades(websocket: WebSocket):
    await trades_manager.connect(websocket)
    try:
        trades = get_all_trades()
        await websocket.send_json({
            "type": "initial",
            "trades": [format_trade(t).dict() for t in trades]
        })
        while True:
            data = await websocket.receive_text()
            if data == "refresh":
                trades = get_all_trades()
                await websocket.send_json({
                    "type": "update",
                    "trades": [format_trade(t).dict() for t in trades]
                })
    except WebSocketDisconnect:
        trades_manager.disconnect(websocket)
    except Exception as e:
        trades_manager.disconnect(websocket)
        print(f"[Trades WS] Error: {e}")


@app.websocket("/ws/candles")
async def websocket_candles(websocket: WebSocket):
    await candles_manager.connect(websocket)
    try:
        candles = get_historical_candles(limit=25920)
        await websocket.send_json({
            "type": "initial",
            "candles": candles
        })
        print(f"[Candles WS] Sent {len(candles)} historical candles")
        while True:
            await websocket.receive_text()  # keepalive
    except WebSocketDisconnect:
        candles_manager.disconnect(websocket)
    except Exception as e:
        candles_manager.disconnect(websocket)
        print(f"[Candles WS] Error: {e}")


@app.websocket("/ws/market_stats")
async def websocket_market_stats(websocket: WebSocket):
    await stats_manager.connect(websocket)
    try:
        stats = get_market_stats()
        await websocket.send_json({"type": "market_stats", "stats": stats})
        while True:
            await asyncio.sleep(2)
            stats = get_market_stats()
            await websocket.send_json({"type": "market_stats", "stats": stats})
    except WebSocketDisconnect:
        stats_manager.disconnect(websocket)
    except Exception as e:
        stats_manager.disconnect(websocket)
        print(f"[Stats WS] Error: {e}")

# ─── Auth Endpoints ───────────────────────────────────────────────────────────

@app.post("/api/auth/register")
def register(body: RegisterRequest):
    if not body.email or not body.name or not body.password:
        raise HTTPException(status_code=400, detail="email, name, and password are required")
    existing = get_user_by_email(body.email)
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")
    pw_hash = hash_password(body.password)
    try:
        user_id = create_user(body.email, body.name, pw_hash)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    create_wallet(user_id)
    token = create_jwt(user_id, body.email.lower().strip(), body.name.strip())
    return {
        "token": token,
        "user": {"id": user_id, "email": body.email.lower().strip(), "name": body.name.strip()}
    }


@app.post("/api/auth/login")
def login(body: LoginRequest):
    user = get_user_by_email(body.email)
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_jwt(user["id"], user["email"], user["name"])
    return {
        "token": token,
        "user": {"id": user["id"], "email": user["email"], "name": user["name"]}
    }


@app.get("/api/auth/me")
def me(request: Request):
    user = get_current_user(request.headers.get("authorization"))
    return {"user": user}


# ─── Wallet Endpoint ──────────────────────────────────────────────────────────

@app.get("/api/wallet")
def wallet(request: Request):
    user = get_current_user(request.headers.get("authorization"))
    w = get_wallet(user["id"])
    if w is None:
        raise HTTPException(status_code=404, detail="Wallet not found")
    return {"azc": float(w["azc"]), "sats": float(w["sats"])}

# ─── REST Endpoints ───────────────────────────────────────────────────────────

@app.get("/api/health")
def health_check():
    return {"status": "ok"}

@app.get("/api/orders")
def get_orders():
    try:
        return {"orders": [format_order(o) for o in get_open_orders()]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/orders/poll")
def poll_orders():
    try:
        return {"orders": [format_order(o) for o in get_all_user_orders()]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/orders/bid")
def get_bid():
    try:
        bid = get_best_bid()
        if not bid:
            raise HTTPException(status_code=404, detail="No open buy orders")
        return format_order(bid)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/orders/ask")
def get_ask():
    try:
        ask = get_best_ask()
        if not ask:
            raise HTTPException(status_code=404, detail="No open sell orders")
        return format_order(ask)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/orders")
async def create_order(order: PlaceOrderRequest, request: Request):
    user = get_current_user(request.headers.get("authorization"))
    user_id = user["id"]

    side       = order.side.lower()
    order_type = order.type.lower()
    qty        = order.quantity
    price      = order.price

    # ── Balance check ─────────────────────────────────────────────────────────
    if order_type == "limit":
        if side == "buy":
            if not check_balance(user_id, "sats", qty * price):
                raise HTTPException(status_code=400, detail="Insufficient balance")
        else:  # sell
            if not check_balance(user_id, "azc", qty):
                raise HTTPException(status_code=400, detail="Insufficient balance")
    else:  # market
        if side == "buy":
            if not check_balance(user_id, "sats", 1):  # any SATS > 0
                raise HTTPException(status_code=400, detail="Insufficient balance")
        else:  # sell
            if not check_balance(user_id, "azc", qty):
                raise HTTPException(status_code=400, detail="Insufficient balance")

    try:
        order_id = place_order(
            side=side,
            order_type=order_type,
            price=price,
            quantity=qty,
            user_id=user_id,
        )
        from broadcast import broadcast_orders_update
        await broadcast_orders_update()
        return {"order_id": order_id, "message": "Order placed successfully"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/trades")
def get_trades():
    try:
        return {"trades": [format_trade(t) for t in get_all_trades()]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/trades/poll")
def poll_trades():
    try:
        return {"trades": [format_trade(t) for t in get_all_trades()]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/candles")
def get_candles(limit: int = 120):
    try:
        return {"candles": get_historical_candles(limit=limit)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))