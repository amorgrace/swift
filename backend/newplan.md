# Swift Trade — HD Wallet Crypto Deposit System
## Full Implementation Plan

---

## Overview

This document describes the complete architecture and implementation plan for Swift Trade's crypto deposit system. The goal is to allow users to deposit BTC, ETH, and USDT into the platform using a self-custodied HD wallet setup, with Tatum monitoring incoming transactions and Django crediting the internal ledger automatically.

No Quidax. No third-party custody. You own the keys.

---

## Architecture Summary

```
User
  └── sends crypto to their unique deposit address

HD Wallet (xpub on VPS, seed offline on your laptop/USB)
  └── generates one unique address per user per coin

Tatum (blockchain monitoring service)
  └── watches all deposit addresses
  └── fires webhook to Django when crypto arrives

Django Backend (on VPS)
  └── receives webhook
  └── verifies transaction
  └── credits user's internal ledger
  └── queues pending withdrawals

Your Laptop (offline signing script)
  └── fetches pending withdrawals from Django
  └── derives private key from seed
  └── signs transaction
  └── broadcasts to blockchain
  └── reports tx hash back to Django
```

---

## Part 1 — HD Wallet Setup (Done Once, Offline)

### 1.1 What is an HD Wallet

An HD (Hierarchical Deterministic) wallet generates an infinite tree of addresses all from one master seed. You back up the seed once and can always regenerate every address and private key.

```
Master Seed (12/24 word mnemonic)
  └── m/44'/0'/0'/0/0   → User 1 BTC deposit address
  └── m/44'/0'/0'/0/1   → User 2 BTC deposit address
  └── m/44'/0'/0'/0/2   → User 3 BTC deposit address

Master Seed
  └── m/44'/60'/0'/0/0  → User 1 ETH/USDT deposit address
  └── m/44'/60'/0'/0/1  → User 2 ETH/USDT deposit address
```

### 1.2 Derivation Paths to Use

| Coin | Derivation Path | Notes |
|---|---|---|
| BTC | m/44'/0'/0'/0/{index} | BIP44 standard |
| ETH | m/44'/60'/0'/0/{index} | Same address works for USDT ERC-20 |
| USDT TRC-20 | m/44'/195'/0'/0/{index} | TRON network |

### 1.3 What to Generate (Once, Offline)

Run a local Python script on your laptop (NOT on the VPS) to:

1. Generate a 24-word BIP39 mnemonic
2. Derive the master xpub (extended public key) for each coin family
3. Print and save the mnemonic securely

```python
# generate_wallet.py — run ONCE on your laptop, NEVER on VPS

from hdwallet import HDWallet
from hdwallet.utils import generate_mnemonic

# Generate mnemonic
mnemonic = generate_mnemonic(language="english", strength=256)  # 24 words
print("SEED (BACK THIS UP SECURELY):")
print(mnemonic)

# Derive xpub for BTC
btc_wallet = HDWallet(cryptocurrency="Bitcoin")
btc_wallet.from_mnemonic(mnemonic)
btc_wallet.from_path("m/44'/0'/0'")
print("\nBTC xpub:", btc_wallet.xpublic_key())

# Derive xpub for ETH (covers USDT ERC-20 too)
eth_wallet = HDWallet(cryptocurrency="Ethereum")
eth_wallet.from_mnemonic(mnemonic)
eth_wallet.from_path("m/44'/60'/0'")
print("\nETH xpub:", eth_wallet.xpublic_key())
```

### 1.4 What to Do With the Output

| Item | Where to Store |
|---|---|
| 24-word mnemonic | Written on paper (stored in a safe place) + encrypted on USB drive |
| Encrypted seed file | USB drive (keep offline, never upload to VPS) |
| BTC xpub | Copy into VPS environment variables |
| ETH xpub | Copy into VPS environment variables |

**Never store the raw mnemonic or private keys on the VPS.**

### 1.5 Seed Backup Strategy

- USB Drive 1 — primary, kept with you
- USB Drive 2 — backup, stored in a different physical location
- Paper backup — written clearly, stored securely
- Encrypted digital copy — encrypted with a strong passphrase, optionally stored in cloud (since it's encrypted, this is acceptable)

---

## Part 2 — Django App Structure

### 2.1 New Django App

Create a new app called `wallets` inside your existing Django project.

```
apps/
  wallets/
    __init__.py
    models.py          # DepositAddress, DepositTransaction
    services.py        # HD address derivation, Tatum subscription
    views.py           # Webhook handler endpoint
    urls.py            # Webhook URL routing
    tasks.py           # Celery tasks for confirmation
    admin.py           # Admin panel registration
    serializers.py     # DRF serializers if needed
```

### 2.2 Environment Variables to Add

```env
# xpub keys (safe to store on VPS — cannot spend, only derive addresses)
BTC_XPUB=xpub6CUGRUo...
ETH_XPUB=xpub6CUGRUo...

# Tatum
TATUM_API_KEY=your_tatum_api_key
TATUM_WEBHOOK_SECRET=your_tatum_webhook_secret

# Internal signing secret (for the local signing script to authenticate)
INTERNAL_API_SECRET=a_long_random_secret_string
```

---

## Part 3 — Django Models

### 3.1 models.py

```python
from django.db import models
from django.conf import settings


class DepositAddress(models.Model):
    COIN_CHOICES = [
        ("BTC", "Bitcoin"),
        ("ETH", "Ethereum"),
        ("USDT_ERC20", "USDT (ERC-20)"),
        ("USDT_TRC20", "USDT (TRC-20)"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="deposit_addresses"
    )
    coin = models.CharField(max_length=20, choices=COIN_CHOICES)
    address = models.CharField(max_length=100, unique=True)
    derivation_index = models.PositiveIntegerField()
    tatum_subscription_id = models.CharField(max_length=100, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "coin")  # one address per user per coin

    def __str__(self):
        return f"{self.user} | {self.coin} | {self.address}"


class DepositTransaction(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("confirmed", "Confirmed"),
        ("failed", "Failed"),
    ]

    deposit_address = models.ForeignKey(
        DepositAddress,
        on_delete=models.PROTECT,
        related_name="transactions"
    )
    tx_hash = models.CharField(max_length=200, unique=True)
    amount = models.DecimalField(max_digits=36, decimal_places=18)
    coin = models.CharField(max_length=20)
    confirmations = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    raw_webhook_payload = models.JSONField()  # store full Tatum payload for debugging
    created_at = models.DateTimeField(auto_now_add=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.coin} | {self.amount} | {self.status}"


class WithdrawalRequest(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),           # user requested, waiting for signing
        ("signed", "Signed"),             # script has signed and broadcast
        ("confirmed", "Confirmed"),       # tx confirmed on-chain
        ("failed", "Failed"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="withdrawal_requests"
    )
    coin = models.CharField(max_length=20)
    amount = models.DecimalField(max_digits=36, decimal_places=18)
    destination_address = models.CharField(max_length=100)  # user's external wallet
    from_address = models.CharField(max_length=100)          # our deposit address holding funds
    derivation_index = models.PositiveIntegerField()         # so signing script knows which key
    tx_hash = models.CharField(max_length=200, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.user} | {self.coin} | {self.amount} | {self.status}"
```

---

## Part 4 — Address Derivation Service

### 4.1 services.py

```python
import os
import requests
from hdwallet import HDWallet
from django.db import transaction as db_transaction
from .models import DepositAddress

TATUM_API_KEY = os.environ.get("TATUM_API_KEY")
TATUM_BASE_URL = "https://api.tatum.io/v4"

BTC_XPUB = os.environ.get("BTC_XPUB")
ETH_XPUB = os.environ.get("ETH_XPUB")

REQUIRED_CONFIRMATIONS = {
    "BTC": 2,
    "ETH": 12,
    "USDT_ERC20": 12,
    "USDT_TRC20": 20,
}


def get_next_derivation_index(coin: str) -> int:
    """Get the next available derivation index for a coin."""
    last = DepositAddress.objects.filter(coin=coin).order_by("-derivation_index").first()
    return (last.derivation_index + 1) if last else 0


def derive_btc_address(index: int) -> str:
    """Derive a BTC deposit address at the given index from xpub."""
    wallet = HDWallet(cryptocurrency="Bitcoin")
    wallet.from_xpublic_key(BTC_XPUB)
    wallet.from_path(f"m/0/{index}")
    return wallet.p2pkh_address()


def derive_eth_address(index: int) -> str:
    """Derive an ETH/USDT ERC-20 deposit address at the given index from xpub."""
    wallet = HDWallet(cryptocurrency="Ethereum")
    wallet.from_xpublic_key(ETH_XPUB)
    wallet.from_path(f"m/0/{index}")
    return wallet.address()


def subscribe_address_to_tatum(address: str, coin: str, webhook_url: str) -> str:
    """Register an address with Tatum for incoming transaction monitoring."""
    chain_map = {
        "BTC": "BTC",
        "ETH": "ETH",
        "USDT_ERC20": "ETH",   # ERC-20 monitored on ETH chain
        "USDT_TRC20": "TRON",
    }
    chain = chain_map[coin]

    response = requests.post(
        f"{TATUM_BASE_URL}/subscription",
        headers={"x-api-key": TATUM_API_KEY},
        json={
            "type": "INCOMING_NATIVE_TX" if coin in ["BTC", "ETH"] else "INCOMING_FUNGIBLE_TX",
            "attr": {
                "address": address,
                "chain": chain,
                "url": webhook_url,
            }
        }
    )
    response.raise_for_status()
    return response.json().get("id")


def get_or_create_deposit_address(user, coin: str) -> DepositAddress:
    """
    Get existing deposit address for user+coin, or generate a new one.
    This is what gets called when user opens the deposit screen.
    """
    existing = DepositAddress.objects.filter(user=user, coin=coin).first()
    if existing:
        return existing

    with db_transaction.atomic():
        index = get_next_derivation_index(coin)

        if coin == "BTC":
            address = derive_btc_address(index)
        elif coin in ["ETH", "USDT_ERC20"]:
            # ETH and USDT ERC-20 share the same address
            eth_record = DepositAddress.objects.filter(
                user=user, coin="ETH"
            ).first()
            if eth_record:
                address = eth_record.address
                index = eth_record.derivation_index
            else:
                address = derive_eth_address(index)
        else:
            raise ValueError(f"Unsupported coin: {coin}")

        deposit_address = DepositAddress.objects.create(
            user=user,
            coin=coin,
            address=address,
            derivation_index=index,
        )

        # Subscribe to Tatum monitoring
        webhook_url = f"https://yourbackend.com/api/webhooks/deposit/"
        subscription_id = subscribe_address_to_tatum(address, coin, webhook_url)
        deposit_address.tatum_subscription_id = subscription_id
        deposit_address.save()

        return deposit_address
```

---

## Part 5 — Webhook Handler

### 5.1 views.py

```python
import hmac
import hashlib
import os
import json
from decimal import Decimal
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.utils import timezone
from .models import DepositAddress, DepositTransaction
from .tasks import process_confirmed_deposit

TATUM_WEBHOOK_SECRET = os.environ.get("TATUM_WEBHOOK_SECRET")
REQUIRED_CONFIRMATIONS = {
    "BTC": 2,
    "ETH": 12,
    "USDT_ERC20": 12,
    "USDT_TRC20": 20,
}


def verify_tatum_signature(request) -> bool:
    """Verify the webhook came from Tatum using HMAC signature."""
    signature = request.headers.get("x-payload-hash")
    if not signature:
        return False
    expected = hmac.new(
        TATUM_WEBHOOK_SECRET.encode(),
        request.body,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(signature, expected)


@csrf_exempt
@require_POST
def deposit_webhook(request):
    """
    Tatum calls this endpoint when crypto arrives at any monitored address.
    """
    # 1. Verify signature
    if not verify_tatum_signature(request):
        return JsonResponse({"error": "Invalid signature"}, status=401)

    # 2. Parse payload
    payload = json.loads(request.body)

    address = payload.get("address")
    tx_hash = payload.get("txId") or payload.get("hash")
    amount = Decimal(str(payload.get("amount", "0")))
    coin = payload.get("asset", "").upper()
    confirmations = payload.get("confirmations", 0)

    # 3. Look up which user owns this address
    try:
        deposit_address = DepositAddress.objects.select_related("user").get(
            address=address
        )
    except DepositAddress.DoesNotExist:
        # Address not in our system — ignore
        return JsonResponse({"status": "ignored"}, status=200)

    # 4. Prevent duplicate processing
    if DepositTransaction.objects.filter(tx_hash=tx_hash).exists():
        return JsonResponse({"status": "already_processed"}, status=200)

    # 5. Create pending transaction record
    tx = DepositTransaction.objects.create(
        deposit_address=deposit_address,
        tx_hash=tx_hash,
        amount=amount,
        coin=coin,
        confirmations=confirmations,
        status="pending",
        raw_webhook_payload=payload,
    )

    # 6. Check if already has enough confirmations
    required = REQUIRED_CONFIRMATIONS.get(coin, 12)
    if confirmations >= required:
        process_confirmed_deposit.delay(tx.id)
    # else: Tatum will fire again as confirmations increase

    # 7. Always return 200 quickly — Tatum will retry on non-2xx
    return JsonResponse({"status": "received"}, status=200)


# --- Internal endpoints for signing script ---

from django.views.decorators.http import require_GET
from .models import WithdrawalRequest

INTERNAL_API_SECRET = os.environ.get("INTERNAL_API_SECRET")


def verify_internal_secret(request) -> bool:
    return request.headers.get("X-Internal-Key") == INTERNAL_API_SECRET


@csrf_exempt
@require_GET
def pending_withdrawals(request):
    """Signing script calls this to fetch withdrawals that need to be signed."""
    if not verify_internal_secret(request):
        return JsonResponse({"error": "Unauthorized"}, status=401)

    withdrawals = WithdrawalRequest.objects.filter(status="pending").values(
        "id", "coin", "amount", "destination_address",
        "from_address", "derivation_index"
    )
    return JsonResponse({"withdrawals": list(withdrawals)})


@csrf_exempt
@require_POST
def confirm_withdrawal(request):
    """Signing script calls this after broadcasting a transaction."""
    if not verify_internal_secret(request):
        return JsonResponse({"error": "Unauthorized"}, status=401)

    data = json.loads(request.body)
    withdrawal_id = data.get("withdrawal_id")
    tx_hash = data.get("tx_hash")

    try:
        withdrawal = WithdrawalRequest.objects.get(id=withdrawal_id)
        withdrawal.tx_hash = tx_hash
        withdrawal.status = "signed"
        withdrawal.processed_at = timezone.now()
        withdrawal.save()
        return JsonResponse({"status": "ok"})
    except WithdrawalRequest.DoesNotExist:
        return JsonResponse({"error": "Not found"}, status=404)
```

### 5.2 urls.py

```python
from django.urls import path
from . import views

urlpatterns = [
    path("webhooks/deposit/", views.deposit_webhook, name="deposit_webhook"),
    path("internal/pending-withdrawals/", views.pending_withdrawals, name="pending_withdrawals"),
    path("internal/confirm-withdrawal/", views.confirm_withdrawal, name="confirm_withdrawal"),
]
```

---

## Part 6 — Celery Tasks

### 6.1 tasks.py

```python
from celery import shared_task
from django.utils import timezone
from decimal import Decimal
from .models import DepositTransaction

# Import your existing internal ledger credit function
# from apps.ledger.services import credit_user_balance


@shared_task
def process_confirmed_deposit(transaction_id: int):
    """
    Called when a deposit has enough confirmations.
    Credits the user's internal ledger.
    """
    try:
        tx = DepositTransaction.objects.select_related(
            "deposit_address__user"
        ).get(id=transaction_id)

        if tx.status == "confirmed":
            return  # Already processed, idempotent

        user = tx.deposit_address.user
        amount = tx.amount
        coin = tx.coin

        # Credit the internal ledger
        # credit_user_balance(user=user, coin=coin, amount=amount, tx_hash=tx.tx_hash)

        # Mark as confirmed
        tx.status = "confirmed"
        tx.confirmed_at = timezone.now()
        tx.save()

        # TODO: Send user a notification (email / in-app)

    except DepositTransaction.DoesNotExist:
        pass
```

---

## Part 7 — Local Signing Script (Runs on Your Laptop)

### 7.1 sign_and_broadcast.py

This script lives **only on your laptop**. Never upload it to the VPS with the seed included.

```python
#!/usr/bin/env python3
"""
Swift Trade — Local Signing Script
Run this on your laptop when you need to process withdrawal requests.
Never run this on the VPS.
"""

import os
import requests
from decimal import Decimal
from hdwallet import HDWallet
from web3 import Web3
from eth_account import Account

# --- Configuration ---
MNEMONIC = "your twenty four word seed phrase goes here"  # or load from encrypted file
BACKEND_URL = "https://yourbackend.com/api"
INTERNAL_SECRET = "your_internal_api_secret"
TATUM_API_KEY = "your_tatum_api_key"

HEADERS = {"X-Internal-Key": INTERNAL_SECRET}


def derive_btc_private_key(index: int) -> str:
    wallet = HDWallet(cryptocurrency="Bitcoin")
    wallet.from_mnemonic(MNEMONIC)
    wallet.from_path(f"m/44'/0'/0'/0/{index}")
    return wallet.private_key()


def derive_eth_private_key(index: int) -> str:
    wallet = HDWallet(cryptocurrency="Ethereum")
    wallet.from_mnemonic(MNEMONIC)
    wallet.from_path(f"m/44'/60'/0'/0/{index}")
    return wallet.private_key()


def broadcast_btc_transaction(private_key: str, to_address: str, amount_btc: Decimal) -> str:
    """Sign and broadcast a BTC transaction via Tatum."""
    response = requests.post(
        f"https://api.tatum.io/v3/bitcoin/transaction",
        headers={"x-api-key": TATUM_API_KEY},
        json={
            "fromPrivateKey": private_key,
            "to": [{"address": to_address, "value": float(amount_btc)}],
            "fee": "0.00005",
            "changeAddress": to_address,  # send change back (or to master hot wallet)
        }
    )
    response.raise_for_status()
    return response.json()["txId"]


def broadcast_eth_transaction(private_key: str, to_address: str, amount_eth: Decimal) -> str:
    """Sign and broadcast an ETH transaction via Tatum."""
    response = requests.post(
        f"https://api.tatum.io/v3/ethereum/transaction",
        headers={"x-api-key": TATUM_API_KEY},
        json={
            "fromPrivateKey": private_key,
            "to": to_address,
            "amount": str(amount_eth),
        }
    )
    response.raise_for_status()
    return response.json()["txId"]


def process_withdrawals():
    # 1. Fetch pending withdrawals from backend
    response = requests.get(f"{BACKEND_URL}/internal/pending-withdrawals/", headers=HEADERS)
    response.raise_for_status()
    withdrawals = response.json().get("withdrawals", [])

    if not withdrawals:
        print("No pending withdrawals.")
        return

    print(f"Found {len(withdrawals)} pending withdrawal(s).")

    for w in withdrawals:
        print(f"\nProcessing: {w['amount']} {w['coin']} → {w['destination_address']}")

        try:
            index = w["derivation_index"]
            coin = w["coin"]
            to_address = w["destination_address"]
            amount = Decimal(str(w["amount"]))

            # Sign and broadcast
            if coin == "BTC":
                private_key = derive_btc_private_key(index)
                tx_hash = broadcast_btc_transaction(private_key, to_address, amount)
            elif coin in ["ETH", "USDT_ERC20"]:
                private_key = derive_eth_private_key(index)
                tx_hash = broadcast_eth_transaction(private_key, to_address, amount)
            else:
                print(f"  ⚠️  Unsupported coin: {coin}, skipping.")
                continue

            # Report back to backend
            confirm_response = requests.post(
                f"{BACKEND_URL}/internal/confirm-withdrawal/",
                headers=HEADERS,
                json={"withdrawal_id": w["id"], "tx_hash": tx_hash}
            )
            confirm_response.raise_for_status()
            print(f"  ✅ Done. TX Hash: {tx_hash}")

        except Exception as e:
            print(f"  ❌ Failed: {e}")

    print("\nAll done.")


if __name__ == "__main__":
    process_withdrawals()
```

---

## Part 8 — API Endpoints for Frontend

These are the endpoints your React frontend will call.

```
GET  /api/wallets/deposit-address/?coin=BTC
     → returns the user's BTC deposit address (creates one if first time)
     → response: { address: "bc1q...", coin: "BTC", qr_code_url: "..." }

GET  /api/wallets/deposit-address/?coin=ETH
     → returns ETH deposit address

GET  /api/wallets/deposit-address/?coin=USDT_ERC20
     → returns same ETH address (shared)

GET  /api/wallets/transactions/
     → returns user's deposit transaction history
     → response: [{ tx_hash, amount, coin, status, created_at }]

POST /api/wallets/withdraw/
     → user requests a crypto withdrawal
     → body: { coin, amount, destination_address }
     → creates a WithdrawalRequest with status "pending"
     → response: { id, status: "pending", message: "Processing within 24 hours" }
```

---

## Part 9 — Tatum Account Setup

1. Go to tatum.io
2. Sign up with email and password (no KYC required)
3. Get your API key from the dashboard
4. Add API key to your VPS environment variables
5. Set up a webhook secret in the Tatum dashboard
6. Add webhook secret to your VPS environment variables

That's it. No business verification, no document upload.

---

## Part 10 — Python Libraries Required

```txt
# requirements.txt additions

hdwallet==2.2.1          # HD wallet derivation for BTC, ETH
web3==6.15.1             # Ethereum interaction
eth-account==0.11.0      # ETH transaction signing
requests==2.31.0         # HTTP calls to Tatum
tronpy==0.4.0            # TRON/USDT TRC-20 (if needed later)
cryptography==42.0.0     # For encrypting seed file locally
```

---

## Part 11 — Security Checklist

### VPS
- [ ] Seed and mnemonic never stored on VPS
- [ ] Only xpub keys stored (in environment variables, not in code)
- [ ] Internal endpoints (`/internal/`) not exposed to public — firewall rule or nginx block
- [ ] Tatum webhook signature verified on every request
- [ ] All webhook processing is idempotent (duplicate tx_hash = ignored)
- [ ] Deposit transactions only credited once (unique constraint on tx_hash)

### Seed / Local Machine
- [ ] Mnemonic written on paper and stored securely
- [ ] Encrypted backup on USB drive
- [ ] Second USB backup in different location
- [ ] Signing script never committed to Git
- [ ] Mnemonic never typed into any online tool or website

### Django
- [ ] Internal API endpoints require `X-Internal-Key` header
- [ ] INTERNAL_API_SECRET is a long random string (32+ chars)
- [ ] Webhook endpoint returns 200 immediately, processes async via Celery
- [ ] All ledger credits happen inside atomic database transactions

---

## Part 12 — Implementation Order

Implement in this exact order:

1. **Models** — DepositAddress, DepositTransaction, WithdrawalRequest
2. **Migrations** — run makemigrations and migrate
3. **Services** — address derivation from xpub (no seed needed on server)
4. **Tatum signup** — get API key, set up webhook secret
5. **Webhook endpoint** — deposit_webhook view + URL routing
6. **Celery task** — process_confirmed_deposit
7. **Internal endpoints** — pending_withdrawals + confirm_withdrawal
8. **Deposit address API endpoint** — for frontend to call
9. **Test on testnet** — use BTC testnet and ETH Sepolia, get Tatum testnet key
10. **Local signing script** — test withdrawal flow end to end
11. **Frontend integration** — deposit screen shows address + QR code
12. **Go live on mainnet** — swap testnet xpub for mainnet xpub, update Tatum to mainnet

---

## Part 13 — Daily Operator Workflow

```
Morning (or whenever you choose):

1. Open your laptop
2. Plug in USB drive (if seed is stored there)
3. Run: python sign_and_broadcast.py
4. Script fetches all pending withdrawals from your backend
5. Signs and broadcasts each one
6. Reports tx hashes back to your backend
7. Users see their withdrawal status updated to "signed"
8. Put seed/USB away

That's it.
```

Celery + Tatum handle everything else automatically (deposits, confirmations, ledger credits). You only need to run the signing script for outbound withdrawals.

---

## Notes for the Agent Implementing This

- The project is called **Swift Trade** — a custodial crypto-to-NGN exchange targeting the Nigerian market
- Backend is **Django + Django REST Framework + Django Ninja** (use whichever pattern fits the existing codebase)
- Database is **PostgreSQL**
- Task queue is **Celery + RabbitMQ**
- The existing project already has a CustomUser model with email as username
- The existing project already has an internal ledger — integrate `credit_user_balance()` from it rather than creating a new one
- Supported coins for now: **BTC, ETH, USDT (ERC-20)**
- USDT TRC-20 can be added later — scaffold is included but not a priority
- Use `python-decouple` or `django-environ` for environment variables, consistent with existing project setup
- All monetary amounts use `DecimalField` with `max_digits=36, decimal_places=18` — never floats
- Follow the existing project's views → services → models architecture pattern
