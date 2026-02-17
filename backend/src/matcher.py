#!/usr/bin/env python3
# src/matcher.py
"""
Simple matching engine:
- Reads existing orders from the DB (does not create new orders)
- Matches market/limit orders according to the rules you specified
- Inserts rows into `trades` and updates `orders.remaining_quantity` and `orders.status`
- Uses transactions to keep updates atomic and prints each executed trade
- Broadcasts updates to connected WebSocket clients
- Runs continuously until interrupted (Ctrl+C)
"""

import json
import sqlite3
import time
from datetime import datetime

# flexible import so the script works whether run from repo root or from src/
try:
    from db import get_connection
    from broadcast import broadcast_trade
except Exception:
    from src.db import get_connection
    from src.broadcast import broadcast_trade


def _fetch_best(cur, side):
    if side == "buy":
        cur.execute(
            """
            SELECT *
            FROM orders
            WHERE status = 'open' AND side = 'buy'
            ORDER BY price DESC NULLS LAST, created_at ASC
            LIMIT 1
            """
        )
    else:
        cur.execute(
            """
            SELECT *
            FROM orders 
            WHERE status = 'open' AND side = 'sell'
            ORDER BY price ASC NULLS LAST, created_at ASC
            LIMIT 1
            """
        )
    return cur.fetchone()


def _insert_trade(cur, buy_id, sell_id, price, quantity):
    cur.execute(
        "INSERT INTO trades (buy_order_id, sell_order_id, price, quantity) VALUES (?, ?, ?, ?)",
        (buy_id, sell_id, price, quantity),
    )
    return cur.lastrowid


def _update_order_after_fill(cur, order_id, remaining_quantity):
    """Update order status: filled if remaining is 0, otherwise keep as open (partial)"""
    if remaining_quantity <= 0:
        cur.execute(
            "UPDATE orders SET remaining_quantity = 0, status = 'filled' WHERE id = ?",
            (order_id,),
        )
    else:
        # Keep status as 'open' even if partially filled
        # Frontend will determine 'partial' status based on remaining_quantity < quantity
        cur.execute(
            "UPDATE orders SET remaining_quantity = ? WHERE id = ?",
            (remaining_quantity, order_id),
        )


def _to_dict(row):
    return dict(row) if row is not None else None


def match_loop():
    """
    Runs matching continuously until interrupted (Ctrl+C).
    Keeps matching trades as new orders come in.
    Broadcasts updates to connected WebSocket clients after each trade.
    """
    print("[Matcher] Started. Waiting for orders...")
    
    while True:
        try:
            conn = get_connection()
            cur = conn.cursor()
            
            # Acquire write lock to avoid races
            cur.execute("BEGIN IMMEDIATE;")

            bid_row = _fetch_best(cur, "buy")
            ask_row = _fetch_best(cur, "sell")

            if not bid_row or not ask_row:
                conn.rollback()
                conn.close()
                # No match found, sleep and try again
                time.sleep(0.5)
                continue

            bid = _to_dict(bid_row)
            ask = _to_dict(ask_row)

            # Market BUY (buyer is market)
            if bid["type"] == "market":
                market = bid
                while market["remaining_quantity"] > 0:
                    cur.execute(
                        """
                        SELECT *
                        FROM orders
                        WHERE status = 'open' AND side = 'sell'
                        ORDER BY price ASC, created_at ASC
                        LIMIT 1
                        """
                    )
                    ask_row = cur.fetchone()
                    if not ask_row:
                        break
                    ask = _to_dict(ask_row)
                    exec_qty = min(market["remaining_quantity"], ask["remaining_quantity"])
                    exec_price = ask["price"]
                    _insert_trade(cur, market["id"], ask["id"], exec_price, exec_qty)
                    market["remaining_quantity"] -= exec_qty
                    ask["remaining_quantity"] -= exec_qty
                    _update_order_after_fill(cur, market["id"], market["remaining_quantity"])
                    _update_order_after_fill(cur, ask["id"], ask["remaining_quantity"])
                    conn.commit()
                    trade_info = {
                        "buy_id": market["id"],
                        "sell_id": ask["id"],
                        "price": float(exec_price),
                        "quantity": float(exec_qty)
                    }
                    print(f"[Trade] {json.dumps(trade_info)}")
                    # Broadcast the trade to all connected clients
                    broadcast_trade(trade_info)
                # done processing this market buy; continue outer loop to find next matches
                continue

            # Market SELL (seller is market)
            if ask["type"] == "market":
                market = ask
                while market["remaining_quantity"] > 0:
                    cur.execute(
                        """
                        SELECT *
                        FROM orders
                        WHERE status = 'open' AND side = 'buy'
                        ORDER BY price DESC, created_at ASC
                        LIMIT 1
                        """
                    )
                    bid_row = cur.fetchone()
                    if not bid_row:
                        break
                    bid = _to_dict(bid_row)
                    exec_qty = min(market["remaining_quantity"], bid["remaining_quantity"])
                    exec_price = bid["price"]
                    _insert_trade(cur, bid["id"], market["id"], exec_price, exec_qty)
                    market["remaining_quantity"] -= exec_qty
                    bid["remaining_quantity"] -= exec_qty
                    _update_order_after_fill(cur, market["id"], market["remaining_quantity"])
                    _update_order_after_fill(cur, bid["id"], bid["remaining_quantity"])
                    conn.commit()
                    trade_info = {
                        "buy_id": bid["id"],
                        "sell_id": market["id"],
                        "price": float(exec_price),
                        "quantity": float(exec_qty)
                    }
                    print(f"[Trade] {json.dumps(trade_info)}")
                    # Broadcast the trade to all connected clients
                    broadcast_trade(trade_info)
                continue

            # Both limit (or at least none are market): match if prices cross
            # Price None safety
            bid_price = bid["price"]
            ask_price = ask["price"]
            if bid_price is None or ask_price is None:
                conn.rollback()
                conn.close()
                time.sleep(0.5)
                continue

            if float(bid_price) >= float(ask_price):
                exec_qty = min(bid["remaining_quantity"], ask["remaining_quantity"])
                exec_price = ask_price  # execution price is best_ask.price
                _insert_trade(cur, bid["id"], ask["id"], exec_price, exec_qty)
                bid["remaining_quantity"] -= exec_qty
                ask["remaining_quantity"] -= exec_qty
                _update_order_after_fill(cur, bid["id"], bid["remaining_quantity"])
                _update_order_after_fill(cur, ask["id"], ask["remaining_quantity"])
                conn.commit()
                trade_info = {
                    "buy_id": bid["id"],
                    "sell_id": ask["id"],
                    "price": float(exec_price),
                    "quantity": float(exec_qty)
                }
                print(f"[Trade] {json.dumps(trade_info)}")
                # Broadcast the trade to all connected clients
                broadcast_trade(trade_info)
                continue
            else:
                conn.rollback()
                conn.close()
                # No match found, sleep and try again
                time.sleep(0.5)
                continue
                
        except sqlite3.DatabaseError as e:
            try:
                conn.rollback()
            except:
                pass
            print(f"[Error] DB error: {e}")
            time.sleep(0.5)
            continue
        except KeyboardInterrupt:
            print("\n[Matcher] Shutting down gracefully...")
            break
        except Exception as e:
            try:
                conn.rollback()
            except:
                pass
            print(f"[Error] Unexpected error: {e}")
            time.sleep(0.5)
            continue
        finally:
            try:
                conn.close()
            except:
                pass


if __name__ == "__main__":
    match_loop()