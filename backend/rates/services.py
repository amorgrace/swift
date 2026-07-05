import logging
from decimal import Decimal, ROUND_DOWN
from typing import Dict, Optional

import httpx
from django.conf import settings
from django.utils import timezone

from .models import CachedRate, ASSET_TO_COINGECKO_ID, COINGECKO_ID_TO_ASSET, AssetChoices, SystemSettings

logger = logging.getLogger(__name__)

# How long (seconds) before a cached rate is considered stale
RATE_CACHE_TTL = 60


class RateService:
    """Handles fetching rates from CoinGecko, caching, and margin application."""

    @staticmethod
    def fetch_live_rates() -> Dict[str, dict]:
        """
        Fetch live rates for all supported assets from CoinGecko in both NGN and USD.
        Returns dict of {asset_code: {'ngn': rate_ngn, 'usd': rate_usd}}.
        Updates the CachedRate table.
        """
        coingecko_ids = ','.join(ASSET_TO_COINGECKO_ID.values())
        base_url = getattr(settings, 'COINGECKO_BASE_URL', 'https://api.coingecko.com/api/v3')
        api_key = getattr(settings, 'COINGECKO_API_KEY', '')

        params = {
            'ids': coingecko_ids,
            'vs_currencies': 'ngn,usd',
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

        from django.core.cache import cache
        
        rates = {}
        for coingecko_id, prices in data.items():
            asset = COINGECKO_ID_TO_ASSET.get(coingecko_id)
            if asset and 'ngn' in prices and 'usd' in prices:
                rate_ngn = Decimal(str(prices['ngn']))
                rate_usd = Decimal(str(prices['usd']))
                rates[asset] = {'ngn': rate_ngn, 'usd': rate_usd}

                # Update DB cache
                CachedRate.objects.update_or_create(
                    asset=asset,
                    defaults={'rate_ngn': rate_ngn, 'rate_usd': rate_usd},
                )
                
                # Update Redis L1 cache
                cache.set(f'market_rates_{asset}', rates[asset], timeout=RATE_CACHE_TTL)
                
        # Invalidate the all_rates cache so it gets rebuilt
        cache.delete('all_rates_computed')

        logger.info(f'Fetched and cached rates for {len(rates)} assets')
        return rates

    @staticmethod
    def get_market_rates(asset: str) -> dict:
        """
        Get the current market rate for an asset in NGN and USD.
        """
        asset = asset.lower()
        if asset not in ASSET_TO_COINGECKO_ID:
            raise ValueError(f'Unsupported asset: {asset}')

        from django.core.cache import cache
        cache_key = f'market_rates_{asset}'
        cached_rates = cache.get(cache_key)
        if cached_rates:
            return cached_rates

        try:
            cached = CachedRate.objects.get(asset=asset)
            age = (timezone.now() - cached.updated_at).total_seconds()
            if age < RATE_CACHE_TTL and cached.rate_usd is not None:
                rates = {'ngn': cached.rate_ngn, 'usd': cached.rate_usd}
                # Backfill Redis
                cache.set(cache_key, rates, timeout=int(RATE_CACHE_TTL - age))
                return rates
        except CachedRate.DoesNotExist:
            pass

        # Cache is stale or missing — fetch all rates
        rates = RateService.fetch_live_rates()
        if asset not in rates:
            raise ValueError(f'Rate for {asset} not available')
        return rates[asset]

    @staticmethod
    def get_market_rate(asset: str) -> Decimal:
        """
        Get the current market rate for an asset in NGN.
        """
        rates = RateService.get_market_rates(asset)
        return rates['ngn']

    @staticmethod
    def get_margin_percentage() -> Decimal:
        """Get the platform conversion margin percentage from settings."""
        settings_obj = SystemSettings.get_settings()
        return settings_obj.conversion_margin_percentage

    @staticmethod
    def get_user_rate(asset: str) -> Decimal:
        """
        Get the rate the user receives (market rate minus platform margin).
        If market rate is ₦1,600 and margin is 2%, user receives ₦1,568.
        If ngn_usd_buy_rate is set > 0, we bypass margin and calculate based on asset's USD value * ngn_usd_buy_rate.
        """
        settings_obj = SystemSettings.get_settings()
        if settings_obj.ngn_usd_buy_rate > Decimal('0'):
            # Convert the CoinGecko USD price directly to NGN
            try:
                cached = CachedRate.objects.get(asset=asset.lower())
                if cached.rate_usd and cached.rate_usd > 0:
                    return (cached.rate_usd * settings_obj.ngn_usd_buy_rate).quantize(Decimal('0.01'), rounding=ROUND_DOWN)
            except CachedRate.DoesNotExist:
                pass
            
        market_rate = RateService.get_market_rate(asset)
        margin = settings_obj.conversion_margin_percentage
        markdown = market_rate * (margin / Decimal('100'))
        user_rate = (market_rate - markdown).quantize(Decimal('0.01'), rounding=ROUND_DOWN)
        return user_rate

    @staticmethod
    def calculate_ngn_amount(asset: str, crypto_amount: Decimal) -> Dict:
        """
        Calculate the NGN amount a user receives for a given crypto amount.
        Returns dict with rate details for record-keeping.
        Also returns ngn_usd_rate — the user-friendly NGN/USD rate shown on the Live Rates panel.
        """
        market_rate = RateService.get_market_rate(asset)
        margin = RateService.get_margin_percentage()
        user_rate = RateService.get_user_rate(asset)
        ngn_amount = (crypto_amount * user_rate).quantize(Decimal('0.01'), rounding=ROUND_DOWN)

        # Determine the user-friendly NGN/USD rate (matches what Live Rates panel shows)
        settings_obj = SystemSettings.get_settings()
        if settings_obj.ngn_usd_buy_rate > Decimal('0'):
            ngn_usd_rate = settings_obj.ngn_usd_buy_rate
        else:
            # Derive it from rate_usd if available
            try:
                cached = CachedRate.objects.get(asset=asset.lower())
                if cached.rate_usd and cached.rate_usd > Decimal('0'):
                    ngn_usd_rate = (market_rate / cached.rate_usd).quantize(Decimal('0.01'), rounding=ROUND_DOWN)
                else:
                    ngn_usd_rate = None
            except CachedRate.DoesNotExist:
                ngn_usd_rate = None

        return {
            'market_rate': market_rate,
            'user_rate': user_rate,
            'margin_percentage': margin,
            'crypto_amount': crypto_amount,
            'ngn_amount': ngn_amount,
            'ngn_usd_rate': ngn_usd_rate,
        }

    @staticmethod
    def get_all_rates() -> list:
        """Get rates for all supported assets, including implied NGN/USD rates."""
        from django.core.cache import cache
        cached_all_rates = cache.get('all_rates_computed')
        if cached_all_rates:
            return cached_all_rates

        results = []
        margin = RateService.get_margin_percentage()

        # Check if we have fresh rates in DB cache
        needs_fetch = True
        oldest_rate = CachedRate.objects.all().order_by('updated_at').first()
        if oldest_rate:
            age = (timezone.now() - oldest_rate.updated_at).total_seconds()
            if age < RATE_CACHE_TTL:
                needs_fetch = False

        if needs_fetch:
            try:
                RateService.fetch_live_rates()
            except ValueError:
                logger.warning('Could not fetch live rates, using cached')

        for asset_code, _ in AssetChoices.choices:
            try:
                cached = CachedRate.objects.get(asset=asset_code)
                market_rate = cached.rate_ngn
                rate_usd = cached.rate_usd

                settings_obj = SystemSettings.get_settings()
                if settings_obj.ngn_usd_buy_rate > Decimal('0') and rate_usd and rate_usd > Decimal('0'):
                    user_rate = (rate_usd * settings_obj.ngn_usd_buy_rate).quantize(Decimal('0.01'), rounding=ROUND_DOWN)
                    market_ngn_usd_rate = (market_rate / rate_usd).quantize(Decimal('0.01'), rounding=ROUND_DOWN)
                    user_ngn_usd_rate = settings_obj.ngn_usd_buy_rate
                else:
                    markdown = market_rate * (margin / Decimal('100'))
                    user_rate = (market_rate - markdown).quantize(Decimal('0.01'), rounding=ROUND_DOWN)

                    market_ngn_usd_rate = None
                    user_ngn_usd_rate = None
                    if rate_usd and rate_usd > Decimal('0'):
                        market_ngn_usd_rate = (market_rate / rate_usd).quantize(Decimal('0.01'), rounding=ROUND_DOWN)
                        usd_markdown = market_ngn_usd_rate * (margin / Decimal('100'))
                        user_ngn_usd_rate = (market_ngn_usd_rate - usd_markdown).quantize(Decimal('0.01'), rounding=ROUND_DOWN)

                results.append({
                    'asset': asset_code,
                    'market_rate': market_rate,
                    'user_rate': user_rate,
                    'market_ngn_usd_rate': market_ngn_usd_rate,
                    'user_ngn_usd_rate': user_ngn_usd_rate,
                    'margin_percentage': margin if settings_obj.ngn_usd_buy_rate <= Decimal('0') else Decimal('0.00'),
                    'updated_at': cached.updated_at.isoformat(),
                })
            except CachedRate.DoesNotExist:
                results.append({
                    'asset': asset_code,
                    'market_rate': None,
                    'user_rate': None,
                    'market_ngn_usd_rate': None,
                    'user_ngn_usd_rate': None,
                    'margin_percentage': margin,
                    'updated_at': None,
                })

        from django.core.cache import cache
        cache.set('all_rates_computed', results, timeout=RATE_CACHE_TTL)

        return results
