"""任务调度公共 API — 异步优先，Celery 不可用时自动回退同步。

调用方只需 import 本模块的函数，无需关心底层是 Celery 还是同步。
"""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from config import SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SITE_URL

logger = logging.getLogger("aisu.tasks")


def _send_sync(to_email: str, username: str, token: str) -> bool:
    """同步发送验证邮件（Celery 不可用时的回退）。"""
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

    server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=15)
    server.login(SMTP_USER, SMTP_PASSWORD)
    server.sendmail(SMTP_USER, to_email, msg.as_string())
    server.quit()
    logger.info("Verification email sent to %s (sync fallback)", to_email)
    return True


def send_verification_email_async(to_email: str, username: str, token: str):
    """异步发送验证邮件。Celery 可用时走队列，否则同步发送。"""
    try:
        celery = None
        try:
            from server.celery_app import get_celery
            celery = get_celery()
        except Exception:
            pass
        if celery:
            task = celery.send_task(
                "emails.send_verification",
                args=[to_email, username, token],
                queue="email",
            )
            logger.debug("Email task queued: %s", task.id)
            return True
    except Exception as e:
        logger.warning("Celery queue failed (%s), fallback to sync", e)

    try:
        return _send_sync(to_email, username, token)
    except Exception as e:
        logger.error("Sync email failed for %s: %s", to_email, e)
        return False


def get_task_status(task_id: str) -> dict | None:
    """查询 Celery 任务状态。不可用时返回 None。"""
    try:
        from server.celery_app import get_celery
        celery = get_celery()
        if not celery:
            return None
        from celery.result import AsyncResult
        result = AsyncResult(task_id, app=celery)
        return {
            "id": task_id,
            "status": result.status,
            "info": str(result.info) if result.info and result.status == "FAILURE" else None,
        }
    except Exception:
        return None
