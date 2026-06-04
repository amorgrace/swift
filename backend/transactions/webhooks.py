import json
import logging
from ninja import Router
from ninja.errors import HttpError
from django.http import HttpResponse

from .services import DepositService, WithdrawalService
from wallets.services import PaystackService, QuidaxService

logger = logging.getLogger(__name__)

router = Router(tags=['Webhooks'])


@router.post('/quidax', auth=None)
def quidax_webhook(request):
    """Webhook endpoint for Quidax events (e.g., crypto deposits)."""
    
    # In a real scenario, you'd verify the Quidax signature here
    # if not QuidaxService.verify_webhook_signature(request):
    #     raise HttpError(401, "Invalid signature")
        
    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        raise HttpError(400, "Invalid JSON payload")

    event = payload.get('event')
    data = payload.get('data', {})

    if event == 'deposit.successful':
        DepositService.process_deposit_webhook(data)
    else:
        logger.info(f"Ignored Quidax webhook event: {event}")

    # Always return 200 to acknowledge receipt
    return HttpResponse(status=200)


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
