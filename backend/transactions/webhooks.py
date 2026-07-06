import json
import logging
from ninja import Router
from ninja.errors import HttpError
from django.http import HttpResponse

from .services import DepositService, WithdrawalService

logger = logging.getLogger(__name__)

router = Router(tags=['Webhooks'])

# Paystack webhook removed

@router.post('/alchemy-deposit/', auth=None)
def alchemy_deposit_webhook(request):
    """
    Alchemy Address Activity Webhook.
    """
    from wallets.alchemy import verify_alchemy_signature
    
    if not verify_alchemy_signature(request):
        logger.warning("Invalid Alchemy webhook signature")
        raise HttpError(401, "Invalid signature")

    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        raise HttpError(400, "Invalid JSON payload")

    DepositService.process_alchemy_deposit(payload)
    return HttpResponse(status=200)


@router.post('/blockcypher-deposit/', auth=None)
def blockcypher_deposit_webhook(request):
    """
    Blockcypher Transaction Webhook.
    """
    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        raise HttpError(400, "Invalid JSON payload")

    DepositService.process_blockcypher_deposit(payload)
    return HttpResponse(status=200)

