"""Auth 路由 — 注册、登录、邮箱验证、JWT 中间件"""

import logging
import secrets
from datetime import datetime, timedelta

import bcrypt
import jwt
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from server.db import (create_user, create_verification_token, get_pending_token_seconds,
                       get_user_by_id, get_user_by_username, init_auth_db, verify_token)

logger = logging.getLogger("aisu.auth")

JWT_SECRET = secrets.token_hex(32)
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 72

router = APIRouter(prefix="/api/auth", tags=["auth"])
security = HTTPBearer(auto_error=False)


def create_jwt(user_id: str, username: str, role: str) -> str:
    payload = {
        "sub": user_id,
        "username": username,
        "role": role,
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRE_HOURS),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_jwt(token: str) -> dict | None:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


# ── Middleware ──

async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict | None:
    if not credentials:
        return None
    payload = decode_jwt(credentials.credentials)
    if not payload:
        return None
    user = get_user_by_id(payload["sub"])
    return user if user else None


async def require_user(user: dict | None = Depends(get_current_user)) -> dict:
    if not user:
        raise HTTPException(status_code=401, detail="请先登录")
    return user


# ── Routes ──

@router.post("/register")
async def register(request: Request):
    body = await request.json()
    username = (body.get("username") or "").strip()
    password = (body.get("password") or "").strip()
    email = (body.get("email") or "").strip()

    if len(username) < 3 or len(username) > 32:
        raise HTTPException(status_code=400, detail="用户名需要 3-32 个字符")
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="密码至少需要 6 个字符")
    if email and "@" not in email:
        raise HTTPException(status_code=400, detail="邮箱格式不正确")

    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    try:
        user = create_user(username, password_hash, email)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    # 无邮箱 → 直接登录
    if not email:
        jwt_token = create_jwt(user["id"], user["username"], user["role"])
        return {"ok": True, "need_verify": False,
                "token": jwt_token, "user": user, "message": "注册成功"}

    # 有邮箱 → 发送验证邮件，不签发 JWT
    elapsed = get_pending_token_seconds(user["id"], "verify_email")
    if elapsed is not None and elapsed < 60:
        raise HTTPException(status_code=429, detail=f"验证邮件已发送，请 {60 - elapsed} 秒后再试")

    token = secrets.token_urlsafe(32)
    create_verification_token(user["id"], token, "verify_email")
    from server.email import send_verification_email
    email_sent = send_verification_email(email, user["username"], token)
    if not email_sent:
        logger.warning("Failed to send verification email to %s", email)
        return {"ok": True, "need_verify": True,
                "message": "注册成功，但验证邮件发送失败。请检查 SMTP 配置。"}
    return {"ok": True, "need_verify": True,
            "message": "注册成功！验证邮件已发送至 " + email + "，请前往邮箱完成验证后再登录。"}


@router.post("/login")
async def login(request: Request):
    body = await request.json()
    username = (body.get("username") or "").strip()
    password = (body.get("password") or "").strip()

    if not username or not password:
        raise HTTPException(status_code=400, detail="请输入用户名和密码")

    user = get_user_by_username(username)
    if not user:
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    if not bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    if user.get("email") and not user.get("email_verified"):
        raise HTTPException(status_code=403, detail="请先验证邮箱后再登录。检查收件箱或垃圾邮件。")

    jwt_token = create_jwt(user["id"], user["username"], user["role"])
    return {
        "token": jwt_token,
        "user": {
            "id": user["id"],
            "username": user["username"],
            "email": user.get("email"),
            "email_verified": bool(user.get("email_verified")),
            "role": user.get("role"),
        },
    }


@router.get("/verify/{token}")
async def verify_email_endpoint(token: str):
    try:
        user = verify_token(token, "verify_email")
        if not user:
            raise HTTPException(status_code=404, detail="无效的验证令牌")
        return {"ok": True, "message": "邮箱验证成功"}
    except ValueError as e:
        raise HTTPException(status_code=410, detail=str(e))


@router.get("/me")
async def get_me(user: dict | None = Depends(get_current_user)):
    if not user:
        return {
            "authenticated": False,
            "user": None,
        }
    return {
        "authenticated": True,
        "user": {
            "id": user["id"],
            "username": user["username"],
            "email": user.get("email"),
            "email_verified": bool(user.get("email_verified")),
            "role": user.get("role"),
        },
    }


def install_auth(app):
    init_auth_db()
    from server.db import ensure_default_admin
    ensure_default_admin()
    app.include_router(router)
