import os
from hdwallet import HDWallet
from hdwallet.symbols import BTC, ETH

BTC_XPUB = os.environ.get("BTC_XPUB")
ETH_XPUB = os.environ.get("ETH_XPUB")

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
