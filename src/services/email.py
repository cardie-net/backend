import asyncio
import smtplib
from email.message import EmailMessage

from ..config import settings


def send_email_sync(to_email: str, subject: str, content: str):
    if not settings.SMTP_SERVER:
        print("SMTP server not configured, skipping email")
        return

    msg = EmailMessage()
    msg.set_content(content)
    msg["Subject"] = subject
    msg["From"] = settings.EMAILS_FROM_EMAIL
    msg["To"] = to_email

    try:
        with smtplib.SMTP(settings.SMTP_SERVER, settings.SMTP_PORT) as server:
            if settings.SMTP_PORT == 587:
                server.starttls()
            if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
                server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            server.send_message(msg)
            print(f"Email sent to {to_email}")
    except Exception as e:
        print(f"Failed to send email to {to_email}: {e}")


async def send_email(to_email: str, subject: str, content: str):
    """Sends an email asynchronously."""
    await asyncio.to_thread(send_email_sync, to_email, subject, content)
