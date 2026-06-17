"""IP 限流 — Redis 滑动窗口（优先）+ 内存回退。

Redis 可用时使用 INCR + EXPIRE 实现分布式限流；
Redis 不可用时回退到原有的内存字典实现。
"""
import time

from config import DEMO_WINDOW_SECONDS, DEMO_MAX_MSG_PER_IP


# ═══════════════════════════════════════════════════
#  Redis 实现
# ═══════════════════════════════════════════════════

_REDIS_PREFIX = "aisu:ratelimit:"


def _redis_client():
    from server.redis_client import get_redis
    return get_redis()


def _redis_check(ip: str) -> tuple[bool, int, int] | None:
    """Redis 限流检查。返回 (allowed, remaining, reset_at) 或 None 表示不可用。"""
    r = _redis_client()
    if r is None:
        return None
    try:
        key = f"{_REDIS_PREFIX}{ip}"
        count = r.get(key)
        count_int = int(count) if count else 0

        if count_int >= DEMO_MAX_MSG_PER_IP:
            ttl = r.ttl(key)
            reset_at = int(time.time() + max(ttl, 0))
            return False, 0, reset_at

        remaining = DEMO_MAX_MSG_PER_IP - count_int
        ttl = r.ttl(key)
        reset_at = int(time.time() + max(ttl, DEMO_WINDOW_SECONDS))
        return True, remaining, reset_at
    except Exception:
        return None


def _redis_incr(ip: str):
    """Redis 限流计数 +1。"""
    r = _redis_client()
    if r is None:
        return
    try:
        key = f"{_REDIS_PREFIX}{ip}"
        r.incr(key)
        r.expire(key, DEMO_WINDOW_SECONDS, nx=True)
    except Exception:
        pass


def _redis_remaining(ip: str) -> int | None:
    """Redis 查询 IP 剩余次数。返回 None 表示不可用。"""
    r = _redis_client()
    if r is None:
        return None
    try:
        key = f"{_REDIS_PREFIX}{ip}"
        count = r.get(key)
        count_int = int(count) if count else 0
        if r.ttl(key) < 0:
            return DEMO_MAX_MSG_PER_IP
        return max(0, DEMO_MAX_MSG_PER_IP - count_int)
    except Exception:
        return None


# ═══════════════════════════════════════════════════
#  内存回退
# ═══════════════════════════════════════════════════

_ip_store: dict[str, dict] = {}
_expire_time = 0


def _mem_cleanup():
    global _expire_time
    now = time.time()
    if now < _expire_time:
        return
    cutoff = now - max(DEMO_WINDOW_SECONDS, 3600)
    stale = [k for k, v in _ip_store.items() if v.get("reset_at", 0) < cutoff]
    for k in stale:
        del _ip_store[k]
    _expire_time = now + 300


def _mem_check(ip: str) -> tuple[bool, int, int]:
    _mem_cleanup()
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


def _mem_incr(ip: str):
    entry = _ip_store.get(ip)
    if entry and time.time() < entry["reset_at"]:
        entry["count"] += 1
    else:
        _ip_store[ip] = {"count": 1, "reset_at": time.time() + DEMO_WINDOW_SECONDS}


def _mem_remaining(ip: str) -> int:
    _mem_cleanup()
    now = time.time()
    entry = _ip_store.get(ip)
    if entry is None or now >= entry["reset_at"]:
        return DEMO_MAX_MSG_PER_IP
    return max(0, DEMO_MAX_MSG_PER_IP - entry["count"])


# ═══════════════════════════════════════════════════
#  公共 API
# ═══════════════════════════════════════════════════

def check_ip_limit(ip: str) -> tuple[bool, int, int]:
    result = _redis_check(ip)
    if result is not None:
        return result
    return _mem_check(ip)


def increment_ip_count(ip: str):
    _redis_incr(ip)
    _mem_incr(ip)


def get_ip_remaining(ip: str) -> int:
    rem = _redis_remaining(ip)
    if rem is not None:
        return rem
    return _mem_remaining(ip)


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
