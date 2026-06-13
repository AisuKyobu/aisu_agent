"""邮件发送模块 — SMTP 邮箱验证"""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from config import SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SITE_URL

logger = logging.getLogger("aisu.email")


def send_verification_email(to_email: str, username: str, token: str) -> bool:
    if not SMTP_HOST or not SMTP_USER or not SMTP_PASSWORD:
        logger.warning("SMTP not configured, skip sending email to %s", to_email)
        return False

    verify_url = f"{SITE_URL.rstrip('/')}/api/auth/verify/{token}"

    subject = "Aisu - 邮箱验证"
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
    msg["Subject"] = subject
    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15)
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(SMTP_USER, to_email, msg.as_string())
        server.quit()
        logger.info("Verification email sent to %s", to_email)
        return True
    except Exception as e:
        logger.error("Failed to send email to %s: %s", to_email, e)
        return False
