import os
import requests
import logging

logger = logging.getLogger(__name__)

BLOCKCYPHER_TOKEN = os.environ.get("BLOCKCYPHER_TOKEN")
BLOCKCYPHER_BASE_URL = "https://api.blockcypher.com/v1/btc/main"


def subscribe_to_blockcypher(address: str, webhook_url: str) -> str:
    """Subscribe an address to Blockcypher transaction monitoring."""
    if not BLOCKCYPHER_TOKEN:
        logger.warning("BLOCKCYPHER_TOKEN is missing, skipping subscription.")
        return ""
        
    url = f"{BLOCKCYPHER_BASE_URL}/hooks?token={BLOCKCYPHER_TOKEN}"
    payload = {
        "event": "unconfirmed-tx",
        "address": address,
        "url": webhook_url,
    }
    
    response = requests.post(url, json=payload, timeout=10)
    
    try:
        response.raise_for_status()
        data = response.json()
        logger.info(f"Successfully subscribed {address} to Blockcypher webhook (unconfirmed).")
        hook_id = data.get("id", "")
        
        # Subscribe for confirmed tx as well
        conf_payload = {
            "event": "tx-confirmation",
            "address": address,
            "url": webhook_url,
            "confirmations": 2
        }
        requests.post(url, json=conf_payload, timeout=10)
        
        return hook_id
    except requests.exceptions.HTTPError as e:
        logger.error(f"Blockcypher API Error: {response.text}")
        return ""
