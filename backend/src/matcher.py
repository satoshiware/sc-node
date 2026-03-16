import json
import sqlite3
import time
import traceback

SLEEP_TIME = 0.2
EPS = 1e-9

try:
    from db import get_connection
    from broadcast import broadcast_trade
    from wallets import settle_trade
except Exception:
    from src.db import get_connection
    from src.broadcast import broadcast_trade
    from src.wallets import settle_trade


# ─── Fetch helpers ────────────────────────────────────────────────────────────

def fetch_best_limit(cur, side, exclude_user=None):
    """Best open LIMIT order for side, optionally excluding a user."""
    if side == "buy":
        cur.execute("""
            SELECT * FROM orders
            WHERE status='open' AND side='buy' AND type='limit'
              AND (? IS NULL OR user_id IS NULL OR user_id != ?)
            ORDER BY price DESC, created_at ASC
            LIMIT 1
        """, (exclude_user, exclude_user))
    else:
        cur.execute("""
            SELECT * FROM orders
            WHERE status='open' AND side='sell' AND type='limit'
              AND (? IS NULL OR user_id IS NULL OR user_id != ?)
            ORDER BY price ASC, created_at ASC
            LIMIT 1
        """, (exclude_user, exclude_user))
    row = cur.fetchone()
    return dict(row) if row else None


def fetch_executable_market_buy(cur):
    """
    Oldest market buy that has at least one eligible limit sell
    from a different user (or either side is anonymous).
    """
    cur.execute("""
        SELECT b.* FROM orders b
        WHERE b.status='open' AND b.side='buy' AND b.type='market'
          AND EXISTS (
              SELECT 1 FROM orders a
              WHERE a.status='open' AND a.side='sell' AND a.type='limit'
                AND (b.user_id IS NULL OR a.user_id IS NULL OR b.user_id != a.user_id)
          )
        ORDER BY b.created_at ASC
        LIMIT 1
    """)
    row = cur.fetchone()
    return dict(row) if row else None


def fetch_executable_market_sell(cur):
    """
    Oldest market sell that has at least one eligible limit buy
    from a different user (or either side is anonymous).
    """
    cur.execute("""
        SELECT a.* FROM orders a
        WHERE a.status='open' AND a.side='sell' AND a.type='market'
          AND EXISTS (
              SELECT 1 FROM orders b
              WHERE b.status='open' AND b.side='buy' AND b.type='limit'
                AND (a.user_id IS NULL OR b.user_id IS NULL OR a.user_id != b.user_id)
          )
        ORDER BY a.created_at ASC
        LIMIT 1
    """)
    row = cur.fetchone()
    return dict(row) if row else None


def fetch_crossing_limit_buy(cur):
    """
    Best limit buy (highest price) that crosses with at least one limit sell
    from a different user.
    """
    cur.execute("""
        SELECT b.* FROM orders b
        WHERE b.status='open' AND b.side='buy' AND b.type='limit'
          AND EXISTS (
              SELECT 1 FROM orders a
              WHERE a.status='open' AND a.side='sell' AND a.type='limit'
                AND a.price <= b.price
                AND (b.user_id IS NULL OR a.user_id IS NULL OR b.user_id != a.user_id)
          )
        ORDER BY b.price DESC, b.created_at ASC
        LIMIT 1
    """)
    row = cur.fetchone()
    return dict(row) if row else None


# ─── Order helpers ────────────────────────────────────────────────────────────

def update_order(cur, order_id, remaining):
    if remaining <= EPS:
        cur.execute("""
            UPDATE orders SET remaining_quantity=0, status='filled' WHERE id=?
        """, (order_id,))
    else:
        cur.execute("""
            UPDATE orders SET remaining_quantity=? WHERE id=?
        """, (remaining, order_id))


def insert_trade(cur, bid, ask, price, qty):
    cur.execute("""
        INSERT INTO trades (buy_order_id, sell_order_id, price, quantity)
        VALUES (?, ?, ?, ?)
    """, (bid["id"], ask["id"], float(price), float(qty)))
    return cur.lastrowid


# ─── Main loop ────────────────────────────────────────────────────────────────

def match_loop():
    print("[Matcher] started")

    while True:
        conn = None
        try:
            conn = get_connection()
            conn.isolation_level = None
            cur = conn.cursor()
            cur.execute("BEGIN IMMEDIATE")

            bid = None
            ask = None

            # ── Priority 1: market buy vs best eligible limit sell ────────────
            market_bid = fetch_executable_market_buy(cur)
            if market_bid:
                candidate_ask = fetch_best_limit(cur, "sell", market_bid.get("user_id"))
                if candidate_ask:
                    bid, ask = market_bid, candidate_ask

            # ── Priority 2: best eligible limit buy vs market sell ────────────
            if not bid or not ask:
                market_ask = fetch_executable_market_sell(cur)
                if market_ask:
                    candidate_bid = fetch_best_limit(cur, "buy", market_ask.get("user_id"))
                    if candidate_bid:
                        bid, ask = candidate_bid, market_ask

            # ── Priority 3: crossing limit buy vs limit sell ──────────────────
            if not bid or not ask:
                crossing_bid = fetch_crossing_limit_buy(cur)
                if crossing_bid:
                    candidate_ask = fetch_best_limit(cur, "sell", crossing_bid.get("user_id"))
                    if candidate_ask and float(candidate_ask["price"]) <= float(crossing_bid["price"]):
                        bid, ask = crossing_bid, candidate_ask

            # ── No executable pair found ──────────────────────────────────────
            if not bid or not ask:
                conn.rollback()
                conn.close()
                time.sleep(SLEEP_TIME)
                continue

            # ── Trade price: always the resting limit order's price ───────────
            if ask["type"] == "limit":
                trade_price = float(ask["price"])
            else:
                # ask is market → bid must be limit
                trade_price = float(bid["price"])

            # ── Trade quantity ────────────────────────────────────────────────
            trade_qty = round(min(
                float(bid["remaining_quantity"]),
                float(ask["remaining_quantity"])
            ), 8)

            if trade_qty <= EPS:
                conn.rollback()
                conn.close()
                time.sleep(SLEEP_TIME)
                continue

            # ── Execute ───────────────────────────────────────────────────────
            trade_id = insert_trade(cur, bid, ask, trade_price, trade_qty)
            settle_trade(cur, bid["id"], ask["id"], trade_qty, trade_price)
            update_order(cur, bid["id"], float(bid["remaining_quantity"]) - trade_qty)
            update_order(cur, ask["id"], float(ask["remaining_quantity"]) - trade_qty)

            conn.commit()
            conn.close()

            trade_record = {
                "trade_id": trade_id,
                "buy_id":   bid["id"],
                "sell_id":  ask["id"],
                "price":    trade_price,
                "quantity": trade_qty,
            }
            print("[Trade]", json.dumps(trade_record))
            broadcast_trade([trade_record])

        except sqlite3.OperationalError as e:
            if conn:
                try:
                    conn.rollback()
                    conn.close()
                except Exception:
                    pass
            if "locked" in str(e):
                time.sleep(0.2)
            else:
                print("[Matcher] OperationalError:", e)

        except Exception as e:
            if conn:
                try:
                    conn.rollback()
                    conn.close()
                except Exception:
                    pass
            print("[Matcher] error:", e)
            traceback.print_exc()
            time.sleep(1)

        time.sleep(SLEEP_TIME)


# ───────────────── ENTRYPOINT ───────────────── #

if __name__ == "__main__":
    match_loop()