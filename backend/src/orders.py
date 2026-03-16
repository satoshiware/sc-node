# src/orders.py
from db import get_connection

def place_order(side, order_type, price, quantity, user_id=None):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO orders (side, type, price, quantity, remaining_quantity, status, user_id)
        VALUES (?, ?, ?, ?, ?, 'open', ?)
        """,
        (side, order_type, price, quantity, quantity, user_id),
    )

    order_id = cur.lastrowid
    conn.commit()
    conn.close()

    return order_id

def get_all_user_orders():
    """Get all orders (open, partial, filled, cancelled)"""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT *
        FROM orders
        ORDER BY created_at DESC
        """
    )

    rows = cur.fetchall()
    conn.close()

    return [dict(row) for row in rows]

def get_open_orders():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT *
        FROM orders
        WHERE status IN ('open', 'partial')
        ORDER BY created_at ASC
        """
    )

    rows = cur.fetchall()
    conn.close()

    return [dict(row) for row in rows]


def get_open_buy_orders():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT *
        FROM orders
        WHERE status = 'open' AND side = 'buy'
        ORDER BY price DESC, created_at ASC
        """
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_open_sell_orders():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT *
        FROM orders
        WHERE status = 'open' AND side = 'sell'
        ORDER BY price ASC, created_at ASC
        """
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_best_bid():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT *
        FROM orders
        WHERE status = 'open' AND side = 'buy'
        ORDER BY price DESC, created_at ASC
        LIMIT 1
        """
    )
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None

def get_best_ask():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT *
        FROM orders
        WHERE status = 'open' AND side = 'sell'
        ORDER BY price ASC, created_at ASC
        LIMIT 1
        """
    )
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def get_order_by_id(order_id):
    """Get a single order by id"""
    if order_id is None:
        return None
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT *
        FROM orders
        WHERE id = ?
        """,
        (order_id,)
    )
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None