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