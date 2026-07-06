from ninja import Router, Query
from ninja.errors import HttpError
from ninja.pagination import paginate, PageNumberPagination
from typing import List, Optional
from datetime import datetime

from django.db.models import Sum
from django_ratelimit.decorators import ratelimit

from pydantic import BaseModel

from .schemas import (
    WithdrawalRequestSchema,
    WithdrawalSchema,
    TransactionSchema,
    AdminTransactionSchema,
    DepositSchema,
    DashboardStatsSchema,
    AdminWithdrawalSchema
)
from .services import WithdrawalService
from .models import Transaction, Deposit, Withdrawal, DepositStatus, WithdrawalStatus, TransactionType
from wallets.models import NGNWallet
from notifications.tasks import send_email_task, send_telegram_task, create_notification_task

router = Router(tags=['Transactions'])


class TransactionFilterSchema(BaseModel):
    type: Optional[str] = None


@router.post('/withdraw', response={200: dict})
@ratelimit(key='user', rate='5/m', block=True)
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
            # Prefer the user-friendly NGN/USD rate (e.g. 1370) stored at trade time.
            # Fall back to rate_applied (per-coin NGN rate) for older records.
            rate = d.ngn_usd_rate if d.ngn_usd_rate else d.rate_applied
        elif t.type == TransactionType.WITHDRAWAL and t.related_withdrawal:
            w = t.related_withdrawal
            acc_num = w.bank_account.account_number
            masked = acc_num[-4:] if len(acc_num) >= 4 else acc_num
            bank = f"{w.bank_account.bank_name} ••{masked}"
            rate = None
            
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
            crypto_amount=crypto_amount,
            rate=rate
        ))

    return results


@router.get('/admin/all', response=List[AdminTransactionSchema])
@paginate(PageNumberPagination, page_size=50)
def get_all_transactions_admin(request, filters: TransactionFilterSchema = Query(...)):
    """Admin endpoint to list all transactions globally."""
    if not request.user.is_staff:
        raise HttpError(403, "Permission denied.")
        
    qs = Transaction.objects.select_related(
        'wallet__user',
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
            # Prefer the user-friendly NGN/USD rate (e.g. 1370) stored at trade time.
            # Fall back to rate_applied (per-coin NGN rate) for older records.
            rate = d.ngn_usd_rate if d.ngn_usd_rate else d.rate_applied
        elif t.type == TransactionType.WITHDRAWAL and t.related_withdrawal:
            w = t.related_withdrawal
            acc_num = w.bank_account.account_number
            masked = acc_num[-4:] if len(acc_num) >= 4 else acc_num
            bank = f"{w.bank_account.bank_name} ••{masked}"
            rate = None
            
        results.append(AdminTransactionSchema(
            id=t.id,
            type=mapped_type,
            amount=t.amount,
            description=t.description,
            status=t.status.lower(),
            created_at=t.created_at.isoformat(),
            ref=t.reference,
            bank=bank,
            coin=coin,
            network=network,
            crypto_amount=crypto_amount,
            rate=rate,
            user_email=t.wallet.user.email,
            user_full_name=t.wallet.user.full_name
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

    deposits = Deposit.objects.filter(wallet=wallet).prefetch_related('transaction_set').order_by('-created_at')
    
    res = []
    for d in deposits:
        tx = d.transaction_set.first()
        ref = tx.reference if tx else f"TRD-{d.id}"
        res.append(DepositSchema(
            id=d.id,
            asset=d.asset,
            network=d.network,
            crypto_amount=d.crypto_amount,
            rate_applied=d.ngn_usd_rate if d.ngn_usd_rate else d.rate_applied,
            ngn_amount=d.ngn_amount,
            status=d.status,
            created_at=d.created_at.isoformat(),
            reference=ref
        ))
    return res


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

@router.get('/admin/withdrawals', response=List[AdminWithdrawalSchema])
@paginate(PageNumberPagination, page_size=20)
def get_admin_withdrawals(request, status: str = None):
    """Admin endpoint to list all withdrawals."""
    if not request.user.is_staff:
        raise HttpError(403, "Permission denied.")
        
    qs = Withdrawal.objects.select_related('wallet__user', 'bank_account').order_by('-created_at')
    
    if status and status != 'all':
        qs = qs.filter(status=status)

    results = []
    for w in qs:
        results.append(AdminWithdrawalSchema(
            id=w.id,
            user_email=w.wallet.user.email,
            user_id=str(w.wallet.user.id),
            asset="NGN",
            amount=w.amount,
            status=w.status.lower(),
            bank_name=w.bank_account.bank_name,
            bank_account_name=w.bank_account.account_name,
            bank_account_number=w.bank_account.account_number,
            wallet_address="",
            network="",
            created_at=w.created_at.isoformat()
        ))

    return results


@router.post('/admin/withdrawals/{withdrawal_id}/approve', response={200: dict})
def approve_withdrawal(request, withdrawal_id: int):
    """Admin endpoint to approve a pending withdrawal."""
    if not request.user.is_staff:
        raise HttpError(403, "Permission denied.")
    
    from django.db import transaction
    with transaction.atomic():
        withdrawal = Withdrawal.objects.select_for_update().get(id=withdrawal_id)
        if withdrawal.status != WithdrawalStatus.PENDING:
            raise HttpError(400, "Withdrawal is not pending.")
        
        withdrawal.status = WithdrawalStatus.SUCCESS
        withdrawal.save()
        
        txn_log = Transaction.objects.get(related_withdrawal=withdrawal)
        txn_log.status = WithdrawalStatus.SUCCESS
        txn_log.save()
        
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    send_email_task.delay(
        to_email=withdrawal.wallet.user.email,
        to_name=withdrawal.wallet.user.full_name,
        subject="SwiftTrade \u2013 Withdrawal Completed",
        template_name="emails/withdrawal_completed.html",
        context={
            "full_name": withdrawal.wallet.user.full_name,
            "amount": f"{withdrawal.amount:,.2f}",
            "bank_name": withdrawal.bank_account.bank_name,
            "account_number": withdrawal.bank_account.account_number,
            "timestamp": timestamp,
        },
    )
    
    create_notification_task.delay(
        user_id=withdrawal.wallet.user.id,
        notification_type='withdrawal',
        title='Withdrawal Approved',
        body=f'Your withdrawal of ₦{withdrawal.amount:,.2f} to {withdrawal.bank_account.bank_name} has been approved and processed.'
    )
    
    telegram_msg = (
        "\u2705 <b>WITHDRAWAL APPROVED</b>\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        f"\U0001f464 <b>User:</b> {withdrawal.wallet.user.full_name} ({withdrawal.wallet.user.email})\n"
        f"\U0001f4b5 <b>Amount:</b> \u20a6{withdrawal.amount:,.2f}\n"
        f"\U0001f3e6 <b>Bank:</b> {withdrawal.bank_account.bank_name} \u2014 <code>{withdrawal.bank_account.account_number}</code>\n"
        f"\U0001f517 <b>Ref:</b> <code>{withdrawal.paystack_reference}</code>\n"
        f"\u23f0 {timestamp}"
    )
    send_telegram_task.delay(telegram_msg)
    
    return {"message": "Withdrawal approved successfully."}

@router.post('/admin/withdrawals/{withdrawal_id}/reject', response={200: dict})
def reject_withdrawal(request, withdrawal_id: int):
    """Admin endpoint to reject a pending withdrawal."""
    if not request.user.is_staff:
        raise HttpError(403, "Permission denied.")
        
    from django.db import transaction
    with transaction.atomic():
        withdrawal = Withdrawal.objects.select_for_update().get(id=withdrawal_id)
        if withdrawal.status != WithdrawalStatus.PENDING:
            raise HttpError(400, "Withdrawal is not pending.")
            
        withdrawal.status = WithdrawalStatus.FAILED
        withdrawal.save()
        
        txn_log = Transaction.objects.get(related_withdrawal=withdrawal)
        txn_log.status = WithdrawalStatus.FAILED
        txn_log.save()
        
        # Credit the user back
        withdrawal.wallet.credit(withdrawal.amount)
        
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    send_email_task.delay(
        to_email=withdrawal.wallet.user.email,
        to_name=withdrawal.wallet.user.full_name,
        subject="SwiftTrade \u2013 Withdrawal Rejected",
        template_name="emails/withdrawal_failed.html",
        context={
            "full_name": withdrawal.wallet.user.full_name,
            "amount": f"{withdrawal.amount:,.2f}",
            "bank_name": withdrawal.bank_account.bank_name,
            "timestamp": timestamp,
        },
    )
    
    create_notification_task.delay(
        user_id=withdrawal.wallet.user.id,
        notification_type='withdrawal',
        title='Withdrawal Rejected',
        body=f'Your withdrawal of ₦{withdrawal.amount:,.2f} has been rejected. Funds have been returned to your wallet.'
    )
    
    telegram_msg = (
        "\u274c <b>WITHDRAWAL REJECTED</b>\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        f"\U0001f464 <b>User:</b> {withdrawal.wallet.user.full_name} ({withdrawal.wallet.user.email})\n"
        f"\U0001f4b5 <b>Amount:</b> \u20a6{withdrawal.amount:,.2f}\n"
        f"\U0001f3e6 <b>Bank:</b> {withdrawal.bank_account.bank_name}\n"
        f"\U0001f517 <b>Ref:</b> <code>{withdrawal.paystack_reference}</code>\n"
        f"\u2757 <b>Reason:</b> Rejected by Admin\n"
        f"\u23f0 {timestamp}"
    )
    send_telegram_task.delay(telegram_msg)
    
    return {"message": "Withdrawal rejected and funds refunded."}
