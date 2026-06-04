import logging
from decimal import Decimal, ROUND_DOWN
from typing import Dict, Optional

import httpx
from django.conf import settings
from django.utils import timezone

from .models import CachedRate, ASSET_TO_COINGECKO_ID, COINGECKO_ID_TO_ASSET, AssetChoices

logger = logging.getLogger(__name__)

# How long (seconds) before a cached rate is considered stale
RATE_CACHE_TTL = 60


class RateService:
    """Handles fetching rates from CoinGecko, caching, and margin application."""

    @staticmethod
    def fetch_live_rates() -> Dict[str, Decimal]:
        """
        Fetch live rates for all supported assets from CoinGecko.
        Returns dict of {asset_code: rate_ngn}.
        Updates the CachedRate table.
        """
        coingecko_ids = ','.join(ASSET_TO_COINGECKO_ID.values())
        base_url = getattr(settings, 'COINGECKO_BASE_URL', 'https://api.coingecko.com/api/v3')
        api_key = getattr(settings, 'COINGECKO_API_KEY', '')

        params = {
            'ids': coingecko_ids,
            'vs_currencies': 'ngn',
        }
        headers = {}
        if api_key:
            headers['x-cg-demo-api-key'] = api_key

        try:
            with httpx.Client(timeout=10) as client:
                response = client.get(
                    f'{base_url}/simple/price',
                    params=params,
                    headers=headers,
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as e:
            logger.error(f'CoinGecko API error: {e}')
            raise ValueError(f'Failed to fetch rates from CoinGecko: {e}')

        rates = {}
        for coingecko_id, prices in data.items():
            asset = COINGECKO_ID_TO_ASSET.get(coingecko_id)
            if asset and 'ngn' in prices:
                rate = Decimal(str(prices['ngn']))
                rates[asset] = rate

                # Update cache
                CachedRate.objects.update_or_create(
                    asset=asset,
                    defaults={'rate_ngn': rate},
                )

        logger.info(f'Fetched and cached rates for {len(rates)} assets')
        return rates

    @staticmethod
    def get_market_rate(asset: str) -> Decimal:
        """
        Get the current market rate for an asset in NGN.
        Uses cached rate if fresh (< RATE_CACHE_TTL seconds old),
        otherwise fetches from CoinGecko.
        """
        asset = asset.lower()
        if asset not in ASSET_TO_COINGECKO_ID:
            raise ValueError(f'Unsupported asset: {asset}')

        try:
            cached = CachedRate.objects.get(asset=asset)
            age = (timezone.now() - cached.updated_at).total_seconds()
            if age < RATE_CACHE_TTL:
                return cached.rate_ngn
        except CachedRate.DoesNotExist:
            pass

        # Cache is stale or missing — fetch all rates
        rates = RateService.fetch_live_rates()
        if asset not in rates:
            raise ValueError(f'Rate for {asset} not available')
        return rates[asset]

    @staticmethod
    def get_margin_percentage() -> Decimal:
        """Get the platform conversion margin percentage from settings."""
        return Decimal(str(
            getattr(settings, 'CONVERSION_MARGIN_PERCENTAGE', 2.0)
        ))

    @staticmethod
    def get_user_rate(asset: str) -> Decimal:
        """
        Get the rate the user actually receives (market rate minus margin).
        If market rate is ₦1,600 and margin is 2%, user gets ₦1,568.
        """
        market_rate = RateService.get_market_rate(asset)
        margin = RateService.get_margin_percentage()
        discount = market_rate * (margin / Decimal('100'))
        user_rate = (market_rate - discount).quantize(Decimal('0.01'), rounding=ROUND_DOWN)
        return user_rate

    @staticmethod
    def calculate_ngn_amount(asset: str, crypto_amount: Decimal) -> Dict:
        """
        Calculate the NGN amount a user receives for a given crypto amount.
        Returns dict with rate details for record-keeping.
        """
        market_rate = RateService.get_market_rate(asset)
        margin = RateService.get_margin_percentage()
        user_rate = RateService.get_user_rate(asset)
        ngn_amount = (crypto_amount * user_rate).quantize(Decimal('0.01'), rounding=ROUND_DOWN)

        return {
            'market_rate': market_rate,
            'user_rate': user_rate,
            'margin_percentage': margin,
            'crypto_amount': crypto_amount,
            'ngn_amount': ngn_amount,
        }

    @staticmethod
    def get_all_rates() -> list:
        """Get rates for all supported assets."""
        results = []
        margin = RateService.get_margin_percentage()

        # Try to fetch fresh rates for all assets at once
        try:
            RateService.fetch_live_rates()
        except ValueError:
            logger.warning('Could not fetch live rates, using cached')

        for asset_code, _ in AssetChoices.choices:
            try:
                cached = CachedRate.objects.get(asset=asset_code)
                market_rate = cached.rate_ngn
                discount = market_rate * (margin / Decimal('100'))
                user_rate = (market_rate - discount).quantize(Decimal('0.01'), rounding=ROUND_DOWN)

                results.append({
                    'asset': asset_code,
                    'market_rate': market_rate,
                    'user_rate': user_rate,
                    'margin_percentage': margin,
                    'updated_at': cached.updated_at.isoformat(),
                })
            except CachedRate.DoesNotExist:
                results.append({
                    'asset': asset_code,
                    'market_rate': None,
                    'user_rate': None,
                    'margin_percentage': margin,
                    'updated_at': None,
                })

        return results
