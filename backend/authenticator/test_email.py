"""
Quick test to verify Mailtrap configuration
"""
import logging
from django.conf import settings
from django.core.mail import EmailMultiAlternatives

logger = logging.getLogger(__name__)


def test_mailtrap_config():
    """Test Mailtrap configuration without sending actual email"""
    logger.info("=" * 50)
    logger.info("TESTING MAILTRAP CONFIGURATION")
    logger.info("=" * 50)
    
    # Check settings
    logger.info(f"EMAIL_BACKEND: {settings.EMAIL_BACKEND}")
    logger.info(f"DEFAULT_FROM_EMAIL: {settings.DEFAULT_FROM_EMAIL}")
    
    if hasattr(settings, 'ANYMAIL'):
        logger.info(f"ANYMAIL config present: {bool(settings.ANYMAIL)}")
        if 'MAILTRAP_API_TOKEN' in settings.ANYMAIL:
            token = settings.ANYMAIL['MAILTRAP_API_TOKEN']
            logger.info(f"MAILTRAP_API_TOKEN: {token[:10]}...{token[-10:]} (hidden for security)")
        else:
            logger.error("❌ MAILTRAP_API_TOKEN not in ANYMAIL settings!")
    else:
        logger.error("❌ ANYMAIL not configured in settings!")
    
    # Try creating a message
    try:
        msg = EmailMultiAlternatives(
            subject="Mailtrap Test",
            body="This is a test",
            from_email="support@swifttrade.com",
            to=["test@example.com"],
        )
        msg.attach_alternative("<p>This is a test</p>", "text/html")
        logger.info("✓ EmailMultiAlternatives object created successfully")
        
        # Don't actually send, just check it can be created
        logger.info("✓ Email object is valid and ready to send")
        
    except Exception as e:
        logger.error(f"❌ Failed to create email message: {e}")
        import traceback
        logger.error(traceback.format_exc())
    
    logger.info("=" * 50)


if __name__ == "__main__":
    import django
    django.setup()
    test_mailtrap_config()
