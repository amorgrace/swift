import os
import sys
import io

# Force UTF-8 output on Windows console
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import django
import requests
from decimal import Decimal

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "engine.settings")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
django.setup()

from wallets.models import DepositAddress
from transactions.models import Deposit

ALCHEMY_API_KEY = os.environ.get("ALCHEMY_API_KEY", "")
ALCHEMY_RPC_URL = f"https://eth-mainnet.g.alchemy.com/v2/{ALCHEMY_API_KEY}"


def alchemy_get_asset_transfers(to_address: str):
    payload = {
        "id": 1,
        "jsonrpc": "2.0",
        "method": "alchemy_getAssetTransfers",
        "params": [
            {
                "fromBlock": "0x0",
                "toBlock": "latest",
                "toAddress": to_address,
                "category": ["external", "erc20"],
                "withMetadata": True,
                "excludeZeroValue": True,
                "maxCount": "0x3e8",
            }
        ],
    }
    try:
        resp = requests.post(ALCHEMY_RPC_URL, json=payload, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        return data.get("result", {}).get("transfers", [])
    except Exception as e:
        print(f"  [ERROR] Alchemy API call failed for {to_address}: {e}")
        return []


def main():
    print("=" * 70)
    print("  MISSED DEPOSIT FINDER")
    print("=" * 70)

    erc20_addresses = list(
        DepositAddress.objects.filter(network__in=["erc20", "bep20"])
        .select_related("wallet__user")
        .order_by("wallet__user__email")
    )

    btc_addresses = list(
        DepositAddress.objects.filter(network="bitcoin")
        .select_related("wallet__user")
        .order_by("wallet__user__email")
    )

    print(f"\nFound {len(erc20_addresses)} ERC20/BEP20 deposit addresses in DB.")
    print(f"Found {len(btc_addresses)} BTC deposit addresses in DB.")
    print(f"\nNote: BTC check requires Blockcypher API - checking ERC20 only via Alchemy.\n")

    credited_hashes = set(
        Deposit.objects.values_list("quidax_reference", flat=True)
    )
    print(f"Already credited tx hashes in DB: {len(credited_hashes)}\n")

    missed = []

    for dep_addr in erc20_addresses:
        address = dep_addr.address
        user = dep_addr.wallet.user
        print(f"Checking {address} ({user.email}, network={dep_addr.network}) ...")

        transfers = alchemy_get_asset_transfers(address)

        if not transfers:
            print(f"  -> No transfers found.")
            continue

        for tx in transfers:
            tx_hash = (tx.get("hash") or "").lower()
            asset_symbol = (tx.get("asset") or "").upper()
            value = tx.get("value") or 0
            from_addr = tx.get("from", "")
            block_num = tx.get("blockNum", "")
            metadata = tx.get("metadata", {})
            timestamp = metadata.get("blockTimestamp", "unknown time")

            if tx_hash in credited_hashes:
                print(f"  [OK] {tx_hash[:20]}... already credited ({asset_symbol} {value})")
                continue

            missed.append({
                "user_email": user.email,
                "user_name": user.full_name,
                "user_id": str(user.id),
                "wallet_id": dep_addr.wallet.id,
                "address": address,
                "network": dep_addr.network,
                "tx_hash": tx_hash,
                "asset": asset_symbol,
                "amount": Decimal(str(value)),
                "from": from_addr,
                "block": block_num,
                "timestamp": timestamp,
            })
            print(f"  [MISSED] {asset_symbol} {value} from {from_addr} | tx {tx_hash[:22]}... | {timestamp}")

    print("\n" + "=" * 70)
    print(f"  SUMMARY: {len(missed)} MISSED DEPOSIT(S) FOUND")
    print("=" * 70)

    if not missed:
        print("\n[ALL CLEAR] All tracked deposits have been credited. Nothing missed.\n")
        return

    for i, m in enumerate(missed, 1):
        print(f"\n{'─'*60}")
        print(f"  #{i}")
        print(f"  User       : {m['user_name']} <{m['user_email']}>")
        print(f"  User ID    : {m['user_id']}")
        print(f"  Wallet ID  : {m['wallet_id']}")
        print(f"  Network    : {m['network'].upper()}")
        print(f"  Asset      : {m['asset']}")
        print(f"  Amount     : {m['amount']}")
        print(f"  To Address : {m['address']}")
        print(f"  From       : {m['from']}")
        print(f"  TX Hash    : {m['tx_hash']}")
        print(f"  Block      : {m['block']}")
        print(f"  Time       : {m['timestamp']}")

    print(f"\n{'─'*60}")
    print(f"\nTell me which ones to credit and I'll process them.")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
