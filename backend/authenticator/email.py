import logging
from datetime import datetime

from django.conf import settings
from django.template.loader import render_to_string
from django.core.mail import EmailMultiAlternatives

logger = logging.getLogger(__name__)

def send_email(
    to_email: str,
    to_name: str,
    subject: str,
    template_name: str,
    context: dict | None = None,
) -> bool:
    """
    Render an HTML template and send it via Django's email backend (Anymail).

    Args:
        to_email: Recipient email address.
        to_name: Recipient display name.
        subject: Email subject line.
        template_name: Template path relative to templates/ (e.g. 'emails/welcome.html').
        context: Dict of variables passed to the template.

    Returns:
        True if the API accepted the message, False otherwise.
    """
    ctx = context or {}
    ctx.setdefault("year", datetime.now().year)
    html_body = render_to_string(template_name, ctx)

    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@swifttrade.com")
    to_address = f"{to_name} <{to_email}>" if to_name else to_email

    msg = EmailMultiAlternatives(
        subject=subject,
        body="Please view this email in an HTML-compatible email client.",
        from_email=from_email,
        to=[to_address],
    )
    msg.attach_alternative(html_body, "text/html")
    
    try:
        msg.send()
        logger.info("Email sent to %s [%s]", to_email, subject)
        return True
    except Exception as exc:
        logger.error("Failed to send email to %s: %s", to_email, exc)
        return False


# -------------------------------------------------------------------
# Convenience helpers used by auth services
# -------------------------------------------------------------------

def send_verification_email(user, token: str) -> bool:
    """Send the 6-digit email verification code."""
    return send_email(
        to_email=user.email,
        to_name=user.full_name,
        subject="SwiftTrade – Verify Your Email",
        template_name="emails/email_verification.html",
        context={
            "full_name": user.full_name,
            "token": token,
        },
    )


def send_password_reset_email(user, token: str) -> bool:
    """Send the 6-digit password reset code."""
    return send_email(
        to_email=user.email,
        to_name=user.full_name,
        subject="SwiftTrade – Password Reset Code",
        template_name="emails/password_reset.html",
        context={
            "full_name": user.full_name,
            "token": token,
        },
    )


def send_password_changed_email(user) -> bool:
    """Send a confirmation that the password was changed."""
    return send_email(
        to_email=user.email,
        to_name=user.full_name,
        subject="SwiftTrade – Password Changed",
        template_name="emails/password_changed.html",
        context={
            "full_name": user.full_name,
            "email": user.email,
            "timestamp": datetime.now().strftime("%B %d, %Y at %I:%M %p UTC"),
        },
    )
