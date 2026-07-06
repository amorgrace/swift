import os
import hmac
import hashlib
import requests
import logging

logger = logging.getLogger(__name__)

ALCHEMY_AUTH_TOKEN = os.environ.get("ALCHEMY_AUTH_TOKEN")
ALCHEMY_WEBHOOK_SECRET = os.environ.get("ALCHEMY_SIGNING_KEY")
ALCHEMY_WEBHOOK_ID = os.environ.get("ALCHEMY_WEBHOOK_ID")


def subscribe_to_alchemy(address: str) -> bool:
    """Subscribe an address to the Alchemy Address Activity Webhook."""
    if not ALCHEMY_AUTH_TOKEN or not ALCHEMY_WEBHOOK_ID:
        logger.warning("Alchemy tokens missing, skipping subscription.")
        return False
        
    url = "https://dashboard.alchemy.com/api/update-webhook-addresses"
    headers = {
        "X-Alchemy-Token": ALCHEMY_AUTH_TOKEN,
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    payload = {
        "webhook_id": ALCHEMY_WEBHOOK_ID,
        "addresses_to_add": [address],
        "addresses_to_remove": []
    }
    
    response = requests.put(url, headers=headers, json=payload, timeout=10)
    
    try:
        response.raise_for_status()
        logger.info(f"Successfully subscribed {address} to Alchemy webhook.")
        return True
    except requests.exceptions.HTTPError as e:
        logger.error(f"Alchemy API Error: {response.text}")
        return False


def verify_alchemy_signature(request) -> bool:
    """Verify HMAC signature on incoming Alchemy webhook."""
    if not ALCHEMY_WEBHOOK_SECRET:
        return True  # dev mode / no secret configured
        
    signature = request.headers.get("x-alchemy-signature", "")
    if not signature:
        return False
        
    expected = hmac.new(
        ALCHEMY_WEBHOOK_SECRET.encode(),
        request.body,
        hashlib.sha256,
    ).hexdigest()
    
    return hmac.compare_digest(signature, expected)
