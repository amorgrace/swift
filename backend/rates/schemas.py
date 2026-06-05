from decimal import Decimal
from typing import Optional

from pydantic import BaseModel


class RateResponseSchema(BaseModel):
    """Schema for a single asset rate."""
    asset: str
    market_rate: Optional[Decimal] = None
    user_rate: Optional[Decimal] = None
    market_ngn_usd_rate: Optional[Decimal] = None
    user_ngn_usd_rate: Optional[Decimal] = None
    margin_percentage: Decimal
    updated_at: Optional[str] = None
