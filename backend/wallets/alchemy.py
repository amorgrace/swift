import os
import hmac
import hashlib
import requests
import logging

logger = logging.getLogger(__name__)

ALCHEMY_AUTH_TOKEN = os.environ.get("ALCHEMY_AUTH_TOKEN")
ALCHEMY_WEBHOOK_SECRET = os.environ.get("ALCHEMY_SIGNING_KEY")
ALCHEMY_WEBHOOK_ID = os.environ.get("ALCHEMY_WEBHOOK_ID")


def subscribe_to_alchemy(address: str, webhook_id: str = None) -> bool:
    """Subscribe an address to the Alchemy Address Activity Webhook."""
    target_webhook_id = webhook_id or ALCHEMY_WEBHOOK_ID
    if not ALCHEMY_AUTH_TOKEN or not target_webhook_id:
        logger.warning("Alchemy tokens missing, skipping subscription.")
        return False
        
    url = "https://dashboard.alchemy.com/api/update-webhook-addresses"
    headers = {
        "X-Alchemy-Token": ALCHEMY_AUTH_TOKEN,
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    payload = {
        "webhook_id": target_webhook_id,
        "addresses_to_add": [address],
        "addresses_to_remove": []
    }
    
    response = requests.patch(url, headers=headers, json=payload, timeout=10)
    
    try:
        response.raise_for_status()
        logger.info(f"Successfully subscribed {address} to Alchemy webhook.")
        return True
    except requests.exceptions.HTTPError as e:
        logger.error(f"Alchemy API Error: {response.text}")
        return False


def verify_alchemy_signature(request) -> bool:
    """Verify HMAC signature on incoming Alchemy webhook."""
    signature = request.headers.get("x-alchemy-signature", "")
    if not signature:
        return False
        
    keys_to_try = []
    if os.environ.get("ALCHEMY_SIGNING_KEY"):
        keys_to_try.append(os.environ.get("ALCHEMY_SIGNING_KEY"))
    if os.environ.get("ALCHEMY_BEP20_SIGNING_KEY"):
        keys_to_try.append(os.environ.get("ALCHEMY_BEP20_SIGNING_KEY"))
        
    if not keys_to_try:
        return True  # dev mode / no secret configured
        
    for secret in keys_to_try:
        expected = hmac.new(
            secret.encode(),
            request.body,
            hashlib.sha256,
        ).hexdigest()
        
        if hmac.compare_digest(signature, expected):
            return True
            
    return False
