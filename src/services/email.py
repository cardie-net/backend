import asyncio
import logging
import smtplib
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

from ..config import settings

logger = logging.getLogger(__name__)

_background_tasks: set[asyncio.Task] = set()


def send_email_sync(to_email: str, subject: str, content: str) -> None:
    """Send an email synchronously with dynamic port handling."""
    if not settings.SMTP_SERVER:
        logger.info("SMTP server not configured, skipping email")
        return

    msg = EmailMessage()
    msg.set_content(content)
    msg["Subject"] = subject
    msg["From"] = settings.EMAILS_FROM_EMAIL
    msg["To"] = to_email
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=settings.EMAIL_DOMAIN)

    try:
        smtp_cls = smtplib.SMTP_SSL if settings.SMTP_PORT == 465 else smtplib.SMTP
        with smtp_cls(
            settings.SMTP_SERVER, settings.SMTP_PORT, timeout=settings.SMTP_TIMEOUT
        ) as server:
            if settings.SMTP_PORT == 587:
                server.starttls()
            if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
                server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            server.send_message(msg)
            logger.info(f"Email sent to {to_email}")
    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {e}")


async def send_email(to_email: str, subject: str, content: str) -> None:
    """Send an email asynchronously in the background."""
    task = asyncio.create_task(
        asyncio.to_thread(send_email_sync, to_email, subject, content)
    )
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
