"""Redis 客户端 — 统一的连接管理与可选回退。

当 config.REDIS_URL 为空时，所有 get_redis() 调用返回 None，
各模块自动使用现有的内存实现。
"""

import logging

from redis import Redis, ConnectionPool

from config import REDIS_URL

logger = logging.getLogger("aisu.redis")

_pool: ConnectionPool | None = None
_client: Redis | None = None
_checked: bool = False


def get_redis() -> Redis | None:
    """获取 Redis 客户端实例。

    首次调用时根据 REDIS_URL 尝试连接。如果 REDIS_URL 为空或连接失败，
    返回 None，调用方应回退到内存实现。
    """
    global _client, _pool, _checked

    if not REDIS_URL:
        _checked = True
        return None

    if _client is not None:
        return _client

    if _checked:
        return None

    try:
        _pool = ConnectionPool.from_url(
            REDIS_URL,
            max_connections=20,
            socket_timeout=3,
            socket_connect_timeout=3,
            retry_on_timeout=False,
        )
        _client = Redis(connection_pool=_pool)
        _client.ping()
        logger.info("Redis connected: %s", REDIS_URL)
        _checked = True
        return _client
    except Exception as e:
        logger.warning("Redis unavailable (%s), falling back to in-memory stores", e)
        _client = None
        _checked = True
        return None
