# backend/src/trades.py
from db import get_connection

def get_all_trades():
    """Get all trades ordered by executed_at descending (newest first)"""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT *
        FROM trades
        ORDER BY executed_at DESC
        """
    )

    rows = cur.fetchall()
    conn.close()

    return [dict(row) for row in rows]

def get_recent_trades(limit=100):
    """Get most recent N trades"""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT *
        FROM trades
        ORDER BY executed_at DESC
        LIMIT ?
        """,
        (limit,)
    )

    rows = cur.fetchall()
    conn.close()

    return [dict(row) for row in rows]

def get_trades_by_user(user_id: int):
    """Get most recent N trades where user was buyer or seller."""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT
            t.id,
            t.price,
            t.quantity,
            t.executed_at,
            bo.user_id AS buyer_user_id,
            so.user_id AS seller_user_id,
            bo.type AS buyer_order_type,
            so.type AS seller_order_type
        FROM trades t
        JOIN orders bo ON bo.id = t.buy_order_id
        JOIN orders so ON so.id = t.sell_order_id
        WHERE bo.user_id = ? OR so.user_id = ?
        ORDER BY t.executed_at DESC;
        """,
        (user_id, user_id)
    )

    rows = cur.fetchall()
    conn.close()

    return [dict(row) for row in rows]