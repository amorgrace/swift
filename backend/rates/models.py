from django.db import models


class AssetChoices(models.TextChoices):
    BTC = 'btc', 'Bitcoin'
    ETH = 'eth', 'Ethereum'
    USDT = 'usdt', 'Tether'
    USDC = 'usdc', 'USD Coin'
    SOL = 'sol', 'Solana'
    BNB = 'bnb', 'Binance Coin'


# Mapping from our asset codes to CoinGecko IDs
ASSET_TO_COINGECKO_ID = {
    'btc': 'bitcoin',
    'eth': 'ethereum',
    'usdt': 'tether',
    'usdc': 'usd-coin',
    'sol': 'solana',
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
