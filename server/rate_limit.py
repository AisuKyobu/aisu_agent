import time
from collections import defaultdict

from config import DEMO_WINDOW_SECONDS, DEMO_MAX_MSG_PER_IP

_ip_store: dict[str, dict] = {}
_expire_time = 0


def _cleanup():
    global _expire_time
    now = time.time()
    if now < _expire_time:
        return
    cutoff = now - max(DEMO_WINDOW_SECONDS, 3600)
    stale = [k for k, v in _ip_store.items() if v.get("reset_at", 0) < cutoff]
    for k in stale:
        del _ip_store[k]
    _expire_time = now + 300


def check_ip_limit(ip: str) -> tuple[bool, int, int]:
    _cleanup()
    now = time.time()
    entry = _ip_store.get(ip)
    if entry is None or now >= entry["reset_at"]:
        _ip_store[ip] = {"count": 0, "reset_at": now + DEMO_WINDOW_SECONDS}
        entry = _ip_store[ip]

    remaining = max(0, DEMO_MAX_MSG_PER_IP - entry["count"])
    reset_at = int(entry["reset_at"])

    if entry["count"] >= DEMO_MAX_MSG_PER_IP:
        return False, remaining, reset_at

    return True, remaining, reset_at


def increment_ip_count(ip: str):
    entry = _ip_store.get(ip)
    if entry and time.time() < entry["reset_at"]:
        entry["count"] += 1
    else:
        _ip_store[ip] = {"count": 1, "reset_at": time.time() + DEMO_WINDOW_SECONDS}


def get_ip_remaining(ip: str) -> int:
    _cleanup()
    now = time.time()
    entry = _ip_store.get(ip)
    if entry is None or now >= entry["reset_at"]:
        return DEMO_MAX_MSG_PER_IP
    return max(0, DEMO_MAX_MSG_PER_IP - entry["count"])


def extract_client_ip(request=None, websocket=None) -> str:
    """从 request 或 websocket 提取真实客户端 IP，兼容反向代理。"""
    import re
    if websocket and hasattr(websocket, "headers"):
        headers = dict(websocket.headers)
        for header in ("x-forwarded-for", "x-real-ip"):
            val = headers.get(header, "")
            if val:
                return val.split(",")[0].strip()
        client = websocket.client
        if client:
            host, _ = client
            if isinstance(host, str):
                return re.sub(r"[^0-9a-fA-F.:]", "", host)
            return str(host)
    if request:
        for header in ("x-forwarded-for", "x-real-ip"):
            val = request.headers.get(header, "")
            if val:
                return val.split(",")[0].strip()
        client_host = request.client.host if request.client else None
        if client_host:
            return re.sub(r"[^0-9a-fA-F.:]", "", client_host)
    return "127.0.0.1"
