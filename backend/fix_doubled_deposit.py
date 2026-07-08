"""
fix_doubled_deposit.py

Run with:
  python fix_doubled_deposit.py

This script:
  1. Finds all deposits for famakinwa99@gmail.com
  2. Identifies any duplicated tx_hashes (same tx credited twice —
     once manually with a different reference, once by webhook)
  3. Shows the exact excess amount
  4. Debits the wallet by the duplicate amount and marks the
     duplicate Deposit + Transaction as FAILED so the audit trail
     is clear

If there are no duplicates it prints ALL CLEAR and exits safely.
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

from decimal import Decimal
from django.db import transaction as db_transaction

from authenticator.models import User
from wallets.models import NGNWallet
from transactions.models import Deposit, Transaction, DepositStatus

TARGET_EMAIL = "famakinwa99@gmail.com"


def main():
    print("=" * 70)
    print("  DOUBLE-DEPOSIT BALANCE FIX")
    print("=" * 70)

    try:
        user = User.objects.get(email=TARGET_EMAIL)
    except User.DoesNotExist:
        print(f"\n[ERROR] No user found with email: {TARGET_EMAIL}")
        sys.exit(1)

    try:
        wallet = NGNWallet.objects.get(user=user)
    except NGNWallet.DoesNotExist:
        print(f"\n[ERROR] No wallet found for {TARGET_EMAIL}")
        sys.exit(1)

    print(f"\nUser    : {user.full_name} <{user.email}>")
    print(f"Wallet  : #{wallet.id}")
    print(f"Balance : ₦{wallet.balance:,.2f}\n")

    # Fetch all deposits for this wallet, newest first
    all_deposits = list(
        Deposit.objects.filter(wallet=wallet).order_by("created_at")
    )

    print(f"Total deposit records : {len(all_deposits)}")
    print()

    if not all_deposits:
        print("[ALL CLEAR] No deposits found. Nothing to fix.")
        return

    # Print all deposits for visibility
    print(f"{'#':<4} {'ID':<6} {'Asset':<8} {'Crypto':<18} {'NGN Amount':<18} {'tx_hash / reference':<66} {'Status':<12} {'Created'}")
    print("-" * 150)
    for i, d in enumerate(all_deposits, 1):
        print(
            f"{i:<4} {d.id:<6} {d.asset.upper():<8} {str(d.crypto_amount):<18} "
            f"₦{d.ngn_amount:,.2f}{'':>4} {d.tx_hash:<66} {d.status:<12} {d.created_at:%Y-%m-%d %H:%M UTC}"
        )

    print()

    # ─── Strategy ───────────────────────────────────────────────────────────
    # Look for deposits that are CLEARLY duplicates:
    #   a) Same crypto_amount + same asset — look for pairs where one has a
    #      real tx_hash (starts with 0x or is 64 hex chars) and one has a
    #      placeholder/manual reference.
    #   b) The duplicate is whichever was created LATER.
    # ─────────────────────────────────────────────────────────────────────────

    import re
    real_tx_pattern = re.compile(r'^(0x[0-9a-f]{64}|[0-9a-f]{64})$', re.IGNORECASE)

    def looks_like_real_tx(ref: str) -> bool:
        return bool(real_tx_pattern.match(ref.strip()))

    # Group by (asset, crypto_amount) to find duplicates
    from collections import defaultdict
    groups: dict = defaultdict(list)
    for d in all_deposits:
        key = (d.asset, str(d.crypto_amount))
        groups[key].append(d)

    duplicates_found = []
    for key, deposits in groups.items():
        if len(deposits) < 2:
            continue
        # More than one deposit for the same asset+amount = potential duplicate
        print(f"[ALERT] Found {len(deposits)} deposit(s) for {key[0].upper()} {key[1]}:")
        for d in deposits:
            print(f"  → ID={d.id}  ref={d.tx_hash}  NGN=₦{d.ngn_amount:,.2f}  status={d.status}  created={d.created_at:%Y-%m-%d %H:%M}")

        # The duplicate is the one with an INVALID / placeholder reference
        # (manual credits tend to have non-tx references)
        real = [d for d in deposits if looks_like_real_tx(d.tx_hash)]
        manual = [d for d in deposits if not looks_like_real_tx(d.tx_hash)]

        if real and manual:
            for dup in manual:
                duplicates_found.append(dup)
                print(f"  ✗ Duplicate identified: ID={dup.id} (manual/placeholder ref) — will reverse ₦{dup.ngn_amount:,.2f}")
        else:
            # Can't auto-determine — flag for manual review
            print(f"  ⚠ Cannot auto-identify duplicate — all refs look similar. MANUAL REVIEW REQUIRED.")
            for d in deposits:
                print(f"    ID={d.id}  ref={d.tx_hash}")

    print()

    if not duplicates_found:
        print("[ALL CLEAR] No automatic duplicate deposits identified.")
        print("If you believe the balance is still wrong, review the table above manually.")
        return

    total_excess = sum(d.ngn_amount for d in duplicates_found)
    print(f"Total excess to reverse : ₦{total_excess:,.2f}")
    print(f"Current balance         : ₦{wallet.balance:,.2f}")
    print(f"Corrected balance       : ₦{wallet.balance - total_excess:,.2f}")
    print()

    confirm = input("Proceed with reversal? (yes/no): ").strip().lower()
    if confirm != "yes":
        print("Aborted. No changes made.")
        return

    # ─── Apply reversal ──────────────────────────────────────────────────────
    with db_transaction.atomic():
        locked_wallet = NGNWallet.objects.select_for_update().get(pk=wallet.pk)

        for dup in duplicates_found:
            # Mark deposit as FAILED
            dup.status = DepositStatus.FAILED
            dup.save(update_fields=["status", "updated_at"])

            # Mark the linked Transaction log entry as failed too
            linked_tx = Transaction.objects.filter(related_deposit=dup).first()
            if linked_tx:
                linked_tx.status = "failed"
                linked_tx.save(update_fields=["status"])
                print(f"  Marked Transaction #{linked_tx.id} as failed.")

            # Debit the excess from the wallet
            locked_wallet.balance -= dup.ngn_amount
            print(f"  Reversed ₦{dup.ngn_amount:,.2f} for Deposit #{dup.id}.")

        locked_wallet.save(update_fields=["balance", "updated_at"])
        wallet.balance = locked_wallet.balance

    print()
    print("=" * 70)
    print(f"  DONE — Balance corrected to ₦{wallet.balance:,.2f}")
    print("=" * 70)


if __name__ == "__main__":
    main()
