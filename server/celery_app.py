"""Celery 实例 — 异步任务队列，Redis 做 broker 和 result backend。

未配置 REDIS_URL 时 Celery 不可用，各调用方自动回退同步执行。
"""

import logging

from celery import Celery

from config import REDIS_URL

logger = logging.getLogger("aisu.celery")

_app: Celery | None = None


def get_celery() -> Celery | None:
    """获取 Celery 实例。不可用时返回 None。"""
    global _app
    if _app is not None:
        return _app
    if not REDIS_URL:
        logger.debug("Celery disabled: no REDIS_URL configured")
        return None
    try:
        _app = Celery("aisu",
                      broker=REDIS_URL,
                      backend=REDIS_URL,
                      task_serializer="json",
                      result_serializer="json",
                      accept_content=["json"],
                      task_track_started=True,
                      task_acks_late=True,
                      worker_prefetch_multiplier=1,
                      broker_connection_retry_on_startup=True,
                      )
        _app.conf.update(
            result_expires=3600,
            task_default_retry_delay=30,
            task_max_retries=3,
        )
        logger.info("Celery app configured: %s", REDIS_URL)
        return _app
    except Exception as e:
        logger.warning("Celery unavailable (%s), tasks will run synchronously", e)
        _app = None
        return None
