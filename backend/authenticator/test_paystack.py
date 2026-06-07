"""
Test Paystack configuration and connectivity
"""
import logging
import os
from django.conf import settings

logger = logging.getLogger(__name__)


def test_paystack_config():
    """Test Paystack configuration and API connectivity"""
    logger.info("=" * 60)
    logger.info("TESTING PAYSTACK CONFIGURATION")
    logger.info("=" * 60)
    
    # Check environment variables
    paystack_secret = os.environ.get('PAYSTACK_SECRET_KEY')
    paystack_public = os.environ.get('PAYSTACK_PUBLIC_KEY')
    paystack_webhook = os.environ.get('PAYSTACK_WEBHOOK_URL')
    
    if paystack_secret:
        logger.info(f"✓ PAYSTACK_SECRET_KEY found: {paystack_secret[:20]}...{paystack_secret[-10:]}")
    else:
        logger.error("❌ PAYSTACK_SECRET_KEY not found in environment!")
        
    if paystack_public:
        logger.info(f"✓ PAYSTACK_PUBLIC_KEY found: {paystack_public[:20]}...{paystack_public[-10:]}")
    else:
        logger.error("❌ PAYSTACK_PUBLIC_KEY not found in environment!")
        
    if paystack_webhook:
        logger.info(f"✓ PAYSTACK_WEBHOOK_URL: {paystack_webhook}")
    else:
        logger.error("❌ PAYSTACK_WEBHOOK_URL not found in environment!")
    
    # Test API connectivity
    if paystack_secret:
        try:
            import requests
            
            headers = {
                "Authorization": f"Bearer {paystack_secret}",
                "Content-Type": "application/json"
            }
            
            logger.info("\nAttempting to verify Paystack API key...")
            response = requests.get(
                "https://api.paystack.co/bank",
                headers=headers,
                timeout=5
            )
            
            if response.status_code == 200:
                logger.info(f"✓ Paystack API is ACTIVE and responding!")
                logger.info(f"  Status Code: {response.status_code}")
                data = response.json()
                if 'data' in data:
                    logger.info(f"  Banks available: {len(data.get('data', []))} banks")
            else:
                logger.error(f"❌ Paystack API returned status {response.status_code}")
                logger.error(f"  Response: {response.text[:200]}")
                
        except requests.exceptions.Timeout:
            logger.error("❌ Paystack API request timed out")
        except requests.exceptions.ConnectionError as e:
            logger.error(f"❌ Failed to connect to Paystack API: {e}")
        except Exception as e:
            logger.error(f"❌ Error testing Paystack API: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    logger.info("=" * 60)


if __name__ == "__main__":
    import django
    django.setup()
    test_paystack_config()
