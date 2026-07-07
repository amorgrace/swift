"""
resubscribe_all_addresses.py
----------------------------
Re-registers ALL deposit addresses that have no webhook subscription.
Run once after deploying the PATCH fix for Alchemy.

    python resubscribe_all_addresses.py
"""

import os
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "engine.settings")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
django.setup()

from django.conf import settings
from wallets.models import DepositAddress
from wallets.alchemy import subscribe_to_alchemy
from wallets.blockcypher import subscribe_to_blockcypher


def main():
    print("=" * 60)
    print("  WEBHOOK RE-SUBSCRIPTION")
    print("=" * 60)

    unsubscribed = DepositAddress.objects.filter(
        tatum_subscription_id=""
    ).select_related("wallet__user").order_by("network", "wallet__user__email")

    # Also grab ERC20 addresses — some may have been sub'd via PUT (broken),
    # so we force re-subscribe them too just to be safe.
    # We identify broken ones as having tatum_subscription_id="alchemy_subscribed"
    # but were created before the PATCH fix. To be safe, re-register ALL ERC20.
    all_erc20 = DepositAddress.objects.filter(
        network="erc20"
    ).select_related("wallet__user").order_by("wallet__user__email")

    print(f"\nAddresses with NO subscription : {unsubscribed.count()}")
    print(f"ERC20 addresses (re-register all): {all_erc20.count()}")

    results = {"ok": 0, "failed": 0, "skipped": 0}

    # ── Re-register ALL ERC20 addresses via PATCH (now fixed) ──────────────
    print(f"\n-- ERC20 (Ethereum) Addresses --")
    seen_erc20 = set()
    for addr in all_erc20:
        if addr.address in seen_erc20:
            continue
        seen_erc20.add(addr.address)

        user = addr.wallet.user
        print(f"  Subscribing {addr.address} ({user.email}) ...")
        success = subscribe_to_alchemy(addr.address)
        if success:
            # Update ALL DepositAddress rows for this address (erc20/bep20 share address)
            DepositAddress.objects.filter(address=addr.address, network__in=["erc20", "bep20"]).update(
                tatum_subscription_id="alchemy_subscribed"
            )
            print(f"    [OK] Subscribed.")
            results["ok"] += 1
        else:
            print(f"    [FAILED] Alchemy subscription failed!")
            results["failed"] += 1

    # ── Register any BTC addresses with no subscription ─────────────────────
    print(f"\n-- Bitcoin Addresses --")
    btc_unsub = DepositAddress.objects.filter(
        network="bitcoin", tatum_subscription_id=""
    ).select_related("wallet__user")

    if not btc_unsub.exists():
        print("  All BTC addresses already subscribed.")
    else:
        webhook_url = f"{settings.BACKEND_URL}/api/webhooks/blockcypher-deposit/"
        for addr in btc_unsub:
            user = addr.wallet.user
            print(f"  Subscribing {addr.address} ({user.email}) ...")
            sub_id = subscribe_to_blockcypher(addr.address, webhook_url)
            if sub_id:
                addr.tatum_subscription_id = sub_id
                addr.save(update_fields=["tatum_subscription_id"])
                print(f"    [OK] Hook ID: {sub_id}")
                results["ok"] += 1
            else:
                print(f"    [FAILED] Blockcypher subscription failed!")
                results["failed"] += 1

    print(f"\n{'='*60}")
    print(f"  DONE: {results['ok']} subscribed, {results['failed']} failed")
    print(f"{'='*60}\n")

    if results["failed"] > 0:
        print("[ACTION REQUIRED] Some subscriptions failed.")
        print("Check ALCHEMY_AUTH_TOKEN and ALCHEMY_WEBHOOK_ID in .env.\n")
    else:
        print("[ALL GOOD] All addresses are now subscribed.")
        print("Your next test deposit should trigger the webhook correctly.\n")


if __name__ == "__main__":
    main()
