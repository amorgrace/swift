# Swift Trade — Tatum + HD Wallet Deposit System
## Revised Implementation Plan (Post-Quidax Pivot)

---

## What This Is

Swift Trade is a **crypto liquidation platform**. Users send crypto in, get NGN out. Paystack handles bank withdrawals. The platform owns the keys to all deposit addresses.

The only thing Quidax was doing that we now need to replace:
1. **Generating deposit addresses** per user per asset/network
2. **Detecting when crypto arrives** and firing a webhook

That is it. Everything else already works — NGN wallet, rates, Paystack withdrawals, KYC, emails, Telegram notifications — all of it stays **completely unchanged**.

---

## What Already Exists (Do Not Touch)

### NGN Wallet (wallets/models.py)
- NGNWallet — one per user, stores NGN balance
- NGNWallet.credit() — atomic, idempotent balance credit
- NGNWallet.debit() — atomic, balance debit
- BankAccount — users linked bank account for Paystack withdrawals
- DepositAddress — already exists, linked to NGNWallet, stores asset + network + address

### Deposit and Withdrawal Transactions (transactions/models.py)
- Deposit — records every crypto-to-NGN conversion. Has quidax_reference (unique, used for idempotency)
- Withdrawal — records every NGN bank transfer
- Transaction — unified log for user history

### Deposit Processing (transactions/services.py -> DepositService.process_deposit_webhook)
- Already fully built: receives webhook payload, calculates NGN, credits wallet, logs, sends email and Telegram
- Currently expects Quidax payload shape — only this needs adapting

### Rates (rates/services.py)
- RateService.calculate_ngn_amount(asset, crypto_amount) — fully working
- Pulls live rates from CoinGecko, applies margin, returns NGN amount
- SystemSettings lets admin control margin % or set a fixed NGN/USD rate

### Paystack Withdrawals (wallets/services.py -> PaystackService)
- Full NGN transfer flow: debit -> Paystack transfer -> webhook -> success/failure
- Untouched

### Everything Else
- KYC verification
- Emails and Telegram notifications
- Admin endpoints
- Authentication

---

## What We Are Replacing

### Quidax Sub-Account System (Remove / Replace)
Currently in wallets/services.py:
- QuidaxService class — generates sub-accounts and deposit addresses via Quidax API
- WalletService.create_wallet_for_user() — calls Quidax to create sub-account
- WalletService.get_deposit_addresses() — calls Quidax to generate addresses

Currently in wallets/models.py:
- NGNWallet.quidax_user_id — stores Quidax sub-account ID (will be left in place, just blank for new users)

Currently in transactions/models.py:
- Deposit.quidax_reference — stores Quidax transaction ID for idempotency (repurposed to store Tatum txId)

---

## Architecture: What Replaces Quidax

HD Wallet (xpub keys in Vercel env vars — no seed on server)
  - Derives one unique address per user per asset per network
  - Same DepositAddress model, different generation method

Tatum (free tier — no KYC, just sign up)
  - Watches deposit addresses for incoming transactions
  - Fires webhook to Django when crypto arrives
  - Retries webhook as block confirmations increase

Django Webhook Handler (new view)
  - Verifies Tatum HMAC signature
  - Looks up which user owns the address
  - Calls existing RateService.calculate_ngn_amount()
  - Calls existing DepositService logic (adapted for Tatum payload)
  - Everything else unchanged

No Celery. No VPS. Runs on Vercel. Webhook is synchronous — Tatum retries if no 200.

---

## Part 1 — HD Wallet Setup (Done Once, Offline on Laptop)

### 1.1 What to Generate

Run this locally on your laptop. Never run on the server.

    # generate_wallet.py — run ONCE on laptop
    from hdwallet import HDWallet
    from hdwallet.utils import generate_mnemonic

    mnemonic = generate_mnemonic(language="english", strength=256)
    print("MNEMONIC:", mnemonic)

    btc_wallet = HDWallet(cryptocurrency="Bitcoin")
    btc_wallet.from_mnemonic(mnemonic)
    btc_wallet.from_path("m/44'/0'/0'")
    print("BTC xpub:", btc_wallet.xpublic_key())

    eth_wallet = HDWallet(cryptocurrency="Ethereum")
    eth_wallet.from_mnemonic(mnemonic)
    eth_wallet.from_path("m/44'/60'/0'")
    print("ETH xpub:", eth_wallet.xpublic_key())

### 1.2 What to Store Where

| Item | Where |
|---|---|
| 24-word mnemonic | Paper backup (safe) + encrypted USB |
| BTC xpub | Vercel env var: BTC_XPUB |
| ETH xpub | Vercel env var: ETH_XPUB |

The xpub is read-only — it can only derive addresses, never spend funds.

### 1.3 Supported Coins Phase 1

| Asset | Network | Notes |
|---|---|---|
| BTC | bitcoin | BIP44 derivation from BTC xpub |
| ETH | erc20 | BIP44 derivation from ETH xpub |
| USDT | erc20 | Same ETH address (ERC-20 shares address) |
| USDC | erc20 | Same ETH address |
| USDT TRC-20 | trc20 | Deferred |
| SOL | solana | Deferred |
| BNB | bep20 | Deferred |

---

## Part 2 — Model Changes

### 2.1 DepositAddress (wallets/models.py)

Add two fields via migration:

    derivation_index = models.PositiveIntegerField(null=True, blank=True)
    tatum_subscription_id = models.CharField(max_length=100, blank=True)

Everything else in the model stays the same.

### 2.2 Deposit.quidax_reference (transactions/models.py)

No rename needed. This field is just a unique string. We will store the Tatum txId here. Field name stays as-is to avoid a migration that gains nothing.

### 2.3 NGNWallet.quidax_user_id

Leave in place. Will be blank for new users going forward. No migration needed.

---

## Part 3 — New Environment Variables

Add to Vercel and local .env:

    BTC_XPUB=xpub6...
    ETH_XPUB=xpub6...
    TATUM_API_KEY=your_tatum_key
    TATUM_WEBHOOK_SECRET=your_webhook_secret
    BACKEND_URL=https://your-vercel-domain.vercel.app

---

## Part 4 — New File: wallets/tatum.py

    import os, hmac, hashlib, requests
    from hdwallet import HDWallet

    TATUM_API_KEY = os.environ.get("TATUM_API_KEY")
    TATUM_WEBHOOK_SECRET = os.environ.get("TATUM_WEBHOOK_SECRET")
    BTC_XPUB = os.environ.get("BTC_XPUB")
    ETH_XPUB = os.environ.get("ETH_XPUB")
    TATUM_BASE_URL = "https://api.tatum.io/v4"

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
        if network == "bitcoin":
            wallet = HDWallet(cryptocurrency="Bitcoin")
            wallet.from_xpublic_key(BTC_XPUB)
            wallet.from_path(f"m/0/{index}")
            return wallet.p2pkh_address()
        elif network in ("erc20", "bep20"):
            wallet = HDWallet(cryptocurrency="Ethereum")
            wallet.from_xpublic_key(ETH_XPUB)
            wallet.from_path(f"m/0/{index}")
            return wallet.address()
        else:
            raise ValueError(f"Unsupported network: {network}")

    def subscribe_to_tatum(address: str, network: str, webhook_url: str) -> str:
        chain_map = {"bitcoin": "BTC", "erc20": "ETH"}
        chain = chain_map.get(network)
        if not chain:
            raise ValueError(f"No Tatum chain for network: {network}")
        r = requests.post(
            f"{TATUM_BASE_URL}/subscription",
            headers={"x-api-key": TATUM_API_KEY},
            json={"type": "INCOMING_NATIVE_TX", "attr": {"address": address, "chain": chain, "url": webhook_url}},
            timeout=10,
        )
        r.raise_for_status()
        return r.json().get("id", "")

    def verify_tatum_signature(request) -> bool:
        if not TATUM_WEBHOOK_SECRET:
            return True
        signature = request.headers.get("x-payload-hash", "")
        expected = hmac.new(
            TATUM_WEBHOOK_SECRET.encode(), request.body, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(signature, expected)

---

## Part 5 — Updated WalletService (wallets/services.py)

Replace QuidaxService calls in WalletService:

create_wallet_for_user — remove Quidax sub-account creation. Just do get_or_create for NGNWallet:

    wallet, _ = NGNWallet.objects.get_or_create(user=user)
    return wallet

get_deposit_addresses — replace with get_or_create_deposit_address per asset/network:

    def get_or_create_deposit_address(user, asset, network):
        # ETH and all ERC-20 tokens share the same derived address
        lookup_asset = "eth" if network == "erc20" else asset

        wallet = NGNWallet.objects.get(user=user)
        existing = DepositAddress.objects.filter(wallet=wallet, asset=lookup_asset, network=network).first()
        if existing:
            return existing

        index = get_next_derivation_index(lookup_asset, network)
        address = derive_address(lookup_asset, network, index)

        deposit_address = DepositAddress.objects.create(
            wallet=wallet, asset=lookup_asset, network=network,
            address=address, derivation_index=index,
        )

        webhook_url = f"{settings.BACKEND_URL}/api/webhooks/tatum-deposit/"
        try:
            sub_id = subscribe_to_tatum(address, network, webhook_url)
            deposit_address.tatum_subscription_id = sub_id
            deposit_address.save(update_fields=["tatum_subscription_id"])
        except Exception as e:
            logger.error(f"Tatum subscription failed for {address}: {e}")
            # Address is still valid — subscription can be retried manually

        return deposit_address

---

## Part 6 — New Webhook Endpoint (transactions/views.py)

    @router.post("/webhooks/tatum-deposit/", auth=None)
    def tatum_deposit_webhook(request):
        from wallets.tatum import verify_tatum_signature
        if not verify_tatum_signature(request):
            raise HttpError(401, "Invalid signature")
        import json
        payload = json.loads(request.body)
        DepositService.process_tatum_deposit(payload)
        return {"status": "ok"}

---

## Part 7 — New DepositService Method (transactions/services.py)

Add process_tatum_deposit() alongside existing process_deposit_webhook():

    Tatum payload shape:
    {
      "address": "bc1q...",
      "txId": "abc123...",
      "amount": "0.05",
      "asset": "BTC",
      "confirmations": 2
    }

    Logic:
    1. Extract txId, address, amount, confirmations
    2. Check idempotency: Deposit.objects.filter(quidax_reference=txId).exists()
    3. Check confirmations >= REQUIRED (BTC:2, ETH/USDT:12)
       - If not enough confirmations: return True (Tatum will retry)
    4. Look up DepositAddress by address -> get wallet -> get user
    5. Call RateService.calculate_ngn_amount(asset, crypto_amount)
    6. Inside transaction.atomic():
       - Create Deposit record (quidax_reference = txId)
       - wallet.credit(ngn_amount)
       - Create Transaction log
    7. Send email and Telegram notification

    REQUIRED_CONFIRMATIONS = {"btc": 2, "eth": 12, "usdt": 12, "usdc": 12}

---

## Part 8 — What We Are NOT Building

| Item | Status |
|---|---|
| Crypto withdrawals | Not needed — users only withdraw NGN via Paystack |
| WithdrawalRequest model for crypto | Not needed |
| Signing script | Not needed |
| Celery / task queues | Not needed — webhook is synchronous |
| VPS | Not needed — staying on Vercel |
| USDT TRC-20 deposits | Deferred |
| SOL, BNB deposits | Deferred |

---

## Part 9 — Tatum Account Setup

1. Go to tatum.io
2. Sign up (no KYC, just email and password)
3. Get API key from dashboard
4. Create webhook secret
5. Add API key and webhook secret to Vercel env vars
6. Use testnet key first, swap to mainnet when ready

---

## Part 10 — New Dependencies

    # Add to requirements.txt
    hdwallet==2.2.1

Everything else (requests, httpx, etc.) already installed.

---

## Part 11 — Implementation Order

1. Generate HD wallet offline — run generate_wallet.py on laptop, get xpubs
2. Add env vars — BTC_XPUB, ETH_XPUB, TATUM_API_KEY, TATUM_WEBHOOK_SECRET, BACKEND_URL to Vercel
3. Write migration — add derivation_index and tatum_subscription_id to DepositAddress
4. Create wallets/tatum.py — HD derivation + Tatum subscription + signature verification
5. Update WalletService — remove Quidax calls, add HD + Tatum path
6. Add DepositService.process_tatum_deposit() — Tatum payload handler
7. Add Tatum webhook URL — new endpoint
8. Register webhook URL in engine/api.py or engine/urls.py
9. Update get_deposit_addresses view — call new service method
10. Test on testnet — BTC testnet + ETH Sepolia, Tatum testnet key
11. Go live — swap xpubs and Tatum key to mainnet

---

## Part 12 — Security Checklist

- [ ] Seed mnemonic never stored on server or committed to git
- [ ] Only xpub keys in environment variables
- [ ] Tatum webhook signature verified on every request
- [ ] Deposit processing is idempotent (tx_hash unique via quidax_reference field)
- [ ] NGN credit happens inside transaction.atomic()
- [ ] BACKEND_URL env var is set correctly per environment (testnet vs mainnet)
- [ ] Webhook endpoint has no auth but signature verification replaces it

---

## Checkpoint

Commit saved before this pivot: 28e356a82a6c0226736f903f28ea8e63b49fc161
