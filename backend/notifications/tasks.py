import logging

from celery import shared_task
from datetime import datetime

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=30, name='notifications.tasks.send_email_task')
def send_email_task(self, to_email: str, to_name: str, subject: str, template_name: str, context: dict):
    """
    Send a templated email in the background.
    Retries up to 3 times with a 30-second delay on failure.
    """
    from authenticator.email import send_email
    try:
        send_email(to_email, to_name, subject, template_name, context)
        logger.info(f"[email_task] Sent '{subject}' to {to_email}")
    except Exception as exc:
        logger.error(f"[email_task] Failed for {to_email}: {exc}")
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=10, name='notifications.tasks.send_telegram_task')
def send_telegram_task(self, message: str):
    """
    Send a Telegram admin notification in the background.
    Retries up to 3 times with a 10-second delay on transient failures.
    """
    from notifications.telegram import TelegramNotifier
    try:
        TelegramNotifier._send(message)
        logger.info("[telegram_task] Message sent.")
    except Exception as exc:
        logger.error(f"[telegram_task] Failed: {exc}")
        raise self.retry(exc=exc)


@shared_task(name='notifications.tasks.create_notification_task')
def create_notification_task(user_id: int, notification_type: str, title: str, body: str):
    """
    Persist an in-app notification for a user in the background.
    """
    from authenticator.models import User
    from notifications.models import Notification
    try:
        user = User.objects.get(id=user_id)
        Notification.objects.create(user=user, type=notification_type, title=title, body=body)
        logger.info(f"[notification_task] Created '{title}' for user {user_id}")
    except Exception as exc:
        logger.error(f"[notification_task] Failed for user {user_id}: {exc}")
