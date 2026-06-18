"""Celery Worker 任务定义 — 由 celery worker 进程加载执行。

启动方式:
  celery -A server.celery_tasks worker -Q email,celery -l info
  celery -A server.celery_tasks beat -l info   （定时任务调度器）
"""

import logging
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from config import SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SITE_URL

logger = logging.getLogger("aisu.celery_tasks")


def get_celery():
    from server.celery_app import get_celery as _get
    return _get()

celery_app = get_celery()


@celery_app.task(bind=True, max_retries=3, default_retry_delay=30, name="emails.send_verification")
def send_verification_email(self, to_email: str, username: str, token: str) -> bool:
    """异步发送验证邮件，失败自动重试 3 次。"""
    if not SMTP_HOST or not SMTP_USER or not SMTP_PASSWORD:
        logger.warning("SMTP not configured, skip email to %s", to_email)
        return False

    verify_url = f"{SITE_URL.rstrip('/')}/api/auth/verify/{token}"

    html = f"""
    <div style="max-width:480px;margin:0 auto;font-family:sans-serif">
      <h2 style="color:#FB7299">Aisu</h2>
      <p>你好 <b>{username}</b>，感谢注册！</p>
      <p>请点击下方链接验证邮箱（1 小时内有效）：</p>
      <a href="{verify_url}" style="display:inline-block;padding:10px 24px;
         background:#FB7299;color:#fff;text-decoration:none;border-radius:6px">
        验证邮箱
      </a>
      <p style="margin-top:16px;font-size:12px;color:#888">
        如果按钮无法点击，请复制以下链接到浏览器：<br>{verify_url}
      </p>
    </div>
    """

    msg = MIMEMultipart("alternative")
    msg["From"] = SMTP_USER
    msg["To"] = to_email
    msg["Subject"] = "Aisu - 邮箱验证"
    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=15)
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(SMTP_USER, to_email, msg.as_string())
        server.quit()
        logger.info("Verification email sent to %s (Celery)", to_email)
        return True
    except Exception as e:
        logger.error("Email send failed (attempt %d): %s", self.request.retries + 1, e)
        raise self.retry(exc=e)


@celery_app.task(bind=True, name="maintenance.cleanup_stale")
def cleanup_stale_sessions(self):
    """定时清理过期会话状态（每 10 分钟由 Celery Beat 触发）。"""
    try:
        from server.state import _cleanup_stale_status
        _cleanup_stale_status()
        logger.debug("Celery Beat: stale status cleaned")
    except Exception as e:
        logger.warning("Cleanup failed: %s", e)


# Celery Beat 定时调度配置
celery_app.conf.beat_schedule = {
    "cleanup-every-10m": {
        "task": "maintenance.cleanup_stale",
        "schedule": 600.0,  # 10 分钟
    },
}
