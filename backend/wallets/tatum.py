import os
import hmac
import hashlib
import requests
import logging
from hdwallet import HDWallet
from hdwallet.symbols import BTC, ETH

logger = logging.getLogger(__name__)

TATUM_API_KEY = os.environ.get("TATUM_API_KEY")
TATUM_WEBHOOK_SECRET = os.environ.get("TATUM_WEBHOOK_SECRET")
BTC_XPUB = os.environ.get("BTC_XPUB")
ETH_XPUB = os.environ.get("ETH_XPUB")

TATUM_BASE_URL = "https://api.tatum.io/v4"

CHAIN_MAP = {
    "bitcoin": "BTC",
    "erc20":   "ETH",   # ETH and all ERC-20 tokens
    "bep20":   "BSC",   # BSC support
}


def get_next_derivation_index(asset: str, network: str) -> int:
    from .models import DepositAddress
    last = (
        DepositAddress.objects
        .filter(asset=asset, network=network, derivation_index__isnull=False)
        .order_by("-derivation_index")
        .first()
    )
    return (last.derivation_index + 1) if last else 0


def derive_address(asset: str, network: str, index: int) -> str:
    """Derive a deposit address at the given index using xpub."""
    if network == "bitcoin":
        wallet = HDWallet(symbol=BTC)
        wallet.from_xpublic_key(BTC_XPUB)
        wallet.from_path(f"m/0/{index}")
        return wallet.p2pkh_address()

    elif network in ("erc20", "bep20"):
        # ETH address works for all ERC-20 and BEP-20 tokens
        wallet = HDWallet(symbol=ETH)
        wallet.from_xpublic_key(ETH_XPUB)
        wallet.from_path(f"m/0/{index}")
        return wallet.p2pkh_address()

    else:
        raise ValueError(f"Unsupported network for HD derivation: {network}")


def subscribe_to_tatum(address: str, network: str, webhook_url: str) -> str:
    """Subscribe an address to Tatum incoming transaction monitoring."""
    chain = CHAIN_MAP.get(network)
    if not chain:
        raise ValueError(f"No Tatum chain mapping for network: {network}")

    if not TATUM_API_KEY:
        logger.warning("TATUM_API_KEY is missing, skipping subscription.")
        return ""

    response = requests.post(
        f"{TATUM_BASE_URL}/subscription",
        headers={"x-api-key": TATUM_API_KEY},
        json={
            "type": "INCOMING_NATIVE_TX",
            "attr": {
                "address": address,
                "chain": chain,
                "url": webhook_url,
            },
        },
        timeout=10,
    )
    
    try:
        response.raise_for_status()
    except requests.exceptions.HTTPError as e:
        logger.error(f"Tatum API Error: {response.text}")
        raise e
        
    return response.json().get("id", "")


def verify_tatum_signature(request) -> bool:
    """Verify HMAC signature on incoming Tatum webhook."""
    if not TATUM_WEBHOOK_SECRET:
        return True  # dev mode / no secret configured
    signature = request.headers.get("x-payload-hash", "")
    if not signature:
        return False
        
    expected = hmac.new(
        TATUM_WEBHOOK_SECRET.encode(),
        request.body,
        hashlib.sha256,
    ).hexdigest()
    
    return hmac.compare_digest(signature, expected)
