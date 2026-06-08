from ninja import Router, Query
from ninja.errors import HttpError
from ninja.pagination import paginate, PageNumberPagination
from typing import List, Optional

from django.db.models import Sum

from pydantic import BaseModel

from .schemas import (
    WithdrawalRequestSchema,
    WithdrawalSchema,
    TransactionSchema,
    DepositSchema,
    DashboardStatsSchema
)
from .services import WithdrawalService
from .models import Transaction, Deposit, Withdrawal, DepositStatus, WithdrawalStatus, TransactionType
from wallets.models import NGNWallet

router = Router(tags=['Transactions'])


class TransactionFilterSchema(BaseModel):
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


@router.get('/', response=List[TransactionSchema])
@paginate(PageNumberPagination, page_size=10)
def get_transactions(request, filters: TransactionFilterSchema = Query(...)):
    """Get user's transaction history."""
    try:
        wallet = NGNWallet.objects.get(user=request.user)
    except NGNWallet.DoesNotExist:
        return []

    qs = Transaction.objects.filter(wallet=wallet).select_related(
        'related_deposit',
        'related_withdrawal__bank_account'
    ).order_by('-created_at')
    
    if filters.type:
        qs = qs.filter(type=filters.type)

    results = []
    for t in qs:
        mapped_type = 'trade' if t.type == TransactionType.DEPOSIT else 'withdrawal'
        
        bank = None
        coin = None
        network = None
        crypto_amount = None
        
        if t.type == TransactionType.DEPOSIT and t.related_deposit:
            d = t.related_deposit
            coin = d.asset.upper()
            network = d.network
            crypto_amount = d.crypto_amount
        elif t.type == TransactionType.WITHDRAWAL and t.related_withdrawal:
            w = t.related_withdrawal
            acc_num = w.bank_account.account_number
            masked = acc_num[-4:] if len(acc_num) >= 4 else acc_num
            bank = f"{w.bank_account.bank_name} ••{masked}"
            
        results.append(TransactionSchema(
            id=t.id,
            type=mapped_type,
            amount=t.amount,
            description=t.description,
            status=t.status.lower(),  # Ensure status is lowercase for frontend
            created_at=t.created_at.isoformat(),
            ref=t.reference,
            bank=bank,
            coin=coin,
            network=network,
            crypto_amount=crypto_amount
        ))

    return results


@router.get('/deposits', response=List[DepositSchema])
@paginate(PageNumberPagination, page_size=10)
def get_deposits(request):
    """Get user's deposit history."""
    try:
        wallet = NGNWallet.objects.get(user=request.user)
    except NGNWallet.DoesNotExist:
        return []

    deposits = Deposit.objects.filter(wallet=wallet).order_by('-created_at')
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
@paginate(PageNumberPagination, page_size=10)
def get_withdrawals(request):
    """Get user's withdrawal history."""
    try:
        wallet = NGNWallet.objects.get(user=request.user)
    except NGNWallet.DoesNotExist:
        return []

    withdrawals = Withdrawal.objects.filter(wallet=wallet).select_related('bank_account').order_by('-created_at')
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

@router.get('/stats', response=DashboardStatsSchema)
def get_dashboard_stats(request):
    """Get dashboard statistics for the user."""
    try:
        wallet = NGNWallet.objects.get(user=request.user)
    except NGNWallet.DoesNotExist:
        return DashboardStatsSchema(
            current_balance=0,
            total_deposit_amount=0,
            total_withdrawal_amount=0,
            deposit_count=0,
            withdrawal_count=0
        )

    # Calculate totals
    deposits = Deposit.objects.filter(wallet=wallet, status=DepositStatus.CONVERTED)
    total_deposit_amount = deposits.aggregate(Sum('ngn_amount'))['ngn_amount__sum'] or 0
    deposit_count = deposits.count()

    withdrawals = Withdrawal.objects.filter(wallet=wallet, status=WithdrawalStatus.SUCCESS)
    total_withdrawal_amount = withdrawals.aggregate(Sum('amount'))['amount__sum'] or 0
    withdrawal_count = withdrawals.count()

    return DashboardStatsSchema(
        current_balance=wallet.balance,
        total_deposit_amount=total_deposit_amount,
        total_withdrawal_amount=total_withdrawal_amount,
        deposit_count=deposit_count,
        withdrawal_count=withdrawal_count
    )
