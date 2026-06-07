"""
Test Quidax configuration and connectivity
"""
import logging
import os
from django.conf import settings

logger = logging.getLogger(__name__)


def test_quidax_config():
    """Test Quidax configuration and API connectivity"""
    logger.info("=" * 60)
    logger.info("TESTING QUIDAX CONFIGURATION")
    logger.info("=" * 60)
    
    # Check environment variables
    quidax_api_key = os.environ.get('QUIDAX_API_KEY')
    quidax_secret_key = os.environ.get('QUIDAX_SECRET_KEY')
    quidax_webhook_secret = os.environ.get('QUIDAX_WEBHOOK_SECRET')
    quidax_base_url = os.environ.get('QUIDAX_API_BASE_URL')
    quidax_callback_url = os.environ.get('QUIDAX_CALLBACK_URL')
    
    if quidax_api_key:
        logger.info(f"✓ QUIDAX_API_KEY found: {quidax_api_key[:20]}...{quidax_api_key[-10:]}")
    else:
        logger.error("❌ QUIDAX_API_KEY not found in environment!")
        
    if quidax_secret_key:
        logger.info(f"✓ QUIDAX_SECRET_KEY found: {quidax_secret_key[:20]}...{quidax_secret_key[-10:]}")
    else:
        logger.error("❌ QUIDAX_SECRET_KEY not found in environment!")
        
    if quidax_webhook_secret:
        logger.info(f"✓ QUIDAX_WEBHOOK_SECRET found: {quidax_webhook_secret[:10]}...")
    else:
        logger.error("❌ QUIDAX_WEBHOOK_SECRET not found in environment!")
        
    if quidax_base_url:
        logger.info(f"✓ QUIDAX_API_BASE_URL: {quidax_base_url}")
    else:
        logger.error("❌ QUIDAX_API_BASE_URL not found in environment!")
        
    if quidax_callback_url:
        logger.info(f"✓ QUIDAX_CALLBACK_URL: {quidax_callback_url.strip()}")
    else:
        logger.error("❌ QUIDAX_CALLBACK_URL not found in environment!")
    
    # Test API connectivity with multiple endpoints
    if quidax_api_key and quidax_base_url:
        try:
            import requests
            import base64
            
            logger.info("\nAttempting to verify Quidax API key...")
            
            # Quidax uses Basic Auth with API key
            auth_string = base64.b64encode(f"{quidax_api_key}:".encode()).decode()
            headers = {
                "Authorization": f"Basic {auth_string}",
                "Content-Type": "application/json"
            }
            
            # Try multiple endpoints
            endpoints = [
                "/coins/",
                "/assets/",
                "/profile/",
                "/wallets/",
            ]
            
            api_working = False
            for endpoint in endpoints:
                logger.info(f"\nTrying endpoint: {endpoint}")
                response = requests.get(
                    f"{quidax_base_url}{endpoint}",
                    headers=headers,
                    timeout=5
                )
                
                if response.status_code in [200, 201]:
                    logger.info(f"✓ Quidax API is ACTIVE and responding on {endpoint}!")
                    logger.info(f"  Status Code: {response.status_code}")
                    api_working = True
                    break
                else:
                    logger.info(f"  Status {response.status_code}: {response.text[:100]}")
            
            if not api_working:
                logger.error(f"⚠ Quidax API is reachable but no successful endpoints found")
                logger.error(f"  This might be due to API permissions or endpoint changes")
                logger.error(f"  Verify credentials are correct and have proper permissions")
                
        except requests.exceptions.Timeout:
            logger.error("❌ Quidax API request timed out")
        except requests.exceptions.ConnectionError as e:
            logger.error(f"❌ Failed to connect to Quidax API: {e}")
        except Exception as e:
            logger.error(f"❌ Error testing Quidax API: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    logger.info("=" * 60)


if __name__ == "__main__":
    import django
    django.setup()
    test_quidax_config()
