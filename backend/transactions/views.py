from ninja import Router, Query
from ninja.errors import HttpError
from typing import List, Optional

from pydantic import BaseModel

from .schemas import (
    WithdrawalRequestSchema,
    WithdrawalSchema,
    TransactionSchema,
    TransactionListSchema,
    DepositSchema
)
from .services import WithdrawalService
from .models import Transaction, Deposit, Withdrawal
from wallets.models import NGNWallet

router = Router(tags=['Transactions'])


class PaginationFilters(BaseModel):
    limit: int = 20
    offset: int = 0
    type: Optional[str] = None


@router.post('/withdraw', response={200: dict})
def request_withdrawal(request, payload: WithdrawalRequestSchema):
    """Request an NGN withdrawal to a linked bank account."""
    try:
        result = WithdrawalService.request_withdrawal(
            user=request.user,
            bank_account_id=payload.bank_account_id,
            amount=payload.amount,
            pin=payload.pin
        )
        return result
    except ValueError as e:
        raise HttpError(400, str(e))
    except Exception as e:
        raise HttpError(500, str(e))


@router.get('/', response=TransactionListSchema)
def get_transactions(request, filters: PaginationFilters = Query(...)):
    """Get user's transaction history."""
    try:
        wallet = NGNWallet.objects.get(user=request.user)
    except NGNWallet.DoesNotExist:
        return TransactionListSchema(items=[], total=0)

    qs = Transaction.objects.filter(wallet=wallet)
    if filters.type:
        qs = qs.filter(type=filters.type)

    total = qs.count()
    items = qs[filters.offset : filters.offset + filters.limit]

    return TransactionListSchema(
        items=[
            TransactionSchema(
                id=t.id,
                type=t.type,
                amount=t.amount,
                description=t.description,
                status=t.status,
                created_at=t.created_at.isoformat()
            ) for t in items
        ],
        total=total
    )


@router.get('/deposits', response=List[DepositSchema])
def get_deposits(request, limit: int = 20, offset: int = 0):
    """Get user's deposit history."""
    try:
        wallet = NGNWallet.objects.get(user=request.user)
    except NGNWallet.DoesNotExist:
        return []

    deposits = Deposit.objects.filter(wallet=wallet)[offset : offset + limit]
    return [
        DepositSchema(
            id=d.id,
            asset=d.asset,
            network=d.network,
            crypto_amount=d.crypto_amount,
            rate_applied=d.rate_applied,
            ngn_amount=d.ngn_amount,
            status=d.status,
            created_at=d.created_at.isoformat()
        ) for d in deposits
    ]


@router.get('/withdrawals', response=List[WithdrawalSchema])
def get_withdrawals(request, limit: int = 20, offset: int = 0):
    """Get user's withdrawal history."""
    try:
        wallet = NGNWallet.objects.get(user=request.user)
    except NGNWallet.DoesNotExist:
        return []

    withdrawals = Withdrawal.objects.filter(wallet=wallet).select_related('bank_account')[offset : offset + limit]
    return [
        WithdrawalSchema(
            id=w.id,
            amount=w.amount,
            fee=w.fee,
            bank_account_name=w.bank_account.bank_name,
            account_number=w.bank_account.account_number,
            status=w.status,
            created_at=w.created_at.isoformat()
        ) for w in withdrawals
    ]
