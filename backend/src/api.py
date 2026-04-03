from fastapi import FastAPI, HTTPException, Path, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
import asyncio
import json
import os
import ssl
from urllib import parse, request as urlrequest
from urllib.error import HTTPError, URLError
try:
    import certifi
except ImportError:
    certifi = None
from orders import get_open_orders, get_best_bid, get_best_ask, place_order, get_all_user_orders, get_order_by_id,get_orders_by_user
from trades import get_all_trades, get_trades_by_user
from candles import get_historical_candles
from market_stats import get_market_stats
from pydantic import BaseModel
from dotenv import load_dotenv
from pathlib import Path
load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env")
from fastapi import Request
from auth import hash_password, verify_password, create_jwt, get_current_user, get_user_by_email, create_user
from wallets import get_wallet, create_wallet, check_balance

BRAIINS_BASE_URL = "https://pool.braiins.com"
MINER_PROVIDER = os.getenv("MINER_PROVIDER", "local").strip().lower()
LOCAL_POOL_BASE_URL = os.getenv("LOCAL_POOL_BASE_URL", "http://10.10.80.10:8000").rstrip("/")


def build_ssl_context() -> ssl.SSLContext:
    skip_verify = os.getenv("BRAIINS_SKIP_SSL_VERIFY", "false").lower() in {"1", "true", "yes"}
    if skip_verify:
        # Dev-only fallback when local machine trust store is broken.
        return ssl._create_unverified_context()

    if certifi is not None:
        return ssl.create_default_context(cafile=certifi.where())

    return ssl.create_default_context()


BRAIINS_SSL_CONTEXT = build_ssl_context()


def get_braiins_api_key() -> str:
    # Support both names while keeping BRAIINS_API_KEY as preferred convention.
    token = os.getenv("BRAIINS_API_KEY") or os.getenv("braiins_api_key")
    if not token:
        raise HTTPException(
            status_code=500,
            detail="Braiins API key is missing. Set BRAIINS_API_KEY in backend/.env",
        )
    return token


def braiins_get(path: str, query: dict | None = None) -> dict:
    token = get_braiins_api_key()
    url = f"{BRAIINS_BASE_URL}{path}"
    if query:
        url = f"{url}?{parse.urlencode(query)}"

    req = urlrequest.Request(
        url,
        headers={
            "Pool-Auth-Token": token,
            "Accept": "application/json",
            "User-Agent": "coinbot-backend/1.0",
        },
        method="GET",
    )

    try:
        with urlrequest.urlopen(req, timeout=10, context=BRAIINS_SSL_CONTEXT) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body)
    except HTTPError as e:
        msg = e.read().decode("utf-8", errors="ignore")
        raise HTTPException(status_code=502, detail=f"Braiins API HTTP {e.code}: {msg[:200]}")
    except ssl.SSLError as e:
        raise HTTPException(status_code=502, detail=f"Braiins API SSL error: {str(e)}")
    except URLError as e:
        raise HTTPException(status_code=502, detail=f"Braiins API network error: {e.reason}")
    except json.JSONDecodeError:
        raise HTTPException(status_code=502, detail="Braiins API returned invalid JSON")


def get_local_pool_token() -> str:
    token = os.getenv("LOCAL_POOL_BEARER_TOKEN") or os.getenv("local_pool_bearer_token")
    if not token:
        raise HTTPException(
            status_code=500,
            detail="Local pool bearer token is missing. Set LOCAL_POOL_BEARER_TOKEN in backend/.env",
        )
    return token


def local_pool_get(path: str, query: dict | None = None) -> dict | list:
    token = get_local_pool_token()
    url = f"{LOCAL_POOL_BASE_URL}{path}"
    if query:
        url = f"{url}?{parse.urlencode(query)}"

    req = urlrequest.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": "coinbot-backend/1.0",
        },
        method="GET",
    )

    try:
        with urlrequest.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body)
    except HTTPError as e:
        msg = e.read().decode("utf-8", errors="ignore")
        raise HTTPException(status_code=502, detail=f"Local pool API HTTP {e.code}: {msg[:200]}")
    except URLError as e:
        raise HTTPException(status_code=502, detail=f"Local pool API network error: {e.reason}")
    except json.JSONDecodeError:
        raise HTTPException(status_code=502, detail="Local pool API returned invalid JSON")


def resolve_pool_username(user: dict | None, requested_username: str | None = None) -> str | None:
    if requested_username:
        value = requested_username.strip()
        return value or None
    if isinstance(user, dict):
        # Login identity is the primary source for pool username.
        candidate = user.get("name") or user.get("username") or user.get("email")
        if candidate:
            candidate = str(candidate)
            if "@" in candidate:
                return candidate.split("@", 1)[0]
            return candidate
    return None


def map_worker_state(seconds_since_last_share: float | int | None) -> str:
    s = to_number(seconds_since_last_share)
    if s is None:
        return "off"
    if s <= 90:
        return "ok"
    if s <= 300:
        return "low"
    if s <= 1800:
        return "off"
    return "dis"


def to_number(value):
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    if n != n:
        return None
    return n


def local_profile_payload(coin: str, detail: dict) -> dict:
    hashrate = to_number(detail.get("hashrate_user")) or 0.0
    all_time_reward = to_number(detail.get("rewards_total")) or 0.0
    return {
        coin: {
            "hash_rate_5m": hashrate,
            "hash_rate_60m": hashrate,
            "hash_rate_24h": hashrate,
            "hash_rate_unit": "h/s",
            "today_reward": 0.0,
            "all_time_reward": all_time_reward,
            "current_balance": 0.0,
        }
    }


def local_workers_payload(coin: str, detail: dict) -> dict:
    miners = detail.get("miners") or []
    workers = {}
    for miner in miners:
        name = str(miner.get("name") or miner.get("raw_worker") or "")
        if not name:
            continue

        worker_detail = {}
        try:
            worker_detail = local_pool_get(f"/v1/mining/workers/{parse.quote(name, safe='')}")
            if not isinstance(worker_detail, dict):
                worker_detail = {}
        except HTTPException:
            # Keep endpoint resilient: one worker detail failure should not block all workers.
            worker_detail = {}

        merged = {**miner, **worker_detail}
        hashrate = to_number(merged.get("hashrate_miner")) or to_number(merged.get("hashrate_user")) or 0.0

        workers[name] = {
            "name": name,
            "worker_name": merged.get("miner_name") or name,
            "raw_worker": merged.get("raw_worker") or name,
            "state": map_worker_state(merged.get("seconds_since_last_share")),
            "last_share": to_number(merged.get("last_share_ts")) or to_number(merged.get("last_seen")) or 0,
            "hash_rate_5m": hashrate,
            "hash_rate_60m": hashrate,
            "hash_rate_24h": hashrate,
            "hash_rate_unit": "h/s",
            "accepted": to_number(merged.get("accepted")) or 0,
            "rejected": to_number(merged.get("rejected")) or 0,
            "dup": to_number(merged.get("dup")) or 0,
            "alert_limit": 0,
            "labels": merged.get("labels") or [],
        }
    return {coin: {"workers": workers}}


def local_stats_payload(coin: str, users: list) -> dict:
    total_hashrate = 0.0
    total_users = 0
    total_workers = 0
    for u in users:
        total_users += 1
        total_hashrate += to_number(u.get("hashrate_user")) or 0.0
        total_workers += int(to_number(u.get("miner_count")) or 0)
    return {
        coin: {
            "pool_60m_hash_rate": total_hashrate,
            "pool_active_users": total_users,
            "pool_active_workers": total_workers,
            "hash_rate_unit": "h/s",
        }
    }


def local_rewards_payload(coin: str) -> dict:
    return {coin: {"daily_rewards": []}}


def empty_profile_payload(coin: str) -> dict:
    return {
        coin: {
            "hash_rate_5m": 0.0,
            "hash_rate_60m": 0.0,
            "hash_rate_24h": 0.0,
            "hash_rate_unit": "h/s",
            "today_reward": 0.0,
            "all_time_reward": 0.0,
            "current_balance": 0.0,
        }
    }


def empty_workers_payload(coin: str) -> dict:
    return {coin: {"workers": {}}}


def empty_stats_payload(coin: str) -> dict:
    return {
        coin: {
            "pool_60m_hash_rate": 0.0,
            "pool_active_users": 0,
            "pool_active_workers": 0,
            "hash_rate_unit": "h/s",
        }
    }


def miner_profile_response(user: dict, coin: str, username: str | None = None) -> dict:
    if MINER_PROVIDER != "local":
        return empty_profile_payload(coin)
    pool_user = resolve_pool_username(user, username)
    if not pool_user:
        return empty_profile_payload(coin)
    detail = local_pool_get(f"/v1/mining/users/{pool_user}")
    if not isinstance(detail, dict):
        raise HTTPException(status_code=502, detail="Local pool API returned unexpected user detail payload")
    return local_profile_payload(coin, detail)


def miner_workers_response(user: dict, coin: str, username: str | None = None) -> dict:
    if MINER_PROVIDER != "local":
        return empty_workers_payload(coin)
    pool_user = resolve_pool_username(user, username)
    if not pool_user:
        return empty_workers_payload(coin)
    detail = local_pool_get(f"/v1/mining/users/{pool_user}")
    if not isinstance(detail, dict):
        raise HTTPException(status_code=502, detail="Local pool API returned unexpected workers payload")
    return local_workers_payload(coin, detail)


def miner_stats_response(coin: str) -> dict:
    if MINER_PROVIDER != "local":
        return empty_stats_payload(coin)
    users = local_pool_get("/v1/mining/users")
    if not isinstance(users, list):
        raise HTTPException(status_code=502, detail="Local pool API returned unexpected users payload")
    return local_stats_payload(coin, users)


def miner_rewards_response(user: dict, coin: str, username: str | None = None) -> dict:
    if MINER_PROVIDER != "local":
        return local_rewards_payload(coin)
    pool_user = resolve_pool_username(user, username)
    if not pool_user:
        return local_rewards_payload(coin)
    return local_rewards_payload(coin)


def build_miner_snapshot(user: dict, coin: str, username: str | None = None) -> dict:
    return {
        "type": "miner_update",
        "coin": coin,
        "profile": miner_profile_response(user, coin, username),
        "workers": miner_workers_response(user, coin, username),
        "stats": miner_stats_response(coin),
        "rewards": miner_rewards_response(user, coin, username),
        "updated_at": datetime.utcnow().isoformat(),
    }

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

class MyTradeResponse(BaseModel):
    id: int
    direction: str
    limitMarket: str
    boughtSold: str
    amountCoins: float
    priceSats: float
    totalSats: float
    feeSats: float
    time: str


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

def format_my_trade(trade_dict, user_id: int):
    price = float(trade_dict["price"])
    qty = float(trade_dict["quantity"])
    is_buyer = int(trade_dict["buyer_user_id"]) == int(user_id)

    direction = "In" if is_buyer else "Out"
    bought_sold = "Bought" if is_buyer else "Sold"
    order_type = trade_dict["buyer_order_type"] if is_buyer else trade_dict["seller_order_type"]

    executed_at = trade_dict.get("executed_at")
    if isinstance(executed_at, str):
        dt = datetime.fromisoformat(executed_at)
    else:
        dt = executed_at
    time_str = dt.strftime("%m/%d/%y %H:%M:%S")

    return MyTradeResponse(
        id=trade_dict["id"],
        direction=direction,
        limitMarket=(order_type or "market").capitalize(),
        boughtSold=bought_sold,
        amountCoins=qty,
        priceSats=price,
        totalSats=price * qty,
        feeSats=0.0,  # no fee column in schema yet
        time=time_str,
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

@app.get("/api/orders/mine")
def poll_my_orders(request: Request):
    user = get_current_user(request.headers.get("authorization"))
    try:
        return {"orders": [format_order(o) for o in get_orders_by_user(user["id"])]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
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

@app.get("/api/trades/mine")
def poll_my_trades(request: Request):
    user = get_current_user(request.headers.get("authorization"))
    try:
        rows = get_trades_by_user(user["id"])
        return {"trades": [format_my_trade(t, user["id"]) for t in rows]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/candles")
def get_candles(limit: int = 120):
    try:
        return {"candles": get_historical_candles(limit=limit)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Miner Endpoints ────────────────────────────────────────────────────────

@app.get("/api/miner/profile")
@app.get("/api/miner/braiins/profile")
def braiins_profile(request: Request, coin: str = "btc", username: str | None = None):
    user = get_current_user(request.headers.get("authorization"))
    return miner_profile_response(user, coin, username)


@app.get("/api/miner/workers")
@app.get("/api/miner/braiins/workers")
def braiins_workers(request: Request, coin: str = "btc", username: str | None = None):
    user = get_current_user(request.headers.get("authorization"))
    return miner_workers_response(user, coin, username)


@app.get("/api/miner/stats")
@app.get("/api/miner/braiins/stats")
def braiins_stats(request: Request, coin: str = "btc"):
    get_current_user(request.headers.get("authorization"))
    return miner_stats_response(coin)


@app.get("/api/miner/rewards")
@app.get("/api/miner/braiins/rewards")
def braiins_rewards(
    request: Request,
    coin: str = "btc",
    from_date: str | None = Query(default=None, alias="from"),
    to_date: str | None = Query(default=None, alias="to"),
    username: str | None = None,
):
    user = get_current_user(request.headers.get("authorization"))
    return miner_rewards_response(user, coin, username)


@app.websocket("/ws/miner")
async def websocket_miner(websocket: WebSocket):
    await websocket.accept()
    try:
        token = websocket.query_params.get("token")
        if not token:
            await websocket.send_json({"type": "error", "detail": "Missing token query param"})
            await websocket.close(code=1008)
            return

        coin = (websocket.query_params.get("coin") or "btc").lower()
        username = websocket.query_params.get("username")
        user = get_current_user(f"Bearer {token}")

        while True:
            payload = build_miner_snapshot(user, coin, username)
            await websocket.send_json(payload)
            await asyncio.sleep(5)
    except HTTPException as e:
        try:
            await websocket.send_json({"type": "error", "detail": e.detail})
        finally:
            await websocket.close(code=1008)
    except WebSocketDisconnect:
        return
    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "detail": str(e)})
        finally:
            await websocket.close(code=1011)