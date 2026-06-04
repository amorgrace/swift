import logging
from decimal import Decimal
import uuid

from django.conf import settings
from django.db import transaction

from rates.services import RateService
from wallets.models import NGNWallet, BankAccount
from wallets.services import PaystackService
from .models import (
    Deposit,
    Withdrawal,
    Transaction,
    DepositStatus,
    WithdrawalStatus,
    TransactionType,
)

logger = logging.getLogger(__name__)


class DepositService:
    """Handles processing of incoming crypto deposits via webhook."""

    @staticmethod
    def process_deposit_webhook(payload: dict) -> bool:
        """
        Process a Quidax deposit.successful webhook payload.
        Idempotent: skips if quidax_reference already exists.
        """
        quidax_reference = payload.get('id')
        if not quidax_reference:
            logger.error("Webhook payload missing 'id' (quidax_reference)")
            return False

        # Idempotency check
        if Deposit.objects.filter(quidax_reference=quidax_reference).exists():
            logger.info(f"Deposit {quidax_reference} already processed, skipping.")
            return True

        # Extract data
        # Note: adjust paths based on actual Quidax webhook structure
        quidax_user_id = payload.get('user', {}).get('id')
        asset = payload.get('currency', '').lower()
        network = payload.get('network', '').lower()
        crypto_amount_str = payload.get('amount')

        if not all([quidax_user_id, asset, crypto_amount_str]):
            logger.error("Webhook payload missing required fields (user.id, currency, or amount)")
            return False

        try:
            crypto_amount = Decimal(str(crypto_amount_str))
        except Exception:
            logger.error(f"Invalid amount format in webhook: {crypto_amount_str}")
            return False

        # Find wallet
        try:
            wallet = NGNWallet.objects.get(quidax_user_id=quidax_user_id)
        except NGNWallet.DoesNotExist:
            logger.error(f"No wallet found for Quidax user {quidax_user_id}")
            return False

        with transaction.atomic():
            # 1. Fetch rates and calculate NGN
            try:
                rate_info = RateService.calculate_ngn_amount(asset, crypto_amount)
            except ValueError as e:
                logger.error(f"Rate calculation failed: {e}")
                # We could save it as PENDING and retry later, but for simplicity we fail here
                return False

            ngn_amount = rate_info['ngn_amount']
            user_rate = rate_info['user_rate']
            margin = rate_info['margin_percentage']

            # 2. Create Deposit record
            deposit = Deposit.objects.create(
                wallet=wallet,
                asset=asset,
                network=network,
                crypto_amount=crypto_amount,
                rate_applied=user_rate,
                margin_applied=margin,
                ngn_amount=ngn_amount,
                quidax_reference=quidax_reference,
                status=DepositStatus.CONVERTED,
            )

            # 3. Credit wallet balance
            wallet.credit(ngn_amount)

            # 4. Create Transaction log
            description = f"Received {crypto_amount} {asset.upper()} → ₦{ngn_amount:,.2f}"
            Transaction.objects.create(
                wallet=wallet,
                type=TransactionType.DEPOSIT,
                amount=ngn_amount,
                description=description,
                status=DepositStatus.CONVERTED,
                related_deposit=deposit,
            )

            logger.info(f"Successfully processed deposit {quidax_reference} for wallet {wallet.id}")
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

        if not bank_account.paystack_recipient_code:
            # Try creating it now if it was missing
            try:
                recipient_code = PaystackService.create_transfer_recipient(bank_account)
                bank_account.paystack_recipient_code = recipient_code
                bank_account.save()
            except Exception as e:
                raise ValueError("Bank account is not properly linked with Paystack. Try removing and adding it again.")

        with transaction.atomic():
            # 1. Debit wallet (will raise ValueError if insufficient balance)
            wallet.debit(amount)

            # 2. Create Withdrawal record
            withdrawal_ref = f"WD-{uuid.uuid4().hex[:12].upper()}"
            withdrawal = Withdrawal.objects.create(
                wallet=wallet,
                bank_account=bank_account,
                amount=amount,
                paystack_reference=withdrawal_ref,
                status=WithdrawalStatus.PENDING,
            )

            # 3. Create Transaction log
            description = f"Withdrawal to {bank_account.bank_name} - {bank_account.account_number}"
            txn_log = Transaction.objects.create(
                wallet=wallet,
                type=TransactionType.WITHDRAWAL,
                amount=amount,
                reference=withdrawal_ref,
                description=description,
                status=WithdrawalStatus.PENDING,
                related_withdrawal=withdrawal,
            )

        # Proceed to initiate transfer outside the main atomic block to avoid holding db locks during API call
        # In a real app, this should be done via a Celery background task
        try:
            amount_kobo = int(amount * 100)
            paystack_res = PaystackService.initiate_transfer(
                amount_kobo,
                bank_account.paystack_recipient_code,
                withdrawal_ref
            )
            
            # Update status
            withdrawal.paystack_transfer_code = paystack_res.get('transfer_code', '')
            withdrawal.status = WithdrawalStatus.PROCESSING
            withdrawal.save()

            txn_log.status = WithdrawalStatus.PROCESSING
            txn_log.save()

        except Exception as e:
            logger.error(f"Paystack transfer initiation failed for {withdrawal_ref}: {e}")
            # If initiation fails completely, we should reverse the debit
            # (In production, be careful: maybe it timed out but succeeded on Paystack's end. 
            # Webhook or query status will confirm. For simplicity here, we assume if initiation fails, it didn't go through.)
            with transaction.atomic():
                wallet.credit(amount)
                withdrawal.status = WithdrawalStatus.FAILED
                withdrawal.save()
                txn_log.status = WithdrawalStatus.FAILED
                txn_log.save()
            raise ValueError("Failed to initiate transfer with payment provider. Funds have been refunded.")

        return {
            "message": "Withdrawal is processing",
            "reference": withdrawal_ref,
            "status": withdrawal.status
        }

    @staticmethod
    def process_paystack_webhook(payload: dict) -> bool:
        """
        Process Paystack transfer.success or transfer.failed webhooks.
        """
        event = payload.get('event')
        data = payload.get('data', {})
        reference = data.get('reference')

        if not reference:
            logger.error("Paystack webhook payload missing reference")
            return False

        try:
            withdrawal = Withdrawal.objects.get(paystack_reference=reference)
            txn_log = Transaction.objects.get(reference=reference)
        except (Withdrawal.DoesNotExist, Transaction.DoesNotExist):
            logger.error(f"Withdrawal or Transaction log not found for reference {reference}")
            return False

        if withdrawal.status in [WithdrawalStatus.SUCCESS, WithdrawalStatus.FAILED, WithdrawalStatus.REVERSED]:
            logger.info(f"Withdrawal {reference} already processed (status: {withdrawal.status}).")
            return True

        if event == 'transfer.success':
            withdrawal.status = WithdrawalStatus.SUCCESS
            withdrawal.save()
            txn_log.status = WithdrawalStatus.SUCCESS
            txn_log.save()
            logger.info(f"Withdrawal {reference} successful")
            return True

        elif event in ['transfer.failed', 'transfer.reversed']:
            with transaction.atomic():
                # Refund the wallet
                withdrawal.wallet.credit(withdrawal.amount)
                
                status = WithdrawalStatus.FAILED if event == 'transfer.failed' else WithdrawalStatus.REVERSED
                withdrawal.status = status
                withdrawal.save()
                
                txn_log.status = status
                txn_log.save()
            logger.info(f"Withdrawal {reference} {status}, funds refunded.")
            return True

        logger.warning(f"Unhandled Paystack event: {event}")
        return False
