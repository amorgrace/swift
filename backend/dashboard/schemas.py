from pydantic import BaseModel
from decimal import Decimal
from typing import List, Optional

class MonthlyVolume(BaseModel):
    month: str
    amount: Decimal

class DashboardStatsSchema(BaseModel):
    totalWithdrawn: Decimal
    completedTrades: int
    volumeThisMonth: Decimal

class AdminDashboardStatsSchema(BaseModel):
    total_users: int
    total_kyc_pending: int
    total_system_ngn_balance: Decimal
    total_system_deposits: Decimal
    total_system_withdrawals: Decimal
    btc_address_count: int
    monthly_volume: Optional[List[MonthlyVolume]] = None
