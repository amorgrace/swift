import uuid
import random
import string
from decimal import Decimal

from django.db import models

from rates.models import AssetChoices
from wallets.models import BankAccount, NGNWallet, NetworkChoices


def generate_transaction_id() -> str:
    """
    Generate a unique transaction ID with the 'TX' prefix.
    Format: TX + 8 uppercase alphanumeric characters = 10 characters total.
    Example: TXAB3F9K2P
    """
    chars = string.ascii_uppercase + string.digits
    suffix = ''.join(random.choices(chars, k=8))
    return f'TX{suffix}'


class DepositStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    CONFIRMED = 'confirmed', 'Confirmed'
    CONVERTED = 'converted', 'Converted'
    FAILED = 'failed', 'Failed'


class WithdrawalStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    PROCESSING = 'processing', 'Processing'
    SUCCESS = 'success', 'Success'
    FAILED = 'failed', 'Failed'
    REVERSED = 'reversed', 'Reversed'


class TransactionType(models.TextChoices):
    DEPOSIT = 'deposit', 'Deposit'
    WITHDRAWAL = 'withdrawal', 'Withdrawal'


class Deposit(models.Model):
    """
    Records an incoming crypto deposit.
    """
    wallet = models.ForeignKey(
        NGNWallet,
        on_delete=models.CASCADE,
        related_name='deposits',
    )
    asset = models.CharField(max_length=10, choices=AssetChoices.choices)
    network = models.CharField(max_length=20, choices=NetworkChoices.choices)
    crypto_amount = models.DecimalField(
        max_digits=20,
        decimal_places=8,
        help_text='Amount of crypto deposited',
    )
    rate_applied = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        help_text='User rate (NGN) at the time of conversion',
    )
    margin_applied = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text='Margin percentage applied at conversion',
    )
    ngn_amount = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        help_text='Final NGN amount credited to wallet',
    )
    quidax_reference = models.CharField(
        max_length=255,
        unique=True,
        help_text='Quidax transaction ID for idempotency',
    )
    status = models.CharField(
        max_length=20,
        choices=DepositStatus.choices,
        default=DepositStatus.PENDING,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'deposits'
        verbose_name = 'Deposit'
        verbose_name_plural = 'Deposits'
        ordering = ['-created_at']

    def __str__(self):
        return f"Deposit {self.crypto_amount} {self.asset.upper()} -> ₦{self.ngn_amount}"


class Withdrawal(models.Model):
    """
    Records an NGN withdrawal to a bank account.
    """
    wallet = models.ForeignKey(
        NGNWallet,
        on_delete=models.CASCADE,
        related_name='withdrawals',
    )
    bank_account = models.ForeignKey(
        BankAccount,
        on_delete=models.PROTECT,
        related_name='withdrawals',
    )
    amount = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        help_text='Amount of NGN to withdraw',
    )
    fee = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Any withdrawal fee applied',
    )
    paystack_reference = models.CharField(
        max_length=255,
        unique=True,
        default=uuid.uuid4,
        help_text='Unique reference for Paystack',
    )
    paystack_transfer_code = models.CharField(
        max_length=255,
        blank=True,
        help_text='Transfer code from Paystack',
    )
    status = models.CharField(
        max_length=20,
        choices=WithdrawalStatus.choices,
        default=WithdrawalStatus.PENDING,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'withdrawals'
        verbose_name = 'Withdrawal'
        verbose_name_plural = 'Withdrawals'
        ordering = ['-created_at']

    def __str__(self):
        return f"Withdrawal ₦{self.amount} -> {self.bank_account.bank_name}"


class Transaction(models.Model):
    """
    Unified transaction log for user's history.
    """
    wallet = models.ForeignKey(
        NGNWallet,
        on_delete=models.CASCADE,
        related_name='transactions',
    )
    type = models.CharField(max_length=20, choices=TransactionType.choices)
    amount = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        help_text='Amount in NGN',
    )
    reference = models.CharField(
        max_length=10,
        unique=True,
        default=generate_transaction_id,
    )
    description = models.CharField(max_length=255)
    status = models.CharField(max_length=50)
    related_deposit = models.ForeignKey(
        Deposit,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    related_withdrawal = models.ForeignKey(
        Withdrawal,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'transactions_log'
        verbose_name = 'Transaction'
        verbose_name_plural = 'Transactions'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_type_display()} ₦{self.amount} - {self.status}"
