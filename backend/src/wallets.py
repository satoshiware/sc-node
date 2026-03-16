# backend/src/wallets.py
from db import get_connection


# ─── Read ─────────────────────────────────────────────────────────────────────

def get_wallet(user_id: int) -> dict | None:
    """Return { azc, sats } for a user, or None if wallet doesn't exist."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT azc, sats FROM wallets WHERE user_id = ?", (user_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def check_balance(user_id: int, asset: str, amount: float) -> bool:
    """
    Return True if user has >= amount of the given asset.
    asset: 'azc' | 'sats'
    """
    wallet = get_wallet(user_id)
    if wallet is None:
        return False
    return float(wallet[asset]) >= float(amount)


# ─── Write ──────────────────────────────────────────────────────────────────── 

def create_wallet(user_id: int, azc: float = 1000.0, sats: float = 1_000_000.0) -> None:
    """Create a wallet for a new user with default starting balances."""
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO wallets (user_id, azc, sats) VALUES (?, ?, ?)",
            (user_id, azc, sats),
        )
        conn.commit()
    finally:
        conn.close()


# ─── Settlement (called by matcher — uses shared cursor) ──────────────────────

def settle_trade(cur, buy_order_id: int, sell_order_id: int, qty: float, price: float) -> None:
    """
    Update wallet balances for a completed fill.

    MUST be called with the matcher's active cursor so the wallet updates
    are part of the same atomic transaction as the trade insert.

    Settlement:
      buyer  → +qty AZC,  -(qty × price) SATS
      seller → -qty AZC,  +(qty × price) SATS

    Sides with user_id = NULL (bot orders) are silently skipped.
    """
    qty        = round(float(qty),   8)
    sats_total = round(qty * float(price), 8)

    # look up user_id from both order rows
    buy_row  = cur.execute(
        "SELECT user_id FROM orders WHERE id = ?", (buy_order_id,)
    ).fetchone()
    sell_row = cur.execute(
        "SELECT user_id FROM orders WHERE id = ?", (sell_order_id,)
    ).fetchone()

    buy_user_id  = buy_row["user_id"]  if buy_row  else None
    sell_user_id = sell_row["user_id"] if sell_row else None

    # ── Buyer: +AZC, -SATS ───────────────────────────────────────────────────
    if buy_user_id is not None:
        cur.execute(
            """
            UPDATE wallets
               SET azc        = azc  + ?,
                   sats       = sats - ?,
                   updated_at = datetime('now')
             WHERE user_id = ?
            """,
            (qty, sats_total, buy_user_id),
        )
        print(f"[Wallets] Buyer  #{buy_user_id}  +{qty} AZC  -{sats_total} SATS")

    # ── Seller: -AZC, +SATS ──────────────────────────────────────────────────
    if sell_user_id is not None:
        cur.execute(
            """
            UPDATE wallets
               SET azc        = azc  - ?,
                   sats       = sats + ?,
                   updated_at = datetime('now')
             WHERE user_id = ?
            """,
            (qty, sats_total, sell_user_id),
        )
        print(f"[Wallets] Seller #{sell_user_id}  -{qty} AZC  +{sats_total} SATS")