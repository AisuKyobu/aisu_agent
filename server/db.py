"""Auth 数据库 — users、verification_tokens 表管理"""

import os
import sqlite3
import uuid
from datetime import datetime

from config import DATA_DIR

os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "auth.db")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_auth_db() -> None:
    conn = _connect()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            email TEXT UNIQUE,
            email_verified INTEGER DEFAULT 0,
            role TEXT DEFAULT 'user',
            created_at REAL
        );

        CREATE TABLE IF NOT EXISTS verification_tokens (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            token TEXT UNIQUE NOT NULL,
            action TEXT DEFAULT 'verify_email',
            expires_at REAL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
        CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
        CREATE INDEX IF NOT EXISTS idx_vt_token ON verification_tokens(token);
    """)
    conn.commit()
    conn.close()


def ensure_default_admin() -> None:
    import bcrypt
    conn = _connect()
    row = conn.execute("SELECT id FROM users WHERE username=?", ("admin",)).fetchone()
    if not row:
        uid = uuid.uuid4().hex
        now = datetime.utcnow().timestamp()
        pw = bcrypt.hashpw("admin123".encode(), bcrypt.gensalt()).decode()
        conn.execute(
            "INSERT INTO users (id, username, password_hash, email, email_verified, role, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (uid, "admin", pw, "", 1, "admin", now))
        conn.commit()
    conn.close()


# ── User CRUD ──

def create_user(username: str, password_hash: str, email: str = "") -> dict:
    conn = _connect()
    uid = uuid.uuid4().hex
    now = datetime.utcnow().timestamp()
    try:
        conn.execute(
            "INSERT INTO users (id, username, password_hash, email, created_at) VALUES (?,?,?,?,?)",
            (uid, username, password_hash, email, now))
        conn.commit()
        conn.close()
        return {"id": uid, "username": username, "email": email, "role": "user", "email_verified": 0}
    except sqlite3.IntegrityError:
        conn.close()

    # 用户名或邮箱已存在 → 检查是否未验证，可以覆盖
    existing = get_user_by_username(username)
    if not existing and email:
        ec = _connect()
        row = ec.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        ec.close()
        existing = dict(row) if row else None
    if existing and not existing.get("email_verified"):
        dc = _connect()
        dc.execute("DELETE FROM verification_tokens WHERE user_id=?", (existing["id"],))
        dc.execute("DELETE FROM users WHERE id=?", (existing["id"],))
        dc.commit()
        dc.close()
        return create_user(username, password_hash, email)
    raise ValueError("用户名或邮箱已存在")


def get_user_by_username(username: str) -> dict | None:
    conn = _connect()
    row = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_id(user_id: str) -> dict | None:
    conn = _connect()
    row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


# ── Verification tokens ──

def create_verification_token(user_id: str, token: str, action: str = "verify_email") -> None:
    conn = _connect()
    vid = uuid.uuid4().hex
    expires = datetime.utcnow().timestamp() + 3600  # 1 hour
    conn.execute(
        "INSERT INTO verification_tokens (id, user_id, token, action, expires_at) VALUES (?,?,?,?,?)",
        (vid, user_id, token, action, expires))
    conn.commit()
    conn.close()


def verify_token(token: str, action: str = "verify_email") -> dict | None:
    conn = _connect()
    row = conn.execute(
        "SELECT user_id, expires_at FROM verification_tokens WHERE token=? AND action=?",
        (token, action)).fetchone()
    if not row:
        conn.close()
        return None
    if row["expires_at"] < datetime.utcnow().timestamp():
        conn.execute("DELETE FROM verification_tokens WHERE token=?", (token,))
        conn.commit()
        conn.close()
        raise ValueError("验证令牌已过期")
    user = get_user_by_id(row["user_id"])
    if action == "verify_email":
        conn.execute("UPDATE users SET email_verified=1 WHERE id=?", (row["user_id"],))
    conn.execute("DELETE FROM verification_tokens WHERE token=?", (token,))
    conn.commit()
    conn.close()
    return user


def get_pending_token_seconds(user_id: str, action: str = "verify_email") -> int | None:
    """返回该用户最近一次验证 token 已过秒数；无未过期 token 返回 None"""
    conn = _connect()
    row = conn.execute(
        "SELECT expires_at FROM verification_tokens WHERE user_id=? AND action=? ORDER BY expires_at DESC LIMIT 1",
        (user_id, action)).fetchone()
    conn.close()
    if not row:
        return None
    remaining = row["expires_at"] - datetime.utcnow().timestamp()
    if remaining <= 0:
        return None
    return max(0, 3600 - int(remaining))
