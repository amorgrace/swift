from ninja import Router
from django.db.models import Sum
from django.utils import timezone
from .schemas import DashboardStatsSchema
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
