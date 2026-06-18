"""Auth 路由 — 注册、登录、邮箱验证、JWT 中间件"""

import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

import bcrypt
import jwt
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from server.db import (create_user, create_verification_token, get_pending_token_seconds,
                       get_user_by_id, get_user_by_username, init_auth_db, verify_token)

logger = logging.getLogger("aisu.auth")


def _load_or_create_jwt_secret() -> str:
    env_secret = os.getenv("JWT_SECRET")
    if env_secret:
        return env_secret
    secret_path = Path(os.getenv("DATA_DIR", ".")) / ".jwt_secret"
    if secret_path.exists():
        return secret_path.read_text(encoding="utf-8").strip()
    new_secret = secrets.token_hex(32)
    secret_path.write_text(new_secret, encoding="utf-8")
    logger.info("Generated new JWT secret at %s", secret_path)
    return new_secret


JWT_SECRET = _load_or_create_jwt_secret()
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 72

router = APIRouter(prefix="/api/auth", tags=["auth"])
security = HTTPBearer(auto_error=False)


def create_jwt(user_id: str, username: str, role: str) -> str:
    payload = {
        "sub": user_id,
        "username": username,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRE_HOURS),
        "iat": datetime.now(timezone.utc),
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


async def require_admin(user: dict | None = Depends(get_current_user)) -> dict:
    if not user:
        raise HTTPException(status_code=401, detail="请先登录")
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
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
    from server.tasks import send_verification_email_async
    email_sent = send_verification_email_async(email, user["username"], token)
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
    from fastapi.responses import HTMLResponse
    from config import SITE_URL
    home = SITE_URL.rstrip("/")
    try:
        user = verify_token(token, "verify_email")
        if not user:
            return HTMLResponse(_verify_page("无效的验证令牌", "该链接无效，请检查是否完整复制。", home, False))
        return HTMLResponse(_verify_page("邮箱验证成功", f"你好 {user['username']}，你的邮箱已验证通过。", home, True))
    except ValueError as e:
        return HTMLResponse(_verify_page("验证链接已过期", str(e) + "，请重新注册以获取新的验证邮件。", home, False))


def _verify_page(title: str, message: str, home_url: str, success: bool) -> str:
    color = "#10b981" if success else "#ef4444"
    icon = "✓" if success else "✗"
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box }}
  body {{ display:flex; align-items:center; justify-content:center; min-height:100vh;
         background:#0d1117; color:#c9d1d9; font-family:-apple-system,BlinkMacSystemFont,sans-serif }}
  .card {{ background:#161b22; border:1px solid #30363d; border-radius:12px; padding:40px 48px;
           text-align:center; max-width:420px; width:100% }}
  .icon {{ font-size:48px; color:{color}; margin-bottom:16px }}
  h1 {{ font-size:22px; margin-bottom:8px; color:{color} }}
  p {{ color:#8b949e; font-size:14px; margin-bottom:28px; line-height:1.6 }}
  a {{ display:inline-block; padding:10px 28px; background:{color}; color:#fff;
       text-decoration:none; border-radius:6px; font-size:14px; transition:opacity .15s }}
  a:hover {{ opacity:.85 }}
</style>
</head>
<body>
<div class="card">
  <div class="icon">{icon}</div>
  <h1>{title}</h1>
  <p>{message}</p>
  <a href="{home_url}">返回网站首页</a>
</div>
</body>
</html>"""


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
