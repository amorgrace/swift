from ninja import Router
from ninja.errors import HttpError
from django_ratelimit.decorators import ratelimit

from django.shortcuts import get_object_or_404

from .schemas import RateResponseSchema, SystemSettingsSchema, GiftCardSchema, GiftCardCreateSchema, GiftCardUpdateSchema
from .services import RateService
from .models import AssetChoices, SystemSettings, GiftCard

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
        rates = RateService.get_market_rates(asset)
        market_rate = rates['ngn']
        rate_usd = rates.get('usd')
        user_rate = RateService.get_user_rate(asset)
        margin = RateService.get_margin_percentage()
        
        from decimal import Decimal, ROUND_DOWN
        market_ngn_usd_rate = None
        user_ngn_usd_rate = None
        if rate_usd and rate_usd > Decimal('0'):
            market_ngn_usd_rate = (market_rate / rate_usd).quantize(Decimal('0.01'), rounding=ROUND_DOWN)
            usd_discount = market_ngn_usd_rate * (margin / Decimal('100'))
            user_ngn_usd_rate = (market_ngn_usd_rate - usd_discount).quantize(Decimal('0.01'), rounding=ROUND_DOWN)

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
            market_ngn_usd_rate=market_ngn_usd_rate,
            user_ngn_usd_rate=user_ngn_usd_rate,
            margin_percentage=margin,
            updated_at=updated_at,
        )
    except ValueError as e:
        raise HttpError(400, str(e))
    except Exception as e:
        raise HttpError(500, f'Failed to fetch rate: {str(e)}')


@router.get('/admin/settings', response=SystemSettingsSchema)
def get_system_settings(request):
    """Get system settings (Admin only)."""
    if not request.user.is_staff:
        raise HttpError(403, "Permission denied.")
    settings = SystemSettings.get_settings()
    return {
        "conversion_margin_percentage": settings.conversion_margin_percentage,
        "ngn_usd_buy_rate": settings.ngn_usd_buy_rate
    }


@router.post('/admin/settings', response=SystemSettingsSchema)
def update_system_settings(request, payload: SystemSettingsSchema):
    """Update system settings (Admin only)."""
    if not request.user.is_staff:
        raise HttpError(403, "Permission denied.")
    
    settings = SystemSettings.get_settings()
    settings.conversion_margin_percentage = payload.conversion_margin_percentage
    settings.ngn_usd_buy_rate = payload.ngn_usd_buy_rate
    settings.save()
    settings.refresh_from_db()
    return {
        "conversion_margin_percentage": settings.conversion_margin_percentage,
        "ngn_usd_buy_rate": settings.ngn_usd_buy_rate
    }

@router.get('/giftcards', response=list[GiftCardSchema], auth=None)
def get_all_giftcards(request):
    """Get all gift card configurations."""
    cards = GiftCard.objects.all().values(
        'id', 'brand', 'category', 'color', 'bg',
        'denominations', 'rates', 'rate_per_dollar', 'country', 'popular'
    )
    return list(cards)

@router.post('/admin/giftcards', response=GiftCardSchema)
def create_giftcard(request, payload: GiftCardCreateSchema):
    """Create a new gift card configuration (Admin only)."""
    if not request.user.is_staff:
        raise HttpError(403, "Permission denied.")
    giftcard = GiftCard.objects.create(**payload.dict())
    return GiftCard.objects.filter(id=giftcard.id).values(
        'id', 'brand', 'category', 'color', 'bg',
        'denominations', 'rates', 'rate_per_dollar', 'country', 'popular'
    ).first()

@router.put('/admin/giftcards/{giftcard_id}', response=GiftCardSchema)
def update_giftcard(request, giftcard_id: int, payload: GiftCardUpdateSchema):
    """Update a gift card configuration (Admin only)."""
    if not request.user.is_staff:
        raise HttpError(403, "Permission denied.")
    giftcard = get_object_or_404(GiftCard, id=giftcard_id)
    for attr, value in payload.dict(exclude_unset=True).items():
        setattr(giftcard, attr, value)
    giftcard.save()
    return GiftCard.objects.filter(id=giftcard.id).values(
        'id', 'brand', 'category', 'color', 'bg',
        'denominations', 'rates', 'rate_per_dollar', 'country', 'popular'
    ).first()

@router.delete('/admin/giftcards/{giftcard_id}')
def delete_giftcard(request, giftcard_id: int):
    """Delete a gift card configuration (Admin only)."""
    if not request.user.is_staff:
        raise HttpError(403, "Permission denied.")
    giftcard = get_object_or_404(GiftCard, id=giftcard_id)
    giftcard.delete()
    return {"success": True}
