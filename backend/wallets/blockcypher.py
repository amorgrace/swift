import os
import requests
import logging

logger = logging.getLogger(__name__)

BLOCKCYPHER_TOKEN = os.environ.get("BLOCKCYPHER_TOKEN")
BLOCKCYPHER_BASE_URL = "https://api.blockcypher.com/v1/btc/main"


def subscribe_to_blockcypher(address: str, webhook_url: str) -> str:
    """Subscribe an address to Blockcypher tx-confirmation monitoring (2 confirmations)."""
    if not BLOCKCYPHER_TOKEN:
        logger.warning("BLOCKCYPHER_TOKEN is missing, skipping subscription.")
        return ""

    url = f"{BLOCKCYPHER_BASE_URL}/hooks?token={BLOCKCYPHER_TOKEN}"

    # Only subscribe to tx-confirmation — unconfirmed-tx events are rejected by
    # process_blockcypher_deposit (confirmations < 2) so they're pointless noise.
    conf_payload = {
        "event": "tx-confirmation",
        "address": address,
        "url": webhook_url,
        "confirmations": 2,
    }

    try:
        response = requests.post(url, json=conf_payload, timeout=10)
        response.raise_for_status()
        data = response.json()
        hook_id = data.get("id", "")
        logger.info(f"Subscribed {address} to Blockcypher tx-confirmation webhook. Hook ID: {hook_id}")
        return hook_id
    except requests.exceptions.HTTPError as e:
        logger.error(f"Blockcypher API Error subscribing {address}: {response.text}")
        return ""
    except requests.exceptions.RequestException as e:
        logger.error(f"Blockcypher request failed for {address}: {e}")
        return ""
