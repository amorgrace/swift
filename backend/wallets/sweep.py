"""
wallets/sweep.py — Core sweep service.

Handles on-chain sweeping of crypto from user HD-derived sub-wallets
to the master admin wallet defined in settings.

BTC  : Uses xpriv to derive private keys + `bit` library to sign/broadcast.
EVM  : Uses EVM_SWEEP_PRIVATE_KEY + web3.py to transfer ETH or ERC-20 tokens.
        For ERC-20, if the sub-wallet lacks gas, it first sends ETH from the
        master wallet to cover gas, then sweeps the tokens.
"""
import os
import logging
from decimal import Decimal
from typing import List, Dict

logger = logging.getLogger(__name__)

# ── Config ──────────────────────────────────────────────────────────────────
BTC_XPRIV          = os.environ.get("BTC_XPRIV", "")
BTC_MASTER_ADDRESS = os.environ.get("MASTER_BTC_ADDRESS", "")
EVM_MASTER_ADDRESS = os.environ.get("MASTER_EVM_ADDRESS", "")
EVM_SWEEP_KEY      = os.environ.get("EVM_SWEEP_PRIVATE_KEY", "")  # master wallet private key

# Alchemy RPC endpoints
ALCHEMY_ETH_RPC    = f"https://eth-mainnet.g.alchemy.com/v2/{os.environ.get('ALCHEMY_API_KEY', '')}"
ALCHEMY_BSC_RPC    = "https://bsc-dataseed.binance.org/"   # Public BSC RPC

# ERC-20 token contract addresses (Mainnet)
ERC20_CONTRACTS = {
    "usdt": {
        "erc20": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
        "bep20": "0x55d398326f99059fF775485246999027B3197955",
    },
    "usdc": {
        "erc20": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
    },
    "bnb": {
        # Native BNB — treated as native token on BEP20
    },
}

# Minimal ERC-20 ABI
ERC20_ABI = [
    {"constant": True,  "inputs": [{"name": "_owner","type": "address"}],
     "name": "balanceOf", "outputs": [{"name": "balance","type": "uint256"}],
     "type": "function"},
    {"constant": False,
     "inputs": [{"name": "_to","type": "address"},{"name": "_value","type": "uint256"}],
     "name": "transfer", "outputs": [{"name": "","type": "bool"}],
     "type": "function"},
]


# ── BTC Sweep ────────────────────────────────────────────────────────────────

def _get_btc_network():
    """Returns bit.PrivateKeyTestnet or bit.PrivateKey based on env flag."""
    from bit import PrivateKey
    return PrivateKey


def derive_btc_private_key(index: int):
    """Derive the private key for a BTC address at the given derivation index."""
    from hdwallet import HDWallet
    from hdwallet.symbols import BTC

    if not BTC_XPRIV:
        raise ValueError("BTC_XPRIV is not configured in environment.")

    wallet = HDWallet(symbol=BTC)
    wallet.from_xprivate_key(BTC_XPRIV)
    wallet.from_path(f"m/0/{index}")
    return wallet.private_key()


def sweep_btc_addresses(deposit_entries: List[Dict]) -> Dict:
    """
    Sweep BTC from one or more deposit addresses into the master BTC wallet.
    deposit_entries: list of {'address': str, 'index': int}
    Returns: {'tx_hash': str, 'total_swept': Decimal, 'gas_cost': Decimal}
    """
    from bit import PrivateKey

    if not BTC_MASTER_ADDRESS:
        raise ValueError("MASTER_BTC_ADDRESS is not configured.")

    keys = []
    for entry in deposit_entries:
        try:
            wif = derive_btc_private_key(entry["index"])
            key = PrivateKey(wif)
            balance = key.get_balance("btc")
            if float(balance) > 0.000015:  # min dust threshold
                keys.append(key)
                logger.info(f"[BTC Sweep] Address {entry['address']} has {balance} BTC")
            else:
                logger.info(f"[BTC Sweep] Skipping {entry['address']} — dust balance")
        except Exception as e:
            logger.error(f"[BTC Sweep] Key derivation failed for index {entry['index']}: {e}")

    if not keys:
        return {"tx_hash": "", "total_swept": Decimal("0"), "gas_cost": Decimal("0")}

    # Consolidate: send everything from all keys to master, fees auto-deducted
    # bit handles fee calculation and deduction from sweep amount automatically
    tx_hash = PrivateKey.sweep(keys, BTC_MASTER_ADDRESS)
    logger.info(f"[BTC Sweep] Broadcast tx: {tx_hash}")

    return {
        "tx_hash": tx_hash,
        "total_swept": Decimal("0"),   # will be updated after confirmation
        "gas_cost": Decimal("0"),
        "addresses": [e["address"] for e in deposit_entries],
    }


# ── EVM Sweep ────────────────────────────────────────────────────────────────

def _get_web3(network: str):
    """Return a connected Web3 instance for the given network."""
    from web3 import Web3
    rpc = ALCHEMY_ETH_RPC if network == "erc20" else ALCHEMY_BSC_RPC
    w3 = Web3(Web3.HTTPProvider(rpc))
    if not w3.is_connected():
        raise ConnectionError(f"Cannot connect to {network} RPC at {rpc}")
    return w3


def _get_evm_balance(w3, address: str, asset: str, network: str) -> int:
    """Return token or native balance in smallest units (wei / satoshi)."""
    from web3 import Web3

    if asset in ("eth", "bnb"):
        return w3.eth.get_balance(Web3.to_checksum_address(address))

    contract_addr = ERC20_CONTRACTS.get(asset, {}).get(network)
    if not contract_addr:
        return 0
    contract = w3.eth.contract(
        address=Web3.to_checksum_address(contract_addr),
        abi=ERC20_ABI,
    )
    return contract.functions.balanceOf(Web3.to_checksum_address(address)).call()


def _ensure_gas(w3, sub_address: str, asset: str, network: str) -> None:
    """
    If the sub-wallet needs gas for a token sweep, send ETH/BNB from master.
    Only needed for ERC-20 / BEP-20 token sweeps (not native ETH/BNB).
    """
    from web3 import Web3

    if asset in ("eth", "bnb"):
        return  # native — no top-up needed

    GAS_BUFFER = w3.to_wei("0.002", "ether")   # ~$5 worth — covers multiple txns
    balance = w3.eth.get_balance(Web3.to_checksum_address(sub_address))

    if balance >= GAS_BUFFER:
        return  # already has enough gas

    logger.info(f"[EVM Sweep] Sending gas top-up to {sub_address}")
    master_account = w3.eth.account.from_key(EVM_SWEEP_KEY)
    nonce = w3.eth.get_transaction_count(master_account.address)
    gas_price = w3.eth.gas_price

    tx = {
        "nonce": nonce,
        "to": Web3.to_checksum_address(sub_address),
        "value": GAS_BUFFER,
        "gas": 21000,
        "gasPrice": gas_price,
        "chainId": w3.eth.chain_id,
    }
    signed = master_account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    # Wait for gas top-up to land before proceeding
    w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    logger.info(f"[EVM Sweep] Gas top-up confirmed for {sub_address}")


def sweep_evm_addresses(deposit_entries: List[Dict], asset: str, network: str) -> Dict:
    """
    Sweep ETH/BNB or ERC-20/BEP-20 tokens from all sub-wallets to master.
    deposit_entries: list of {'address': str, 'index': int}
    Returns: {'tx_hashes': list, 'total_swept_wei': int, 'gas_cost_wei': int}
    """
    from web3 import Web3
    from hdwallet import HDWallet
    from hdwallet.symbols import ETH as ETH_SYM

    if not EVM_MASTER_ADDRESS:
        raise ValueError("MASTER_EVM_ADDRESS is not configured.")
    if not EVM_SWEEP_KEY:
        raise ValueError("EVM_SWEEP_PRIVATE_KEY is not configured.")

    w3 = _get_web3(network)
    tx_hashes = []
    total_swept_wei = 0
    total_gas_wei = 0

    # Derive ETH xpriv
    ETH_XPRIV = os.environ.get("ETH_XPRIV", "")

    for entry in deposit_entries:
        sub_address = entry["address"]
        index = entry["index"]

        try:
            # Derive sub-wallet private key from xpriv
            if not ETH_XPRIV:
                raise ValueError("ETH_XPRIV is not configured.")

            hw = HDWallet(symbol=ETH_SYM)
            hw.from_xprivate_key(ETH_XPRIV)
            hw.from_path(f"m/0/{index}")
            sub_private_key = hw.private_key()
            sub_account = w3.eth.account.from_key(sub_private_key)

            balance = _get_evm_balance(w3, sub_address, asset, network)
            if balance == 0:
                logger.info(f"[EVM Sweep] Skipping {sub_address} — zero balance")
                continue

            # Ensure gas exists for token sweeps
            _ensure_gas(w3, sub_address, asset, network)

            gas_price = w3.eth.gas_price
            nonce = w3.eth.get_transaction_count(sub_account.address)

            if asset in ("eth", "bnb"):
                # Native — subtract gas from amount
                gas_limit = 21000
                gas_cost = gas_limit * gas_price
                sweep_value = balance - gas_cost
                if sweep_value <= 0:
                    logger.info(f"[EVM Sweep] Skipping {sub_address} — balance < gas")
                    continue

                tx = {
                    "nonce": nonce,
                    "to": Web3.to_checksum_address(EVM_MASTER_ADDRESS),
                    "value": sweep_value,
                    "gas": gas_limit,
                    "gasPrice": gas_price,
                    "chainId": w3.eth.chain_id,
                }
                total_gas_wei += gas_cost
                total_swept_wei += sweep_value
            else:
                # ERC-20 token transfer
                contract_addr = ERC20_CONTRACTS[asset][network]
                contract = w3.eth.contract(
                    address=Web3.to_checksum_address(contract_addr),
                    abi=ERC20_ABI,
                )
                gas_estimate = contract.functions.transfer(
                    Web3.to_checksum_address(EVM_MASTER_ADDRESS),
                    balance,
                ).estimate_gas({"from": sub_account.address})

                tx = contract.functions.transfer(
                    Web3.to_checksum_address(EVM_MASTER_ADDRESS),
                    balance,
                ).build_transaction({
                    "nonce": nonce,
                    "gas": gas_estimate,
                    "gasPrice": gas_price,
                    "chainId": w3.eth.chain_id,
                })
                total_gas_wei += gas_estimate * gas_price
                total_swept_wei += balance

            signed = sub_account.sign_transaction(tx)
            tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
            tx_hash_hex = tx_hash.hex()
            tx_hashes.append(tx_hash_hex)
            logger.info(f"[EVM Sweep] Broadcast tx for {sub_address}: {tx_hash_hex}")

        except Exception as e:
            logger.error(f"[EVM Sweep] Failed for {sub_address}: {e}")

    return {
        "tx_hashes": tx_hashes,
        "total_swept_wei": total_swept_wei,
        "total_gas_wei": total_gas_wei,
    }


# ── Balance Fetcher (for admin UI preview) ──────────────────────────────────

def fetch_pending_balances() -> List[Dict]:
    """
    Fetch live on-chain balances for all deposit addresses across all networks.
    Returns a list of dicts suitable for the admin UI.
    """
    from wallets.models import DepositAddress, NetworkChoices

    results = []
    addresses = DepositAddress.objects.select_related("wallet__user").all()

    # Group by (asset, network)
    groups: Dict[tuple, List] = {}
    for addr in addresses:
        key = (addr.asset, addr.network)
        groups.setdefault(key, []).append(addr)

    for (asset, network), addr_list in groups.items():
        total = Decimal("0")
        entries = []

        for addr in addr_list:
            try:
                if network == "bitcoin":
                    from bit.network import NetworkAPI
                    satoshis = NetworkAPI.get_balance(addr.address)
                    bal = Decimal(satoshis) / Decimal(100000000)
                else:
                    w3 = _get_web3(network)
                    raw = _get_evm_balance(w3, addr.address, asset, network)
                    decimals = 18 if asset in ("eth", "bnb") else 6  # USDT/USDC = 6
                    bal = Decimal(raw) / Decimal(10 ** decimals)

                if bal > 0:
                    total += bal
                    entries.append({
                        "address": addr.address,
                        "index": addr.derivation_index,
                        "balance": float(bal),
                        "user_email": addr.wallet.user.email,
                    })
            except Exception as e:
                logger.error(f"[Balance Fetch] {addr.address}: {e}")

        if total > 0:
            results.append({
                "asset": asset.upper(),
                "network": network,
                "total_balance": float(total),
                "address_count": len(entries),
                "entries": entries,
            })

    return results
