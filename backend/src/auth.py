# backend/src/auth.py
import os
from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
from fastapi import HTTPException, status

from db import get_connection

# ─── Config ──────────────────────────────────────────────────────────────────

SECRET_KEY = os.environ.get("SECRET_KEY", "change-me-in-production")
ALGORITHM  = "HS256"
TOKEN_EXPIRE_DAYS = 7

# ─── Password helpers ─────────────────────────────────────────────────────────

import bcrypt

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()

def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        return False

# ─── JWT helpers ──────────────────────────────────────────────────────────────

def create_jwt(user_id: int, email: str, name: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=TOKEN_EXPIRE_DAYS)
    payload = {
        "sub":   str(user_id),
        "email": email,
        "name":  name,
        "exp":   expire,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def decode_jwt(token: str) -> dict:
    """Decode and verify a JWT. Raises HTTP 401 on any failure."""
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise credentials_exc
        return {
            "id":    int(user_id),
            "email": payload.get("email"),
            "name":  payload.get("name"),
        }
    except JWTError:
        raise credentials_exc

# ─── DB helpers ───────────────────────────────────────────────────────────────

def get_user_by_email(email: str) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE email = ?", (email.lower().strip(),)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

def get_user_by_id(user_id: int) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

def create_user(email: str, name: str, password_hash: str) -> int:
    """Insert a new user row. Returns the new user's id."""
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO users (email, name, password_hash) VALUES (?, ?, ?)",
            (email.lower().strip(), name.strip(), password_hash),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()

# ─── FastAPI dependency ───────────────────────────────────────────────────────

def get_current_user(authorization: str | None = None) -> dict:
    """
    Extract and validate Bearer token from Authorization header value.
    Usage in endpoint:  user = get_current_user(request.headers.get("authorization"))
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing or malformed",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization.split(" ", 1)[1]
    return decode_jwt(token)