from django.db import models


class AssetChoices(models.TextChoices):
    BTC = 'btc', 'Bitcoin'
    ETH = 'eth', 'Ethereum'
    USDT = 'usdt', 'Tether'
    USDC = 'usdc', 'USD Coin'
    BNB = 'bnb', 'Binance Coin'


# Mapping from our asset codes to CoinGecko IDs
ASSET_TO_COINGECKO_ID = {
    'btc': 'bitcoin',
    'eth': 'ethereum',
    'usdt': 'tether',
    'usdc': 'usd-coin',
    'bnb': 'binancecoin',
}

# Reverse mapping
COINGECKO_ID_TO_ASSET = {v: k for k, v in ASSET_TO_COINGECKO_ID.items()}


class CachedRate(models.Model):
    """
    Stores the last-fetched market rate per asset from CoinGecko.
    Used to avoid hammering the API on every request.
    """
    asset = models.CharField(
        max_length=10,
        choices=AssetChoices.choices,
        unique=True,
    )
    rate_ngn = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        help_text='Raw market rate in NGN from CoinGecko',
    )
    rate_usd = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Raw market rate in USD from CoinGecko',
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'cached_rates'
        verbose_name = 'Cached Rate'
        verbose_name_plural = 'Cached Rates'

    def __str__(self):
        return f"{self.get_asset_display()}: ₦{self.rate_ngn:,.2f}"


class SystemSettings(models.Model):
    """
    Stores global system configuration that admins can update dynamically.
    Enforces a single-row design.
    """
    conversion_margin_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=2.0,
        help_text='Platform margin percentage taken on conversions (e.g. 2.0 = 2%)'
    )
    ngn_usd_buy_rate = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0.00,
        help_text='If greater than 0, this explicit NGN/USD rate is used to calculate user payouts directly, ignoring the margin percentage.'
    )
    
    class Meta:
        db_table = 'system_settings'
        verbose_name = 'System Settings'
        verbose_name_plural = 'System Settings'
        
    @classmethod
    def get_settings(cls):
        from django.core.cache import cache
        settings_obj = cache.get('system_settings')
        if not settings_obj:
            settings_obj, created = cls.objects.get_or_create(id=1)
            cache.set('system_settings', settings_obj, timeout=3600)  # Cache for 1 hour
        return settings_obj

    def save(self, *args, **kwargs):
        from django.core.cache import cache
        super().save(*args, **kwargs)
        cache.delete('system_settings')  # Invalidate cache on update

    def __str__(self):
        return f"System Settings (Margin: {self.conversion_margin_percentage}%)"


class GiftCard(models.Model):
    brand = models.CharField(max_length=100)
    category = models.CharField(max_length=100)
    color = models.CharField(max_length=50, default="#FFFFFF")
    bg = models.CharField(max_length=255, default="linear-gradient(135deg, #1a1a1a, #000000)")
    denominations = models.JSONField(default=list)
    rates = models.JSONField(default=dict)
    rate_per_dollar = models.DecimalField(max_digits=10, decimal_places=2)
    country = models.CharField(max_length=50)
    popular = models.BooleanField(default=False)
    use_auto_rate = models.BooleanField(default=True, help_text='Automatically calculate rate from NGN/USD buy rate')
    rate_multiplier = models.DecimalField(
        max_digits=6,
        decimal_places=4,
        default=0.9000,
        help_text='Multiplier applied to NGN/USD buy rate (e.g. 0.9000 for 90%)',
    )

    class Meta:
        db_table = 'gift_cards'
        verbose_name = 'Gift Card'
        verbose_name_plural = 'Gift Cards'

    def __str__(self):
        return f"{self.brand} ({self.country})"


class RejectionReason(models.Model):
    """
    Admin-defined list of reasons for rejecting a gift card submission.
    Shown as a dropdown in the admin panel — no free-text typing needed.
    """
    code = models.CharField(max_length=50, unique=True)
    label = models.CharField(max_length=255)
    description = models.CharField(max_length=500, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'giftcard_rejection_reasons'
        verbose_name = 'Rejection Reason'
        verbose_name_plural = 'Rejection Reasons'
        ordering = ['label']

    def __str__(self):
        return self.label


class GiftCardTransactionStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    APPROVED = 'approved', 'Approved'
    REJECTED = 'rejected', 'Rejected'


def generate_gc_reference() -> str:
    import random
    import string
    chars = string.ascii_uppercase + string.digits
    suffix = ''.join(random.choices(chars, k=6))
    return f'GC{suffix}'


class GiftCardTransaction(models.Model):
    """
    Records a user's manual gift card sell submission.
    Admin reviews the uploaded image and either approves (credits NGN wallet)
    or rejects with a predefined reason.
    """
    user = models.ForeignKey(
        'authenticator.User',
        on_delete=models.CASCADE,
        related_name='giftcard_transactions',
    )
    wallet = models.ForeignKey(
        'wallets.NGNWallet',
        on_delete=models.CASCADE,
        related_name='giftcard_transactions',
    )
    brand = models.CharField(max_length=100, help_text='e.g. Amazon')
    country_code = models.CharField(max_length=10, help_text='e.g. US')
    currency_symbol = models.CharField(max_length=5, help_text='e.g. $')
    denomination = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text='Face value of the card in its native currency',
    )
    rate_applied = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text='NGN rate per unit at time of submission',
    )
    ngn_payout = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        help_text='Expected NGN payout = denomination × rate',
    )
    image_url = models.URLField(
        max_length=1000,
        help_text='Cloudinary secure_url of the uploaded gift card image',
    )
    card_code = models.CharField(
        max_length=255,
        blank=True,
        help_text='Optional card code typed by the user',
    )
    status = models.CharField(
        max_length=20,
        choices=GiftCardTransactionStatus.choices,
        default=GiftCardTransactionStatus.PENDING,
        db_index=True,
    )
    rejection_reason = models.ForeignKey(
        RejectionReason,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='transactions',
    )
    reference = models.CharField(
        max_length=10,
        unique=True,
        default=generate_gc_reference,
    )
    reviewed_by = models.ForeignKey(
        'authenticator.User',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='reviewed_giftcard_transactions',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = models.Manager()

    class Meta:
        db_table = 'giftcard_transactions'
        verbose_name = 'Gift Card Transaction'
        verbose_name_plural = 'Gift Card Transactions'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['status', '-created_at']),
        ]

    def __str__(self):
        return f"{self.reference} — {self.brand} {self.currency_symbol}{self.denomination} ({self.status})"
