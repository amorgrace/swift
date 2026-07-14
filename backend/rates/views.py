from decimal import Decimal, ROUND_DOWN

from ninja import Router
from ninja.errors import HttpError
from django_ratelimit.decorators import ratelimit
from django.shortcuts import get_object_or_404
from django.utils import timezone

from .schemas import (
    RateResponseSchema, SystemSettingsSchema,
    GiftCardSchema, GiftCardCreateSchema, GiftCardUpdateSchema,
    RejectionReasonSchema, GiftCardTransactionSubmitSchema,
    GiftCardTransactionOutSchema, AdminGiftCardTransactionOutSchema,
    AdminRejectSchema,
)
from .services import RateService
from .models import AssetChoices, SystemSettings, GiftCard, GiftCardTransaction, GiftCardTransactionStatus, RejectionReason

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
    settings = SystemSettings.get_settings()
    buy_rate = settings.ngn_usd_buy_rate
    cards = GiftCard.objects.all().values(
        'id', 'brand', 'category', 'color', 'bg',
        'denominations', 'rates', 'rate_per_dollar', 'country', 'popular',
        'use_auto_rate', 'rate_multiplier'
    )
    result = []
    for card in cards:
        if card['use_auto_rate'] and buy_rate > 0:
            card['rate_per_dollar'] = (buy_rate * card['rate_multiplier']).quantize(Decimal('0.01'), rounding=ROUND_DOWN)
        result.append(card)
    return result

@router.post('/admin/giftcards', response=GiftCardSchema)
def create_giftcard(request, payload: GiftCardCreateSchema):
    """Create a new gift card configuration (Admin only)."""
    if not request.user.is_staff:
        raise HttpError(403, "Permission denied.")
    giftcard = GiftCard.objects.create(**payload.dict())
    
    settings = SystemSettings.get_settings()
    buy_rate = settings.ngn_usd_buy_rate
    card = GiftCard.objects.filter(id=giftcard.id).values(
        'id', 'brand', 'category', 'color', 'bg',
        'denominations', 'rates', 'rate_per_dollar', 'country', 'popular',
        'use_auto_rate', 'rate_multiplier'
    ).first()
    if card and card['use_auto_rate'] and buy_rate > 0:
        card['rate_per_dollar'] = (buy_rate * card['rate_multiplier']).quantize(Decimal('0.01'), rounding=ROUND_DOWN)
    return card

@router.put('/admin/giftcards/{giftcard_id}', response=GiftCardSchema)
@router.patch('/admin/giftcards/{giftcard_id}', response=GiftCardSchema)
def update_giftcard(request, giftcard_id: int, payload: GiftCardUpdateSchema):
    """Update a gift card configuration (Admin only)."""
    if not request.user.is_staff:
        raise HttpError(403, "Permission denied.")
    giftcard = get_object_or_404(GiftCard, id=giftcard_id)
    for attr, value in payload.dict(exclude_unset=True).items():
        setattr(giftcard, attr, value)
    giftcard.save()
    
    settings = SystemSettings.get_settings()
    buy_rate = settings.ngn_usd_buy_rate
    card = GiftCard.objects.filter(id=giftcard.id).values(
        'id', 'brand', 'category', 'color', 'bg',
        'denominations', 'rates', 'rate_per_dollar', 'country', 'popular',
        'use_auto_rate', 'rate_multiplier'
    ).first()
    if card and card['use_auto_rate'] and buy_rate > 0:
        card['rate_per_dollar'] = (buy_rate * card['rate_multiplier']).quantize(Decimal('0.01'), rounding=ROUND_DOWN)
    return card

@router.delete('/admin/giftcards/{giftcard_id}')
def delete_giftcard(request, giftcard_id: int):
    """Delete a gift card configuration (Admin only)."""
    if not request.user.is_staff:
        raise HttpError(403, "Permission denied.")
    giftcard = get_object_or_404(GiftCard, id=giftcard_id)
    giftcard.delete()
    return {"success": True}


# ── Gift Card Transaction (Sell) Endpoints ─────────────────────────────────────

@router.post('/sell/', response=GiftCardTransactionOutSchema)
def submit_giftcard_sell(request, payload: GiftCardTransactionSubmitSchema):
    """User submits a gift card for manual review. Image URL comes from Cloudinary."""
    from wallets.models import NGNWallet
    try:
        wallet = NGNWallet.objects.get(user=request.user)
    except NGNWallet.DoesNotExist:
        raise HttpError(404, "Wallet not found. Please contact support.")

    tx = GiftCardTransaction.objects.create(
        user=request.user,
        wallet=wallet,
        brand=payload.brand,
        country_code=payload.country_code,
        currency_symbol=payload.currency_symbol,
        denomination=payload.denomination,
        rate_applied=payload.rate_applied,
        ngn_payout=payload.ngn_payout,
        image_url=payload.image_url,
        card_code=payload.card_code,
    )

    # Create pending Transaction for user history
    from transactions.models import Transaction, TransactionType
    from decimal import Decimal
    Transaction.objects.create(
        wallet=wallet,
        type=TransactionType.DEPOSIT,
        amount=Decimal(str(payload.ngn_payout)),
        description=f"Trade {payload.brand} {payload.currency_symbol}{payload.denomination} Gift Card",
        status='pending',
        related_giftcard=tx
    )

    # Fire admin notifications
    from notifications.tasks import send_telegram_task
    admin_msg = (
        f"🚨 <b>New Gift Card Submission</b> 🚨\n\n"
        f"👤 <b>User:</b> {request.user.email}\n"
        f"💳 <b>Brand:</b> {payload.brand} ({payload.country_code})\n"
        f"💰 <b>Denomination:</b> {payload.currency_symbol}{payload.denomination}\n"
        f"💱 <b>Expected Payout:</b> ₦{payload.ngn_payout:,.2f}\n"
        f"🔗 <b>Ref:</b> {tx.reference}\n\n"
        f"Please review in the Admin Panel."
    )
    send_telegram_task.delay(admin_msg)

    from notifications.tasks import send_email_task
    from django.conf import settings
    # Send email to admin (using a default admin email or settings.DEFAULT_FROM_EMAIL)
    admin_email = getattr(settings, 'ADMIN_EMAIL', 'admin@swiftradeapp.com')
    send_email_task.delay(
        subject=f"New Gift Card Submission - {tx.reference}",
        recipient_list=[admin_email],
        template_name='emails/admin_notification.html',
        context={
            'title': 'New Gift Card Submission',
            'message': f"User {request.user.email} submitted a {payload.brand} {payload.currency_symbol}{payload.denomination} gift card for review."
        }
    )

    return tx


@router.get('/my-transactions/', response=list[GiftCardTransactionOutSchema])
def get_my_giftcard_transactions(request):
    """Get the authenticated user's gift card sell history."""
    return GiftCardTransaction.objects.filter(
        user=request.user
    ).select_related('rejection_reason')


# ── Admin Gift Card Transaction Endpoints ──────────────────────────────────────

@router.get('/admin/transactions/', response=list[AdminGiftCardTransactionOutSchema])
def admin_list_transactions(request, status: str = ""):
    """List all gift card transactions. Filter by status: pending|approved|rejected."""
    if not request.user.is_staff:
        raise HttpError(403, "Permission denied.")
    qs = GiftCardTransaction.objects.select_related('user', 'rejection_reason', 'wallet')
    if status in ('pending', 'approved', 'rejected'):
        qs = qs.filter(status=status)
    return qs


@router.get('/admin/transactions/{tx_id}/', response=AdminGiftCardTransactionOutSchema)
def admin_get_transaction(request, tx_id: int):
    """Get a single gift card transaction (Admin only)."""
    if not request.user.is_staff:
        raise HttpError(403, "Permission denied.")
    tx = get_object_or_404(
        GiftCardTransaction.objects.select_related('user', 'rejection_reason', 'wallet'),
        id=tx_id,
    )
    return tx


@router.post('/admin/transactions/{tx_id}/approve/')
def admin_approve_transaction(request, tx_id: int):
    """
    Approve a gift card transaction (Admin only).
    Credits the user's NGN wallet atomically and fires a notification.
    """
    if not request.user.is_staff:
        raise HttpError(403, "Permission denied.")

    from django.db import transaction as db_transaction
    from notifications.models import Notification
    from decimal import Decimal

    tx = get_object_or_404(GiftCardTransaction, id=tx_id)

    if tx.status != GiftCardTransactionStatus.PENDING:
        raise HttpError(400, f"Transaction is already {tx.status}.")

    with db_transaction.atomic():
        # Credit the wallet
        wallet = tx.wallet
        wallet.credit(Decimal(str(tx.ngn_payout)))

        # Update transaction status
        tx.status = GiftCardTransactionStatus.APPROVED
        tx.reviewed_by = request.user
        tx.reviewed_at = timezone.now()
        tx.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'updated_at'])

        # Update the unified Transaction for user history
        from transactions.models import Transaction, TransactionType
        user_tx = Transaction.objects.filter(related_giftcard=tx).first()
        if user_tx:
            user_tx.status = 'success'
            user_tx.save(update_fields=['status'])
        else:
            # Fallback for legacy records
            Transaction.objects.create(
                wallet=wallet,
                type=TransactionType.DEPOSIT,
                amount=Decimal(str(tx.ngn_payout)),
                description=f"Trade {tx.brand} {tx.currency_symbol}{tx.denomination} Gift Card",
                status='success',
                related_giftcard=tx
            )

        # Fire in-app notification
        Notification.objects.create(
            user=tx.user,
            type='giftcard',
            title='Gift Card Approved 🎉',
            body=(
                f"Your {tx.brand} {tx.currency_symbol}{tx.denomination} gift card "
                f"(Ref: {tx.reference}) has been approved. "
                f"₦{tx.ngn_payout:,.2f} has been credited to your wallet."
            ),
        )

    return {"success": True, "reference": tx.reference, "ngn_credited": str(tx.ngn_payout)}


@router.post('/admin/transactions/{tx_id}/reject/')
def admin_reject_transaction(request, tx_id: int, payload: AdminRejectSchema):
    """
    Reject a gift card transaction with a predefined reason (Admin only).
    Sends a notification to the user with the reason.
    """
    if not request.user.is_staff:
        raise HttpError(403, "Permission denied.")

    from notifications.models import Notification

    tx = get_object_or_404(GiftCardTransaction, id=tx_id)

    if tx.status != GiftCardTransactionStatus.PENDING:
        raise HttpError(400, f"Transaction is already {tx.status}.")

    reason = get_object_or_404(RejectionReason, id=payload.reason_id, is_active=True)

    tx.status = GiftCardTransactionStatus.REJECTED
    tx.rejection_reason = reason
    tx.reviewed_by = request.user
    tx.reviewed_at = timezone.now()
    tx.save(update_fields=['status', 'rejection_reason', 'reviewed_by', 'reviewed_at', 'updated_at'])

    # Update the unified Transaction for user history
    from transactions.models import Transaction
    user_tx = Transaction.objects.filter(related_giftcard=tx).first()
    if user_tx:
        user_tx.status = 'failed'
        user_tx.save(update_fields=['status'])

    Notification.objects.create(
        user=tx.user,
        type='giftcard',
        title='Gift Card Not Accepted',
        body=(
            f"Your {tx.brand} {tx.currency_symbol}{tx.denomination} gift card "
            f"(Ref: {tx.reference}) could not be processed. "
            f"Reason: {reason.label}. "
            f"Please contact support if you need assistance."
        ),
    )

    return {"success": True, "reference": tx.reference, "reason": reason.label}


@router.get('/admin/rejection-reasons/', response=list[RejectionReasonSchema])
def admin_list_rejection_reasons(request):
    """Get all active rejection reasons for the admin dropdown."""
    if not request.user.is_staff:
        raise HttpError(403, "Permission denied.")
    return RejectionReason.objects.filter(is_active=True)

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
