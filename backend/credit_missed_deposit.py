"""
credit_missed_deposit.py  (v2 — no Celery/Redis required)
----------------------------------------------------------
Credits the single missed ETH deposit for famakinwa99@gmail.com.
Calls email, Telegram, and in-app notification directly — no Redis needed.

Run from the backend directory:
    python credit_missed_deposit.py
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
from datetime import datetime
from django.db import transaction as db_transaction

from rates.services import RateService
from wallets.models import DepositAddress, NGNWallet
from transactions.models import (
    Deposit, Transaction, DepositStatus, TransactionType, generate_transaction_id
)
from authenticator.email import send_email
from notifications.models import Notification
from notifications.telegram import TelegramNotifier
from authenticator.models import User

# ── The one missed deposit ──────────────────────────────────────────────────
TX_HASH    = "0x9db3be45a6f8108d2887ac1c885a07d1db185696cebba54f805ae6a85474ec21"
TO_ADDR    = "0x51c895483dbc07c2741EEf3Bf95f654DF7039F22"
ASSET      = "eth"
NETWORK    = "erc20"   # detected on Ethereum Mainnet by Alchemy
AMOUNT     = Decimal("0.00052")
# ───────────────────────────────────────────────────────────────────────────


def main():
    print("=" * 60)
    print("  MANUAL DEPOSIT CREDIT  (direct, no Celery)")
    print("=" * 60)

    # Guard: don't double-credit
    if Deposit.objects.filter(quidax_reference=TX_HASH).exists():
        print(f"\n[ALREADY DONE] TX {TX_HASH[:22]}... already in DB.")
        print("No action taken — safe to run again.\n")
        return

    # Lookup wallet
    dep_addr = DepositAddress.objects.select_related("wallet__user").filter(
        address__iexact=TO_ADDR,
        network=NETWORK,
    ).first()

    if not dep_addr:
        print(f"\n[ERROR] DepositAddress not found for {TO_ADDR} / {NETWORK}")
        return

    wallet = dep_addr.wallet
    user   = wallet.user

    print(f"\nUser    : {user.full_name} <{user.email}>")
    print(f"Wallet  : #{wallet.id}")
    print(f"Asset   : {ASSET.upper()}")
    print(f"Amount  : {AMOUNT} ETH")
    print(f"Network : {NETWORK.upper()}")
    print(f"TX      : {TX_HASH}")

    # ── 1. Get live rate & calculate NGN ────────────────────────────────────
    print(f"\nFetching live ETH rate ...")
    rate_info   = RateService.calculate_ngn_amount(ASSET, AMOUNT)
    ngn_amount  = rate_info["ngn_amount"]
    user_rate   = rate_info["user_rate"]
    margin      = rate_info["margin_percentage"]
    ngn_usd_rate = rate_info.get("ngn_usd_rate")
    print(f"Rate    : {user_rate:,.2f} NGN/ETH  |  NGN credited = {ngn_amount:,.2f}")

    balance_before = wallet.balance
    print(f"\nBalance before : {balance_before:,.2f}")

    # ── 2. DB writes ─────────────────────────────────────────────────────────
    with db_transaction.atomic():
        deposit = Deposit.objects.create(
            wallet=wallet,
            asset=ASSET,
            network=NETWORK,
            crypto_amount=AMOUNT,
            rate_applied=user_rate,
            margin_applied=margin,
            ngn_usd_rate=ngn_usd_rate,
            ngn_amount=ngn_amount,
            quidax_reference=TX_HASH,
            status=DepositStatus.CONVERTED,
        )

        wallet.credit(ngn_amount)

        description = f"Received {AMOUNT} {ASSET.upper()} -> N{ngn_amount:,.2f}"
        Transaction.objects.create(
            wallet=wallet,
            type=TransactionType.DEPOSIT,
            amount=ngn_amount,
            description=description,
            status=DepositStatus.CONVERTED,
            related_deposit=deposit,
            reference=generate_transaction_id(),
        )

    wallet.refresh_from_db()
    print(f"Balance after  : {wallet.balance:,.2f}")
    print(f"\n[DB OK] Deposit and Transaction records created.")

    # ── 3. Email ─────────────────────────────────────────────────────────────
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    print(f"\nSending deposit email ...")
    try:
        send_email(
            to_email=user.email,
            to_name=user.full_name,
            subject=f"SwiftTrade - Deposit Received ({ASSET.upper()})",
            template_name="emails/deposit_received.html",
            context={
                "full_name": user.full_name,
                "asset": ASSET.upper(),
                "crypto_amount": str(AMOUNT),
                "ngn_amount": f"{ngn_amount:,.2f}",
                "timestamp": timestamp,
            },
        )
        print(f"  [OK] Email sent to {user.email}")
    except Exception as e:
        print(f"  [WARN] Email failed (non-fatal): {e}")

    # ── 4. In-app notification ───────────────────────────────────────────────
    print(f"Creating in-app notification ...")
    try:
        Notification.objects.create(
            user=user,
            type="trade",
            title="Deposit Received & Converted",
            body=f"Your deposit of {AMOUNT} {ASSET.upper()} was successfully converted to N{ngn_amount:,.2f}.",
        )
        print(f"  [OK] In-app notification created.")
    except Exception as e:
        print(f"  [WARN] In-app notification failed (non-fatal): {e}")

    # ── 5. Telegram ──────────────────────────────────────────────────────────
    print(f"Sending Telegram alert ...")
    telegram_msg = (
        "📥 <b>MANUAL CREDIT (missed deposit)</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>User:</b> {user.full_name} ({user.email})\n"
        f"💰 <b>Crypto:</b> {AMOUNT} {ASSET.upper()}\n"
        f"💵 <b>NGN Credited:</b> ₦{ngn_amount:,.2f}\n"
        f"📊 <b>Rate Used:</b> ₦{user_rate:,.2f}/ETH\n"
        f"🔗 <b>TX:</b> <code>{TX_HASH}</code>\n"
        f"⏰ {timestamp}"
    )
    try:
        TelegramNotifier._send(telegram_msg)
        print(f"  [OK] Telegram sent.")
    except Exception as e:
        print(f"  [WARN] Telegram failed (non-fatal): {e}")

    print(f"\n{'='*60}")
    print(f"  DONE. User has been credited N{ngn_amount:,.2f}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
