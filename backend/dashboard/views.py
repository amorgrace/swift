from ninja import Router
from django.db.models import Sum
from django.utils import timezone
from .schemas import DashboardStatsSchema, AdminDashboardStatsSchema
from wallets.models import NGNWallet
from transactions.models import Deposit, Withdrawal, DepositStatus, WithdrawalStatus

router = Router(tags=['Dashboard'])

@router.get('/stats', response=DashboardStatsSchema)
def get_dashboard_stats(request):
    """Get overall dashboard statistics for the user."""
    try:
        wallet = NGNWallet.objects.get(user=request.user)
    except NGNWallet.DoesNotExist:
        return DashboardStatsSchema(
            totalWithdrawn=0,
            completedTrades=0,
            volumeThisMonth=0
        )

    # totalWithdrawn: Sum of successful withdrawals
    withdrawals = Withdrawal.objects.filter(wallet=wallet, status=WithdrawalStatus.SUCCESS)
    total_withdrawn = withdrawals.aggregate(Sum('amount'))['amount__sum'] or 0

    # completedTrades: Count of converted deposits
    completed_trades = Deposit.objects.filter(wallet=wallet, status=DepositStatus.CONVERTED).count()

    # volumeThisMonth: Sum of converted deposits in the current month
    now = timezone.now()
    deposits_this_month = Deposit.objects.filter(
        wallet=wallet,
        status=DepositStatus.CONVERTED,
        created_at__year=now.year,
        created_at__month=now.month
    )
    volume_this_month = deposits_this_month.aggregate(Sum('ngn_amount'))['ngn_amount__sum'] or 0

    return DashboardStatsSchema(
        totalWithdrawn=total_withdrawn,
        completedTrades=completed_trades,
        volumeThisMonth=volume_this_month
    )


@router.get('/admin/stats', response=AdminDashboardStatsSchema)
def get_admin_dashboard_stats(request):
    """Get global dashboard statistics for the admin."""
    if not request.user.is_staff:
        from ninja.errors import HttpError
        raise HttpError(403, "Permission denied.")
        
    from django.contrib.auth import get_user_model
    from kyc.models import KYCVerification, KYCStatus
    from decimal import Decimal
    from wallets.models import DepositAddress, NetworkChoices
    
    User = get_user_model()
    
    total_users = User.objects.count()
    total_kyc_pending = KYCVerification.objects.filter(status=KYCStatus.SUBMITTED).count()
    
    total_ngn_balance = NGNWallet.objects.aggregate(Sum('balance'))['balance__sum'] or Decimal('0.00')
    
    deposits = Deposit.objects.filter(status=DepositStatus.CONVERTED)
    total_system_deposits = deposits.aggregate(Sum('ngn_amount'))['ngn_amount__sum'] or Decimal('0.00')
    
    withdrawals = Withdrawal.objects.filter(status=WithdrawalStatus.SUCCESS)
    total_system_withdrawals = withdrawals.aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')
    
    btc_address_count = DepositAddress.objects.filter(network=NetworkChoices.BITCOIN).count()
    
    return AdminDashboardStatsSchema(
        total_users=total_users,
        total_kyc_pending=total_kyc_pending,
        total_system_ngn_balance=total_ngn_balance,
        total_system_deposits=total_system_deposits,
        total_system_withdrawals=total_system_withdrawals,
        btc_address_count=btc_address_count
    )
