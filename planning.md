# Plan: Login & Register Authentication

## TL;DR
- Add a `users` table to SQLite.
- Create a `backend/src/auth.py` module for password hashing and JWT generation.
- Implement two new endpoints: `/api/auth/register` and `/api/auth/login`.
- Wire the existing `Login.jsx` to the real API and add a Register tab.
- Store JWT in `localStorage` as the auth token.
- Keep the shared order book unchanged — authentication only gates identity and future per-user features (wallet, manual orders).

## Steps

### 1. Add users table to `schema.sql`
Columns:
- `id`
- `email` (UNIQUE)
- `password_hash`
- `username`
- `created_at`

### 2. Install dependencies
Add to backend requirements:
- [`passlib[bcrypt]`](https://passlib.readthedocs.io/en/stable/) for password hashing.
- [`python-jose[cryptography]`](https://python-jose.readthedocs.io/en/latest/) for JWT handling.

### 3. Create `backend/src/auth.py`
Contains:
- `hash_password(plain) → bcrypt hash`
- `verify_password(plain, hashed) → bool`
- `create_jwt(payload) → signed JWT string (exp = 7 days)`
- `decode_jwt(token) → payload dict or raises`
- Functions: `get_user_by_email(email)`, `create_user(email, username, password_hash)`

### 4. Add auth endpoints to `api.py`
Endpoints:
- **POST `/api/auth/register`** — validate email uniqueness, hash password, insert user, return JWT + user info.
- **POST `/api/auth/login`** — look up user by email, verify password, return JWT + user info.
- **GET `/api/auth/me`** — decode JWT from Authorization header, return user info (used for session re-validation).

### 5. Create a FastAPI dependency in `auth.py`: `get_current_user()`
Extracts and validates JWT from Authorization header; used to protect future endpoints like order placement and wallet.

### 6. Update `Login.jsx`
Features:
- Add mode toggle (`login` / `register`) with tabs or links.
- Register form: email + username + password + confirm password.
- Login form: email + password (keep existing styling).
- Both forms POST to `/api/auth/login` or `/api/auth/register` via environment variable (`VITE_API_URL`).
- On success: call `onLogin({ name, email, token })`. Token stored too.
- Show API error messages inline (e.g., "Email already registered").
d
### 7. Update `App.jsx`
such as:
s - Extend user state to store parsed object from localStorage plus token.
s - Save `{ name, email, token }` on login into localStorage.
s - On app load: if token exists, validate with GET `/api/auth/me`. If invalid/expired, clear storage and show login screen.
s - Create a hook (`useAuth()`) or pass down user.token as prop for authenticated requests. Use Authorization header: `'Bearer <token>'`. 

## Verification Criteria
1. POST `/api/auth/register` with new email returns `{ token, user }`, and user appears in DB.
p2. POST `/api/auth/login` with wrong password returns 401 error.
p3. Correct login returns JWT; stored in localStorage; app loads logged-in state.
p4. Refresh page triggers GET `/api/auth/me`, validating token; remains logged in if valid.
p5. Token expiry after 7 days clears localStorage and redirects to login screen.

## Decisions Summary
-JWT over session tokens — stateless; no DB sessions needed.
d-Use passlib[bcrypt] for industry-standard password hashing—no manual salt management required.
d-Store token in localStorage (current pattern). While httpOnly cookies are more secure,
they require CORS cookie configuration which is not implemented here.
d-Combine Register & Login UI into one file (`Login.jsx`) with mode toggle for simplicity of routing.
d-Store users table within existing database (`exchange.db`)—consistent with current infrastructure.