# CoinBot Exchange — Project Progress

---

## At a Glance

| Area | Files | Status |
|---|---|---|
| Backend core | 9 source files | ✅ Live |
| Database | 2 tables, 1 SQLite DB | ✅ WAL mode |
| Matching engine | 4 order-case logic, continuous loop | ✅ Running |
| WebSocket channels | 4 channels | ✅ Broadcasting |
| REST endpoints | 9 endpoints | ✅ Active |
| Frontend components | 15 components | 🔶 10/15 wired |
| Auth | Login UI exists | ⏳ Not wired |
| Wallet / Balances | UI shells exist | ⏳ Not wired |

---

## Backend (`backend/src/` — 9 files)

### 1. `db.py`
- SQLite connection factory
- WAL mode: `PRAGMA journal_mode=WAL`, `busy_timeout=5000`, `synchronous=NORMAL`
- Enables concurrent reads while matcher writes

### 2. `matcher.py` — 314 lines
- Continuous non-IOC loop (separate process, never stops)
- Handles **4 matching cases**:
  1. Both sides market → resolve via best limit on either side
  2. Market BUY → loops against all resting limit sells until filled
  3. Market SELL → loops against all resting limit buys until filled
  4. Limit vs Limit → fills while `bid_price >= ask_price`
- Single atomic `conn.commit()` per cycle (all fills or none)
- `broadcast_trade()` called **once per cycle** to avoid signal floods
- Exponential backoff on DB lock errors (`consecutive_errors` counter, max 2s wait)
- Status rule: only `open` and `filled` written to DB — `partial` is display-layer only

### 3. `api.py` — 406 lines
- FastAPI app with full CORS
- **4 WebSocket connection managers** (orders, trades, candles, stats)
- **4 Pydantic models**: `PlaceOrderRequest`, `OrderResponse`, `TradeResponse`, `CandleResponse`
- `format_order()` derives display "Partial": `status=open` + `remaining_qty < qty`
- `priceSats: str | None` handles market orders (no price)
- **WebSocket endpoints (4)**: `/ws/orders`, `/ws/trades`, `/ws/candles`, `/ws/market_stats`
- **REST endpoints (9)**: `GET /api/health`, `GET /api/orders`, `GET /api/orders/poll`, `GET /api/orders/bid`, `GET /api/orders/ask`, `POST /api/orders`, `GET /api/trades`, `GET /api/trades/poll`, `GET /api/candles`

### 4. `broadcast.py` — 159 lines
- File-based IPC: matcher writes `.trade_signal` → API polls mtime every 100ms → fires `broadcast_all()`
- `broadcast_all()` uses `asyncio.gather(..., return_exceptions=True)` — one channel failure is isolated
- `_monitor_task` stored as reference to prevent GC; `add_done_callback` auto-restarts on crash
- 4 registered managers: orders, trades, candles, stats

### 5. `orders.py`
- `get_open_orders()`, `get_best_bid()`, `get_best_ask()`
- `place_order()`, `get_all_user_orders()`, `get_order_by_id()`

### 6. `trades.py`
- `get_all_trades()`, `get_recent_trades(limit=100)` — both ordered by `executed_at DESC`

### 7. `candles.py`
- 5-second OHLCV bucket aggregation from `trades.executed_at`
- `get_historical_candles(limit=120)` — last N candles ascending
- `get_candle_timestamp()` rounds to nearest 5s bucket

### 8. `market_stats.py`
- `get_market_stats()` — last price, 24h high/low, volume, % change
- Broadcast every 2 seconds via `/ws/market_stats`

### 9. `bots.py`
- Automated order insertion (simulated market activity)
- Configured via `backend/.env` — ✅ running and inserting live orders

---

## Database (`backend/db/`)

### Tables: 2

**`orders`**
| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| side | TEXT | `buy` or `sell` |
| type | TEXT | `limit` or `market` |
| price | NUMERIC | NULL for market orders |
| quantity | NUMERIC | original size |
| remaining_quantity | NUMERIC | decremented on fills |
| status | TEXT | `open`, `filled`, `cancelled` — no `partial` in DB |
| created_at | DATETIME | auto |

**`trades`**
| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| buy_order_id | INTEGER FK | → orders(id) |
| sell_order_id | INTEGER FK | → orders(id) |
| price | NUMERIC | execution price |
| quantity | NUMERIC | filled quantity |
| executed_at | DATETIME | auto |

---

## Frontend (`frontend/src/` — 15 components)

### Wired to Backend ✅ (10 / 15)

| Component | Data Source | Notes |
|---|---|---|
| `Header.jsx` | `/ws/market_stats` | Last price, 24h change %, volume, high, low |
| `OrderBook.jsx` | `/ws/orders` | Limit only, `remaining_qty > 0`, 8 gap options (1–500 sats) |
| `DepthChart.jsx` | `/ws/orders` | Prefix-sum cumulative curves, ±25% mid window |
| `TradeHistory.jsx` | `/ws/trades` | Latest on top, green/red side coloring |
| `LeftChart.jsx` | `/ws/candles` | Chart.js candlesticks, 5s OHLCV, toggles to DepthChart |
| `OrdersTable.jsx` | `/api/orders/poll` | All open orders display |
| `OrderManagement.jsx` | `/api/orders` | Order management view |
| `Login.jsx` | — | UI complete, backend not wired yet |
| `MarketSelect.jsx` | — | Static/local |
| `Exchange.jsx` | — | View container |

### UI Placeholders ⏳ (5 / 15)

| Component | Status |
|---|---|
| `BuyPanel.jsx` | Static form — not posting to `/api/orders` yet |
| `Wallet.jsx` | Display only — no balance endpoints |
| `ManageFunds.jsx` | UI shell only |
| `Deposite.jsx` | UI shell only |
| `Profile.jsx` | UI shell only |

### Key State (`App.jsx`)
- `priceGap` (default `1`) — owned in App, passed to `OrderBook` + `LeftChart` → `DepthChart`
- `user` — loaded from `localStorage`, drives auth gate (Login wall)
- `view` — `home` / `orders` / `wallet` / `exchange`

### OrderBook + DepthChart Sync
- 8 gap options: `[1, 5, 10, 25, 50, 100, 250, 500]` sats
- Bucketing: `Math.floor(price / priceGap) * priceGap`
- Stale closure fix: `priceGapRef` + `rowDepthRef` used inside `onmessage`
- DepthChart mid price from raw unbucketed best bid/ask; curves use bucketed data

---

## Configuration

| File | Controls |
|---|---|
| `backend/.env` | DB path, bot start price, randomness, API host/port |
| `frontend/.env` | `VITE_WS_URL`, `VITE_API_URL` via `import.meta.env` |

---