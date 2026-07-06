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

    class Meta:
        db_table = 'gift_cards'
        verbose_name = 'Gift Card'
        verbose_name_plural = 'Gift Cards'

    def __str__(self):
        return f"{self.brand} ({self.country})"
