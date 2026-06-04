from ninja import Router
from ninja.errors import HttpError
from django_ratelimit.decorators import ratelimit

from .schemas import RateResponseSchema
from .services import RateService
from .models import AssetChoices

router = Router(tags=['Rates'])


@router.get('/', response=list[RateResponseSchema], auth=None)
@ratelimit(key='ip', rate='10/m', block=True)
def get_all_rates(request):
    """Get current rates for all supported assets (public)."""
    try:
        rates = RateService.get_all_rates()
        return rates
    except Exception as e:
        raise HttpError(500, f'Failed to fetch rates: {str(e)}')


@router.get('/{asset}/', response=RateResponseSchema, auth=None)
@ratelimit(key='ip', rate='10/m', block=True)
def get_asset_rate(request, asset: str):
    """Get current rate for a specific asset (public)."""
    asset = asset.lower()

    valid_assets = [choice[0] for choice in AssetChoices.choices]
    if asset not in valid_assets:
        raise HttpError(400, f'Unsupported asset: {asset}. Supported: {", ".join(valid_assets)}')

    try:
        market_rate = RateService.get_market_rate(asset)
        user_rate = RateService.get_user_rate(asset)
        margin = RateService.get_margin_percentage()

        from .models import CachedRate
        try:
            cached = CachedRate.objects.get(asset=asset)
            updated_at = cached.updated_at.isoformat()
        except CachedRate.DoesNotExist:
            updated_at = None

        return RateResponseSchema(
            asset=asset,
            market_rate=market_rate,
            user_rate=user_rate,
            margin_percentage=margin,
            updated_at=updated_at,
        )
    except ValueError as e:
        raise HttpError(400, str(e))
    except Exception as e:
        raise HttpError(500, f'Failed to fetch rate: {str(e)}')
