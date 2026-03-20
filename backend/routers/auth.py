# Copyright (c) 2025-2026 Alan He. Licensed under AGPL-3.0. See LICENSE.
"""Authentication endpoints: register, login, password reset.

Uses email + password (bcrypt) with JWT tokens.
Requires: JWT_SECRET env var (auto-generated if missing).
Optional: RESEND_API_KEY for password reset emails.
"""

from __future__ import annotations

import os
import uuid
import logging
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel, EmailStr

logger = logging.getLogger("valuescope.auth")

router = APIRouter()

# ── Config ──
JWT_SECRET = os.environ.get("JWT_SECRET", "")
if not JWT_SECRET:
    # Auto-generate for dev; production MUST set JWT_SECRET
    JWT_SECRET = os.urandom(32).hex()
    logger.warning("JWT_SECRET not set — using auto-generated key (will change on restart)")

JWT_ALGORITHM = "HS256"
JWT_EXPIRY_DAYS = 7
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")


# ── Database helpers (SQLite for now, PostgreSQL-ready) ──

def _get_db():
    """Get a connection to the users database (valuations.db for now)."""
    import sqlite3
    db_path = os.environ.get('VS_DB_PATH',
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                     'data', 'valuations.db'))
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _init_users_table():
    """Create users table if not exists."""
    conn = _get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
    # Password reset tokens
    conn.execute("""
        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            token TEXT NOT NULL UNIQUE,
            expires_at TEXT NOT NULL,
            used INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()


# Initialize on import
_init_users_table()


# ── JWT helpers ──

def create_token(user_id: str, email: str) -> str:
    """Create a JWT token."""
    payload = {
        "sub": user_id,
        "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRY_DAYS),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_token(token: str) -> dict | None:
    """Verify and decode a JWT token. Returns payload or None."""
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


# ── Auth dependencies for FastAPI ──

def get_current_user(request: Request) -> str:
    """Extract user_id from JWT. Returns 'local' if no token (anonymous).

    Use this for endpoints that work for both anonymous and logged-in users.
    """
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return "local"
    payload = verify_token(auth[7:])
    if not payload:
        return "local"
    return payload.get("sub", "local")


def require_auth(request: Request) -> str:
    """Extract user_id from JWT. Raises 401 if not authenticated.

    Use this for endpoints that require login (portfolio CRUD).
    """
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")
    payload = verify_token(auth[7:])
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return payload.get("sub", "")


# ── Request/Response models ──

class RegisterRequest(BaseModel):
    email: str  # Using str instead of EmailStr to avoid extra dependency
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    password: str


class AuthResponse(BaseModel):
    token: str
    user_id: str
    email: str


# ── Endpoints ──

@router.post("/register", response_model=AuthResponse)
def register(req: RegisterRequest):
    """Register a new account with email and password."""
    email = req.email.strip().lower()
    password = req.password

    # Validation
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Invalid email address")
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    # Hash password
    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    user_id = uuid.uuid4().hex[:16]

    conn = _get_db()
    try:
        conn.execute(
            "INSERT INTO users (id, email, password_hash) VALUES (?, ?, ?)",
            (user_id, email, pw_hash)
        )
        conn.commit()
    except Exception as e:
        conn.close()
        if "UNIQUE constraint" in str(e):
            raise HTTPException(status_code=409, detail="Email already registered")
        raise HTTPException(status_code=500, detail="Registration failed")

    conn.close()
    token = create_token(user_id, email)
    return AuthResponse(token=token, user_id=user_id, email=email)


@router.post("/login", response_model=AuthResponse)
def login(req: LoginRequest):
    """Login with email and password."""
    email = req.email.strip().lower()

    conn = _get_db()
    row = conn.execute("SELECT id, email, password_hash FROM users WHERE email=?",
                       (email,)).fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not bcrypt.checkpw(req.password.encode(), row["password_hash"].encode()):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_token(row["id"], row["email"])
    return AuthResponse(token=token, user_id=row["id"], email=row["email"])


@router.get("/me")
def get_me(user_id: str = Depends(require_auth)):
    """Get current user info."""
    conn = _get_db()
    row = conn.execute("SELECT id, email, created_at FROM users WHERE id=?",
                       (user_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    return {"user_id": row["id"], "email": row["email"], "created_at": row["created_at"]}


@router.post("/forgot-password")
def forgot_password(req: ForgotPasswordRequest):
    """Send password reset email (requires RESEND_API_KEY)."""
    email = req.email.strip().lower()

    conn = _get_db()
    row = conn.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()

    if not row:
        # Don't reveal whether email exists
        conn.close()
        return {"message": "If the email exists, a reset link has been sent"}

    if not RESEND_API_KEY:
        conn.close()
        raise HTTPException(status_code=503, detail="Email service not configured")

    # Generate reset token
    token = uuid.uuid4().hex
    expires = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    conn.execute(
        "INSERT INTO password_reset_tokens (user_id, token, expires_at) VALUES (?, ?, ?)",
        (row["id"], token, expires)
    )
    conn.commit()
    conn.close()

    # Send email via Resend
    try:
        import requests
        reset_url = f"https://valuescope.app/auth?reset={token}"
        resp = requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
            json={
                "from": "ValueScope <noreply@valuescope.app>",
                "to": [email],
                "subject": "Reset your password — ValueScope",
                "html": f"""
                    <h2>Password Reset</h2>
                    <p>Click the link below to reset your password. This link expires in 1 hour.</p>
                    <p><a href="{reset_url}">Reset Password</a></p>
                    <p>If you didn't request this, you can safely ignore this email.</p>
                """,
            },
            timeout=10,
        )
        if resp.status_code not in (200, 201):
            logger.error(f"Resend API error: {resp.status_code} {resp.text}")
    except Exception as e:
        logger.error(f"Failed to send reset email: {e}")

    return {"message": "If the email exists, a reset link has been sent"}


@router.post("/reset-password")
def reset_password(req: ResetPasswordRequest):
    """Reset password using token from email."""
    if len(req.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    conn = _get_db()
    row = conn.execute(
        "SELECT user_id, expires_at, used FROM password_reset_tokens WHERE token=?",
        (req.token,)
    ).fetchone()

    if not row:
        conn.close()
        raise HTTPException(status_code=400, detail="Invalid reset token")

    if row["used"]:
        conn.close()
        raise HTTPException(status_code=400, detail="Token already used")

    expires = datetime.fromisoformat(row["expires_at"])
    if datetime.now(timezone.utc) > expires:
        conn.close()
        raise HTTPException(status_code=400, detail="Token expired")

    # Update password
    pw_hash = bcrypt.hashpw(req.password.encode(), bcrypt.gensalt()).decode()
    conn.execute("UPDATE users SET password_hash=? WHERE id=?", (pw_hash, row["user_id"]))
    conn.execute("UPDATE password_reset_tokens SET used=1 WHERE token=?", (req.token,))
    conn.commit()
    conn.close()

    return {"message": "Password reset successfully"}
