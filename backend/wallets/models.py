from decimal import Decimal

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.db import models, transaction

from rates.models import AssetChoices


class NetworkChoices(models.TextChoices):
    BITCOIN = 'bitcoin', 'Bitcoin'
    ERC20 = 'erc20', 'ERC-20'
    BEP20 = 'bep20', 'BEP-20'


# Which networks are valid for each asset
ASSET_NETWORKS = {
    'btc': [NetworkChoices.BITCOIN],
    'eth': [NetworkChoices.ERC20],
    'usdt': [NetworkChoices.ERC20, NetworkChoices.BEP20],
    'usdc': [NetworkChoices.ERC20],
    'bnb': [NetworkChoices.BEP20],
}


class NGNWallet(models.Model):
    """
    User's NGN wallet. One per user.
    This is an internal ledger — all crypto is auto-converted to NGN.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='ngn_wallet',
    )
    balance = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Current NGN balance',
    )
    quidax_user_id = models.CharField(
        max_length=255,
        blank=True,
        help_text='Quidax sub-account ID for this user',
    )
    transaction_pin_hash = models.CharField(
        max_length=128,
        blank=True,
        help_text='Hashed 4-digit transaction PIN',
    )
    pin_is_set = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ngn_wallets'
        verbose_name = 'NGN Wallet'
        verbose_name_plural = 'NGN Wallets'

    def __str__(self):
        return f"₦{self.balance:,.2f} — {self.user.email}"

    def set_transaction_pin(self, pin: str):
        """Hash and store a 4-digit transaction PIN."""
        if len(pin) != 4 or not pin.isdigit():
            raise ValueError('Transaction PIN must be exactly 4 digits')
        self.transaction_pin_hash = make_password(pin)
        self.pin_is_set = True
        self.save(update_fields=['transaction_pin_hash', 'pin_is_set'])

    def verify_transaction_pin(self, pin: str) -> bool:
        """Verify a transaction PIN against the stored hash."""
        if not self.pin_is_set:
            raise ValueError('Transaction PIN has not been set')
        return check_password(pin, self.transaction_pin_hash)

    def credit(self, amount: Decimal):
        """Atomically credit the wallet balance."""
        if amount <= 0:
            raise ValueError('Credit amount must be positive')
        with transaction.atomic():
            wallet = NGNWallet.objects.select_for_update().get(pk=self.pk)
            wallet.balance += amount
            wallet.save(update_fields=['balance', 'updated_at'])
            self.balance = wallet.balance

    def debit(self, amount: Decimal):
        """Atomically debit the wallet balance."""
        if amount <= 0:
            raise ValueError('Debit amount must be positive')
        with transaction.atomic():
            wallet = NGNWallet.objects.select_for_update().get(pk=self.pk)
            if wallet.balance < amount:
                raise ValueError('Insufficient balance')
            wallet.balance -= amount
            wallet.save(update_fields=['balance', 'updated_at'])
            self.balance = wallet.balance


class DepositAddress(models.Model):
    """
    Crypto deposit address for a user, per asset and network.
    Generated via HD wallet derivation and monitored by Tatum.
    """
    wallet = models.ForeignKey(
        NGNWallet,
        on_delete=models.CASCADE,
        related_name='deposit_addresses',
    )
    asset = models.CharField(max_length=10, choices=AssetChoices.choices)
    network = models.CharField(max_length=20, choices=NetworkChoices.choices)
    address = models.CharField(max_length=255)
    derivation_index = models.PositiveIntegerField(null=True, blank=True)
    tatum_subscription_id = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'deposit_addresses'
        verbose_name = 'Deposit Address'
        verbose_name_plural = 'Deposit Addresses'
        unique_together = ('wallet', 'asset', 'network')

    def __str__(self):
        return f"{self.asset.upper()} ({self.network}): {self.address[:12]}..."


class BankAccount(models.Model):
    """
    User's linked Nigerian bank account for NGN withdrawals via Paystack.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='bank_accounts',
    )
    bank_name = models.CharField(max_length=255)
    bank_code = models.CharField(
        max_length=10,
        help_text='Paystack bank code',
    )
    account_number = models.CharField(max_length=20)
    account_name = models.CharField(
        max_length=255,
        help_text='Resolved account name from Paystack',
    )
    paystack_recipient_code = models.CharField(
        max_length=255,
        blank=True,
        help_text='Paystack transfer recipient code',
    )
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'bank_accounts'
        verbose_name = 'Bank Account'
        verbose_name_plural = 'Bank Accounts'

    def __str__(self):
        return f"{self.bank_name} — {self.account_number} ({self.account_name})"


class AdminProfile(models.Model):
    """
    Stores admin-level sweep PIN (separate from user transaction PIN).
    One per staff user.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='admin_profile',
        limit_choices_to={'is_staff': True},
    )
    sweep_pin_hash = models.CharField(max_length=128, blank=True)
    pin_is_set = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'admin_profiles'
        verbose_name = 'Admin Profile'
        verbose_name_plural = 'Admin Profiles'

    def set_sweep_pin(self, pin: str):
        if len(pin) != 6 or not pin.isdigit():
            raise ValueError('Sweep PIN must be exactly 6 digits')
        self.sweep_pin_hash = make_password(pin)
        self.pin_is_set = True
        self.save(update_fields=['sweep_pin_hash', 'pin_is_set', 'updated_at'])

    def verify_sweep_pin(self, pin: str) -> bool:
        if not self.pin_is_set:
            raise ValueError('Sweep PIN has not been set')
        return check_password(pin, self.sweep_pin_hash)

    def __str__(self):
        return f"AdminProfile — {self.user.email}"


class SweepStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    APPROVED = 'approved', 'Approved'
    BROADCAST = 'broadcast', 'Broadcast'
    CONFIRMED = 'confirmed', 'Confirmed'
    FAILED = 'failed', 'Failed'


class SweepRequest(models.Model):
    """
    Audit trail for every admin-initiated crypto sweep.
    """
    network = models.CharField(max_length=20, choices=NetworkChoices.choices)
    asset = models.CharField(max_length=10, choices=[
        ('btc', 'BTC'), ('eth', 'ETH'), ('usdt', 'USDT'),
        ('usdc', 'USDC'), ('bnb', 'BNB'),
    ])
    addresses_swept = models.JSONField(default=list, help_text='List of sub-wallet addresses included')
    total_crypto_amount = models.DecimalField(max_digits=30, decimal_places=10)
    gas_cost_crypto = models.DecimalField(max_digits=30, decimal_places=10, default=0)
    destination_address = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=SweepStatus.choices, default=SweepStatus.PENDING)
    tx_hash = models.CharField(max_length=255, blank=True)
    error_message = models.TextField(blank=True)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='sweep_requests',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'sweep_requests'
        verbose_name = 'Sweep Request'
        verbose_name_plural = 'Sweep Requests'
        ordering = ['-created_at']

    def __str__(self):
        return f"Sweep {self.asset.upper()} ({self.network}) — {self.status} [{self.created_at:%Y-%m-%d}]"
