A few things I need to nail down before designing this: 

Analyzing your answers...

Clear picture. Bots are out, users are the only order placers from now on. Here's the full plan:

---

## Plan: Testing Wallet + Auth + Live Settlement

**TL;DR:** Build a `users` + `wallets` table, real JWT auth, balance-checked order placement, and matcher-driven wallet settlement — all in sync. Bots are disabled. Users log in, place orders from BuyPanel, the matcher fills them, and both the `trades` table and wallet balances update atomically.

---

**Phase 1 — Schema (DB foundation)**

1. Add to schema.sql:
   - `users` table: `id`, `email` (UNIQUE), `name`, `password_hash`, `created_at`
   - `wallets` table: `id`, `user_id` FK → users, `azc` NUMERIC DEFAULT 0, `sats` NUMERIC DEFAULT 0, `updated_at`
   - `ALTER TABLE orders ADD COLUMN user_id INTEGER REFERENCES users(id)` — nullable, bot orders stay NULL

2. Create `backend/db/seed.py` — inserts 3–5 test users with bcrypt-hashed passwords + starting balances (e.g. `1000 AZC`, `5,000,000 SATS` each). Run once to populate.

3. Run migration: `ALTER TABLE orders ADD COLUMN user_id INTEGER REFERENCES users(id)` against live `exchange.db` (non-destructive, no data loss)

---

**Phase 2 — Backend auth & wallet logic**

4. **Create `backend/src/auth.py`**:
   - `hash_password(plain)` → bcrypt string
   - `verify_password(plain, hashed)` → bool
   - `create_jwt(user_id, email, name)` → signed token, 7-day expiry, `SECRET_KEY` from .env
   - `decode_jwt(token)` → payload dict or raises `401`
   - `get_user_by_email(email)`, `create_user(email, name, password_hash)` → DB helpers

5. **Create `backend/src/wallets.py`**:
   - `get_wallet(user_id)` → `{ azc, sats }`
   - `check_balance(user_id, asset, amount)` → bool (used before order placement)
   - `settle_trade(buy_order_id, sell_order_id, qty, price)` — called by matcher:
     - Looks up `user_id` on each order
     - If buyer has `user_id`: `azc += qty`, `sats -= qty × price`
     - If seller has `user_id`: `azc -= qty`, `sats += qty × price`
     - Skips NULL `user_id` sides (old bot orders in DB, nothing to settle)
   - All updates atomic within the same connection/transaction passed in from matcher

6. **Add auth + wallet endpoints in api.py**:
   - `POST /api/auth/register` → hash password → insert user + create wallet with default balance → return `{ token, user: { id, name, email } }`
   - `POST /api/auth/login` → verify password → return `{ token, user: { id, name, email } }`
   - `GET /api/auth/me` → decode Bearer token → return user info (validates stored token on load)
   - `GET /api/wallet` → requires Bearer token → return `{ azc, sats }`
 ---------------------------------- current checkpoint! -------------------------------------------
 
7. **Update `POST /api/orders`**:
   - Require `Authorization: Bearer <token>` header — decode to get `user_id`
   - Check `wallets.check_balance()` before inserting:
     - BUY (limit): needs `qty × price` SATS
     - SELL (limit): needs `qty` AZC  
     - MARKET BUY: needs any SATS > 0 (fill price unknown; full deduction happens at settlement)
     - MARKET SELL: needs `qty` AZC
   - If insufficient → return `400 { detail: "Insufficient balance" }`
   - Tag order with `user_id` on insert

---

**Phase 3 — Matcher settlement**

8. **Update matcher.py**:
   - Import `settle_trade` from `wallets.py`
   - After each `_fill()` inside the matching cycle, call `settle_trade(bid_id, ask_id, qty, exec_price, cur)` — **pass the same cursor** so it's part of the same atomic transaction
   - On commit: trades table + wallet updates all committed together. On rollback: all reverted.

---

**Phase 4 — Disable bots**

9. **bots.py**: add a `BOTS_ENABLED` flag read from .env. Set `BOTS_ENABLED=false` in `backend/.env`. No code deletion — just gated so they can be re-enabled for testing.

---

**Phase 5 — Frontend wiring**

10. **auth.js**: already calls correct endpoints. Verify response shape matches `{ token, user: { id, name, email } }`.

11. **App.jsx**:
    - Extend stored user shape to include `token`: `{ id, name, email, token }`
    - On app load: call `GET /api/auth/me` with stored token → 401 = clear + show login, 200 = keep logged in
    - Pass `user` to `<BuyPanel user={user} />`
    - Add `balances` fetch: `GET /api/wallet` with token → `setBalances({ azc, sats })`

12. **BuyPanel.jsx**:
    - Add `Authorization: Bearer ${user.token}` header to `POST /api/orders`
    - After success, re-fetch wallet: `GET /api/wallet` → update `balances` via callback to App.jsx

13. **Wallet.jsx**:
    - Replace hardcoded balances with `GET /api/wallet` (already gets `balances` prop from App.jsx — just needs App.jsx to fetch real data)

14. **Login.jsx**:
    - Keep mock fallback ✅ — mock users have no `token`, BuyPanel sends no auth header, orders get `user_id = NULL`

---

**Verification**
1. Run `seed.py` → check 3+ users + wallets in DB
2. Login as test user → `GET /api/auth/me` returns correct user → token valid
3. Place limit sell 10 AZC → wallet shows `azc - 10` immediately in Wallet view
4. Place limit buy matching the sell → matcher fills → `trades` row + wallet settlement in same commit → both users' balances updated
5. Place buy with 0 SATS → `400 Insufficient balance` returned
6. Refresh page → token re-validated, stay logged in
7. `BOTS_ENABLED=false` → bots do not insert any orders

---

**Decisions**
- No "reserved" balance concept yet — balance is checked at order time and deducted at fill time; double-spend possible only if two orders race (acceptable for now, can add reservation later)
- Wallet balance for new registrations: set in api.py `register` handler to a configurable default (e.g. `1000 AZC`, `5,000,000 SATS`) — same as seed data
- Matcher settlement runs in same transaction as the fill — atomically consistent, no partial state
- `SECRET_KEY` for JWT goes in `backend/.env` — never hardcoded