from pydantic import BaseModel
from decimal import Decimal

class DashboardStatsSchema(BaseModel):
    totalWithdrawn: Decimal
    completedTrades: int
    volumeThisMonth: Decimal
