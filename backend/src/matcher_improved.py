#!/usr/bin/env python3
"""
Matching engine — non-IOC market orders.
Market orders stay open until fully filled against available limit orders.
"""

import json
import sqlite3
import time
import traceback

try:
    from db import get_connection
    from broadcast import broadcast_trade
except Exception:
    from src.db import get_connection
    from src.broadcast import broadcast_trade


# ─── Fetch Helpers ────────────────────────────────────────────────────────────

def _fetch_best(cur, side):
    """Best open order for side — market first, then best price, then oldest."""
    if side == "buy":
        cur.execute("""
            SELECT * FROM orders
            WHERE status = 'open' AND side = 'buy'
            ORDER BY
                CASE WHEN type = 'market' THEN 0 ELSE 1 END ASC,
                CASE WHEN type = 'limit'  THEN price ELSE 0 END DESC,
                created_at ASC
            LIMIT 1
        """)
    else:
        cur.execute("""
            SELECT * FROM orders
            WHERE status = 'open' AND side = 'sell'
            ORDER BY
                CASE WHEN type = 'market' THEN 0 ELSE 1 END ASC,
                CASE WHEN type = 'limit'  THEN price ELSE 9999999999 END ASC,
                created_at ASC
            LIMIT 1
        """)
    row = cur.fetchone()
    return dict(row) if row else None


def _fetch_best_limit(cur, side):
    """Best resting limit order for side."""
    if side == "buy":
        cur.execute("""
            SELECT * FROM orders
            WHERE status = 'open' AND side = 'buy' AND type = 'limit'
            ORDER BY price DESC, created_at ASC
            LIMIT 1
        """)
    else:
        cur.execute("""
            SELECT * FROM orders
            WHERE status = 'open' AND side = 'sell' AND type = 'limit'
            ORDER BY price ASC, created_at ASC
            LIMIT 1
        """)
    row = cur.fetchone()
    return dict(row) if row else None


# ─── DB Write Helpers ─────────────────────────────────────────────────────────

def _insert_trade(cur, buy_id, sell_id, price, quantity):
    cur.execute(
        "INSERT INTO trades (buy_order_id, sell_order_id, price, quantity) VALUES (?, ?, ?, ?)",
        (buy_id, sell_id, float(price), float(quantity)),
    )
    tid = cur.lastrowid
    print(f"[Matcher] ✓ Trade #{tid}  buy={buy_id} sell={sell_id}  "
          f"price={price:.2f}  qty={quantity:.8f}")
    return tid


def _update_order(cur, order_id, remaining_qty):
    """
    Schema: open | filled | cancelled  (no 'partial')
    Partial fill → status stays 'open', remaining_quantity reduced.
    Full fill    → status = 'filled',  remaining_quantity = 0.
    """
    remaining_qty = round(max(0.0, float(remaining_qty)), 8)
    if remaining_qty <= 0:
        cur.execute(
            "UPDATE orders SET remaining_quantity = 0, status = 'filled' WHERE id = ?",
            (order_id,),
        )
        print(f"[Matcher]   Order {order_id} → FILLED")
    else:
        cur.execute(
            "UPDATE orders SET remaining_quantity = ? WHERE id = ?",
            (remaining_qty, order_id),
        )
        print(f"[Matcher]   Order {order_id} → PARTIAL (rem={remaining_qty})")


# ─── Fill Helpers ─────────────────────────────────────────────────────────────

def _fill(cur, bid, ask, exec_price, trades_out):
    """
    Execute one fill between bid and ask at exec_price.
    Mutates bid/ask dicts in-place.
    Appends trade info to trades_out.
    """
    qty = round(
        min(float(bid["remaining_quantity"]), float(ask["remaining_quantity"])),
        8
    )
    if qty <= 0:
        return

    _insert_trade(cur, bid["id"], ask["id"], exec_price, qty)
    bid["remaining_quantity"] = round(float(bid["remaining_quantity"]) - qty, 8)
    ask["remaining_quantity"] = round(float(ask["remaining_quantity"]) - qty, 8)
    _update_order(cur, bid["id"], bid["remaining_quantity"])
    _update_order(cur, ask["id"], ask["remaining_quantity"])

    trades_out.append({
        "buy_id":   bid["id"],
        "sell_id":  ask["id"],
        "price":    float(exec_price),
        "quantity": float(qty),
    })


# ─── Main Loop ────────────────────────────────────────────────────────────────

def match_loop():
    print("[Matcher] Started — waiting for matchable orders")
    consecutive_errors = 0

    while True:
        conn = None
        trades_executed = []

        try:
            conn = get_connection()
            cur  = conn.cursor()

            # ── snapshot: one transaction per matching cycle ───────────────────
            # All fills in this cycle are committed atomically at the end.
            # Non-IOC: market orders are NOT cancelled if no counterparty exists —
            # they stay 'open' and will be matched in the next cycle.

            bid = _fetch_best(cur, "buy")
            ask = _fetch_best(cur, "sell")

            # nothing to match
            if bid is None or ask is None:
                conn.close()
                conn = None
                time.sleep(0.3)
                continue

            bid_mkt = bid["type"] == "market"
            ask_mkt = ask["type"] == "market"

            # ── Case 1: both market — find a limit on either side ─────────────
            if bid_mkt and ask_mkt:
                limit_ask = _fetch_best_limit(cur, "sell")
                limit_bid = _fetch_best_limit(cur, "buy")

                if limit_ask:
                    # market buy fills against best limit sell
                    exec_price = float(limit_ask["price"])
                    _fill(cur, bid, limit_ask, exec_price, trades_executed)
                elif limit_bid:
                    # market sell fills against best limit buy
                    exec_price = float(limit_bid["price"])
                    _fill(cur, limit_bid, ask, exec_price, trades_executed)
                else:
                    # no limit orders at all — cannot resolve price
                    conn.close()
                    conn = None
                    time.sleep(0.3)
                    continue

            # ── Case 2: market BUY hits resting limit sells ───────────────────
            elif bid_mkt:
                # Non-IOC: keep looping until market order is fully filled
                # or no more limit sells exist
                while bid["remaining_quantity"] > 0:
                    limit_ask = _fetch_best_limit(cur, "sell")
                    if limit_ask is None:
                        # No limit sells — market order stays open (non-IOC)
                        print(f"[Matcher] Market buy #{bid['id']} partially filled "
                              f"— no more limit sells, order stays open")
                        break
                    exec_price = float(limit_ask["price"])
                    _fill(cur, bid, limit_ask, exec_price, trades_executed)

            # ── Case 3: market SELL hits resting limit buys ───────────────────
            elif ask_mkt:
                while ask["remaining_quantity"] > 0:
                    limit_bid = _fetch_best_limit(cur, "buy")
                    if limit_bid is None:
                        print(f"[Matcher] Market sell #{ask['id']} partially filled "
                              f"— no more limit buys, order stays open")
                        break
                    exec_price = float(limit_bid["price"])
                    _fill(cur, limit_bid, ask, exec_price, trades_executed)

            # ── Case 4: limit vs limit ────────────────────────────────────────
            else:
                bid_price = float(bid["price"])
                ask_price = float(ask["price"])

                if bid_price >= ask_price:
                    # prices cross — keep filling while they still cross
                    while (bid["remaining_quantity"] > 0
                           and ask["remaining_quantity"] > 0
                           and bid_price >= ask_price):
                        _fill(cur, bid, ask, ask_price, trades_executed)

                        # if one side exhausted, try to fetch the next order
                        if bid["remaining_quantity"] <= 0:
                            next_bid = _fetch_best_limit(cur, "buy")
                            if next_bid is None:
                                break
                            bid = next_bid
                            bid_price = float(bid["price"])

                        if ask["remaining_quantity"] <= 0:
                            next_ask = _fetch_best_limit(cur, "sell")
                            if next_ask is None:
                                break
                            ask = next_ask
                            ask_price = float(ask["price"])
                else:
                    # prices don't cross — nothing to do
                    conn.close()
                    conn = None
                    time.sleep(0.3)
                    continue

            # ── commit ALL fills in this cycle atomically ─────────────────────
            if trades_executed:
                conn.commit()
                conn.close()
                conn = None
                consecutive_errors = 0

                for t in trades_executed:
                    print(f"[Trade] {json.dumps(t)}")

                # write signal file ONCE for the whole cycle
                broadcast_trade(trades_executed)
                print(f"[Matcher] Cycle done — {len(trades_executed)} trade(s)")
            else:
                conn.close()
                conn = None
                time.sleep(0.3)

        except KeyboardInterrupt:
            print("\n[Matcher] Shutting down cleanly")
            break

        except sqlite3.OperationalError as e:
            consecutive_errors += 1
            wait = min(0.1 * consecutive_errors, 2.0)
            if "database is locked" in str(e):
                print(f"[Matcher] DB locked — retry in {wait:.1f}s")
            else:
                print(f"[Matcher] OperationalError: {e}")
            time.sleep(wait)
            try:
                if conn:
                    conn.rollback()
                    conn.close()
                    conn = None
            except Exception:
                pass

        except sqlite3.DatabaseError as e:
            consecutive_errors += 1
            print(f"[Matcher] DatabaseError: {e}")
            traceback.print_exc()
            try:
                if conn:
                    conn.rollback()
                    conn.close()
                    conn = None
            except Exception:
                pass
            time.sleep(0.5)

        except Exception as e:
            consecutive_errors += 1
            print(f"[Matcher] Unexpected error: {e}")
            traceback.print_exc()
            try:
                if conn:
                    conn.rollback()
                    conn.close()
                    conn = None
            except Exception:
                pass
            time.sleep(0.5)

        finally:
            try:
                if conn:
                    conn.close()
            except Exception:
                pass


if __name__ == "__main__":
    match_loop()