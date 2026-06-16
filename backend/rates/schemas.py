from decimal import Decimal
from typing import Optional

from pydantic import BaseModel
from ninja import Schema


class RateResponseSchema(BaseModel):
    """Schema for a single asset rate."""
    asset: str
    market_rate: Optional[Decimal] = None
    user_rate: Optional[Decimal] = None
    market_ngn_usd_rate: Optional[Decimal] = None
    user_ngn_usd_rate: Optional[Decimal] = None
    margin_percentage: Decimal
    updated_at: Optional[str] = None

class SystemSettingsSchema(BaseModel):
    conversion_margin_percentage: Decimal

class GiftCardSchema(Schema):
    id: int
    brand: str
    category: str
    color: str
    bg: str
    denominations: list[str]
    rates: dict[str, float]
    rate_per_dollar: Decimal
    country: str
    popular: bool

class GiftCardCreateSchema(Schema):
    brand: str
    category: str
    color: str = "#FFFFFF"
    bg: str = "linear-gradient(135deg, #1a1a1a, #000000)"
    denominations: list[str] = []
    rates: dict[str, float] = {}
    rate_per_dollar: Decimal
    country: str
    popular: bool = False

class GiftCardUpdateSchema(Schema):
    brand: Optional[str] = None
    category: Optional[str] = None
    color: Optional[str] = None
    bg: Optional[str] = None
    denominations: Optional[list[str]] = None
    rates: Optional[dict[str, float]] = None
    rate_per_dollar: Optional[Decimal] = None
    country: Optional[str] = None
    popular: Optional[bool] = None
