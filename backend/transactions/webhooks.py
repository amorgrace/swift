import json
import logging
from ninja import Router
from ninja.errors import HttpError
from django.http import HttpResponse

from .services import DepositService, WithdrawalService
from wallets.services import PaystackService

logger = logging.getLogger(__name__)

router = Router(tags=['Webhooks'])


@router.post('/paystack', auth=None)
def paystack_webhook(request):
    """Webhook endpoint for Paystack events (e.g., transfers)."""
    
    # Verify Paystack signature
    if not PaystackService.verify_webhook_signature(request):
        logger.warning("Invalid Paystack webhook signature")
        raise HttpError(401, "Invalid signature")

    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        raise HttpError(400, "Invalid JSON payload")

    event = payload.get('event')

    if event in ['transfer.success', 'transfer.failed', 'transfer.reversed']:
        WithdrawalService.process_paystack_webhook(payload)
    else:
        logger.info(f"Ignored Paystack webhook event: {event}")

    # Always return 200 to acknowledge receipt
    return HttpResponse(status=200)


@router.post('/tatum-deposit/', auth=None)
def tatum_deposit_webhook(request):
    """
    Tatum fires this when crypto arrives at a monitored address.
    Idempotent: duplicate tx_hash is silently ignored.
    Synchronous: no Celery needed. Tatum retries on non-2xx.
    """
    from wallets.tatum import verify_tatum_signature
    
    if not verify_tatum_signature(request):
        logger.warning("Invalid Tatum webhook signature")
        raise HttpError(401, "Invalid signature")

    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        raise HttpError(400, "Invalid JSON payload")

    DepositService.process_tatum_deposit(payload)
    return HttpResponse(status=200)

