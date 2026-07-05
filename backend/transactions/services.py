import logging
from decimal import Decimal
import uuid
from datetime import datetime

from django.conf import settings
from django.db import transaction

from rates.services import RateService
from wallets.models import NGNWallet, BankAccount
from wallets.services import PaystackService
from kyc.models import KYCVerification, KYCStatus
from notifications.tasks import send_email_task, send_telegram_task, create_notification_task
from .models import (
    Deposit,
    Withdrawal,
    Transaction,
    DepositStatus,
    WithdrawalStatus,
    TransactionType,
    generate_transaction_id,
)

logger = logging.getLogger(__name__)


class DepositService:
    """Handles processing of incoming crypto deposits via webhook."""

    # process_deposit_webhook (Quidax) removed.

    @staticmethod
    def process_tatum_deposit(payload: dict) -> bool:
        """
        Process a Tatum incoming transaction webhook.
        Tatum payload shape:
          {
            "address": "bc1q...",
            "txId": "abc123...",
            "amount": "0.05",
            "asset": "BTC",
            "confirmations": 2,
            "blockNumber": 123456
          }
        """
        from wallets.models import DepositAddress

        tx_hash = payload.get("txId") or payload.get("hash")
        address = payload.get("address")
        amount_str = payload.get("amount", "0")
        confirmations = int(payload.get("confirmations", 0))
        raw_asset = (payload.get("asset") or "").lower()

        if not tx_hash or not address:
            logger.error("Tatum webhook missing txId or address")
            return False

        # Idempotency — use tx_hash as the unique reference
        if Deposit.objects.filter(quidax_reference=tx_hash).exists():
            logger.info(f"Deposit {tx_hash} already processed.")
            return True

        # Map Tatum asset to our AssetChoices
        asset_map = {"btc": "btc", "eth": "eth", "usdt": "usdt", "usdc": "usdc"}
        asset = asset_map.get(raw_asset)
        if not asset:
            logger.warning(f"Unknown asset in Tatum webhook: {raw_asset}")
            return False

        # Minimum confirmations check
        REQUIRED_CONFIRMATIONS = {"btc": 2, "eth": 12, "usdt": 12, "usdc": 12}
        required = REQUIRED_CONFIRMATIONS.get(asset, 12)
        if confirmations < required:
            # Tatum will fire again when confirmations increase
            logger.info(f"Tatum deposit {tx_hash} needs more confirmations ({confirmations}/{required})")
            return True  # return True so Tatum gets 200 and retries

        # Look up which user owns this address
        try:
            deposit_addr = DepositAddress.objects.select_related("wallet__user").get(address=address)
        except DepositAddress.DoesNotExist:
            logger.warning(f"No DepositAddress found for address {address}")
            return False

        wallet = deposit_addr.wallet
        network = deposit_addr.network

        try:
            crypto_amount = Decimal(str(amount_str))
        except Exception:
            logger.error(f"Invalid amount in Tatum payload: {amount_str}")
            return False

        with transaction.atomic():
            rate_info = RateService.calculate_ngn_amount(asset, crypto_amount)
            ngn_amount = rate_info["ngn_amount"]
            user_rate = rate_info["user_rate"]
            margin = rate_info["margin_percentage"]
            ngn_usd_rate = rate_info.get("ngn_usd_rate")

            deposit = Deposit.objects.create(
                wallet=wallet,
                asset=asset,
                network=network,
                crypto_amount=crypto_amount,
                rate_applied=user_rate,
                margin_applied=margin,
                ngn_usd_rate=ngn_usd_rate,
                ngn_amount=ngn_amount,
                quidax_reference=tx_hash,     # repurposing this field for tx_hash
                status=DepositStatus.CONVERTED,
            )

            wallet.credit(ngn_amount)

            description = f"Received {crypto_amount} {asset.upper()} → ₦{ngn_amount:,.2f}"
            Transaction.objects.create(
                wallet=wallet,
                type=TransactionType.DEPOSIT,
                amount=ngn_amount,
                description=description,
                status=DepositStatus.CONVERTED,
                related_deposit=deposit,
            )

        # --- Background notifications (non-blocking) ---
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

        # Email
        send_email_task.delay(
            to_email=wallet.user.email,
            to_name=wallet.user.full_name,
            subject=f"SwiftTrade \u2013 Deposit Received ({asset.upper()})",
            template_name="emails/deposit_received.html",
            context={
                "full_name": wallet.user.full_name,
                "asset": asset.upper(),
                "crypto_amount": str(crypto_amount),
                "ngn_amount": f"{ngn_amount:,.2f}",
                "timestamp": timestamp,
            },
        )

        # In-app notification
        create_notification_task.delay(
            user_id=wallet.user.id,
            notification_type='trade',
            title='Deposit Received & Converted',
            body=f'Your deposit of {crypto_amount} {asset.upper()} was successfully converted to \u20a6{ngn_amount:,.2f}.',
        )

        # Telegram admin alert
        telegram_msg = (
            "\U0001f4e5 <b>NEW CRYPTO DEPOSIT</b>\n"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            f"\U0001f464 <b>User:</b> {wallet.user.full_name} ({wallet.user.email})\n"
            f"\U0001f4b0 <b>Crypto:</b> {crypto_amount} {asset.upper()}\n"
            f"\U0001f4b5 <b>NGN Credited:</b> \u20a6{ngn_amount:,.2f}\n"
            f"\U0001f4ca <b>Rate Used:</b> \u20a6{user_rate:,.2f}/{asset.upper()}\n"
            f"\U0001f517 <b>Swift Ref:</b> <code>{tx_hash}</code>\n"
            f"\u23f0 {timestamp}"
        )
        send_telegram_task.delay(telegram_msg)

        logger.info(f"Tatum deposit {tx_hash} processed for wallet {wallet.id}")
        return True


class WithdrawalService:
    """Handles NGN withdrawals to bank accounts."""

    @staticmethod
    def get_min_withdrawal_amount() -> Decimal:
        return Decimal(str(getattr(settings, 'MIN_WITHDRAWAL_NGN', 1000)))

    @staticmethod
    def request_withdrawal(user, bank_account_id: int, amount: Decimal, pin: str) -> dict:
        """
        Request a withdrawal from NGN wallet to a linked bank account.
        Validates PIN, checks balance, debits wallet, creates withdrawal, initiates Paystack transfer.
        """
        min_amount = WithdrawalService.get_min_withdrawal_amount()
        if amount < min_amount:
            raise ValueError(f"Minimum withdrawal amount is ₦{min_amount:,.2f}")

        try:
            wallet = NGNWallet.objects.get(user=user)
        except NGNWallet.DoesNotExist:
            raise ValueError("Wallet not found")

        # Verify PIN
        if not wallet.verify_transaction_pin(pin):
            raise ValueError("Invalid transaction PIN")

        try:
            bank_account = BankAccount.objects.get(id=bank_account_id, user=user)
        except BankAccount.DoesNotExist:
            raise ValueError("Bank account not found")

        try:
            kyc = KYCVerification.objects.get(user=user)
            if kyc.status != KYCStatus.VERIFIED:
                raise ValueError(f"KYC status is {kyc.status}. Verified KYC is required for withdrawals.")
        except KYCVerification.DoesNotExist:
            raise ValueError("KYC not submitted. Please submit KYC documents to enable withdrawals.")

        # (Paystack recipient code check removed)

        # Calculate amounts
        fee = Decimal('100.00')
        if amount <= fee:
            raise ValueError(f"Withdrawal amount must be greater than the fee of ₦{fee:,.2f}")
        
        amount_to_paystack = amount - fee

        with transaction.atomic():
            # 1. Debit wallet (will raise ValueError if insufficient balance)
            wallet.debit(amount)

            # 2. Create Withdrawal record
            withdrawal_ref = f"WD-{uuid.uuid4().hex[:12].upper()}"
            withdrawal = Withdrawal.objects.create(
                wallet=wallet,
                bank_account=bank_account,
                amount=amount,
                fee=fee,
                paystack_reference=withdrawal_ref,
                status=WithdrawalStatus.PENDING,
            )

            # 3. Create Transaction log
            description = f"Withdrawal to {bank_account.bank_name} - {bank_account.account_number}"
            txn_log = Transaction.objects.create(
                wallet=wallet,
                type=TransactionType.WITHDRAWAL,
                amount=amount,
                reference=generate_transaction_id(),
                description=description,
                status=WithdrawalStatus.PENDING,
                related_withdrawal=withdrawal,
            )

        # --- Background notifications (non-blocking) ---
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

        # Email user
        send_email_task.delay(
            to_email=user.email,
            to_name=user.full_name,
            subject="SwiftTrade \u2013 Withdrawal Request Received",
            template_name="emails/withdrawal_initiated.html",
            context={
                "full_name": user.full_name,
                "amount": f"{amount:,.2f}",
                "bank_name": bank_account.bank_name,
                "account_number": bank_account.account_number,
                "timestamp": timestamp,
            },
        )

        # Email each admin (each as a separate task — parallelised by workers)
        from authenticator.models import User as UserModel
        for admin in UserModel.objects.filter(is_staff=True).values('email', 'full_name'):
            send_email_task.delay(
                to_email=admin['email'],
                to_name=admin['full_name'],
                subject="SwiftTrade Admin \u2013 New Withdrawal Request",
                template_name="emails/admin_withdrawal_pending.html",
                context={
                    "admin_name": admin['full_name'],
                    "user_name": user.full_name,
                    "amount": f"{amount:,.2f}",
                    "bank_name": bank_account.bank_name,
                    "account_number": bank_account.account_number,
                    "timestamp": timestamp,
                },
            )

        # In-app notification
        create_notification_task.delay(
            user_id=user.id,
            notification_type='withdrawal',
            title='Withdrawal Requested',
            body=f'Your withdrawal of \u20a6{amount:,.2f} to {bank_account.bank_name} has been requested and is pending review.',
        )

        # Telegram admin alert
        telegram_msg = (
            "\U0001f4b8 <b>WITHDRAWAL REQUESTED</b>\n"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            f"\U0001f464 <b>User:</b> {user.full_name} ({user.email})\n"
            f"\U0001f4b5 <b>Amount:</b> \u20a6{amount:,.2f}\n"
            f"\U0001f3e6 <b>Bank:</b> {bank_account.bank_name} \u2014 <code>{bank_account.account_number}</code>\n"
            f"\U0001f517 <b>Ref:</b> <code>{withdrawal_ref}</code>\n"
            f"\u23f0 {timestamp}"
        )
        send_telegram_task.delay(telegram_msg)

        return {
            "message": "Withdrawal request received and pending review",
            "reference": withdrawal_ref,
            "status": withdrawal.status
        }

    # process_paystack_webhook removed.
