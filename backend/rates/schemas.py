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
    ngn_usd_buy_rate: Decimal

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
    use_auto_rate: bool
    rate_multiplier: Decimal

class GiftCardCreateSchema(Schema):
    brand: str
    category: str
    color: str = "#FFFFFF"
    bg: str = "linear-gradient(135deg, #1a1a1a, #000000)"
    denominations: list[str] = []
    rates: dict[str, float] = {}
    rate_per_dollar: Decimal = Decimal("0.00")
    country: str
    popular: bool = False
    use_auto_rate: bool = True
    rate_multiplier: Decimal = Decimal("0.9000")

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
    use_auto_rate: Optional[bool] = None
    rate_multiplier: Optional[Decimal] = None


# ── Gift Card Transaction Schemas ──────────────────────────────────────────────

class RejectionReasonSchema(Schema):
    id: int
    code: str
    label: str
    description: str
    is_active: bool


class GiftCardTransactionSubmitSchema(Schema):
    """Payload sent by the user when submitting a gift card for sale."""
    brand: str
    country_code: str
    currency_symbol: str
    denomination: Decimal
    rate_applied: Decimal
    ngn_payout: Decimal
    image_url: str
    card_code: str = ""


class GiftCardTransactionOutSchema(Schema):
    id: int
    reference: str
    brand: str
    country_code: str
    currency_symbol: str
    denomination: Decimal
    rate_applied: Decimal
    ngn_payout: Decimal
    image_url: str
    card_code: str
    status: str
    rejection_reason: Optional[RejectionReasonSchema] = None
    created_at: str
    reviewed_at: Optional[str] = None

    @staticmethod
    def resolve_created_at(obj):
        return obj.created_at.isoformat()

    @staticmethod
    def resolve_reviewed_at(obj):
        return obj.reviewed_at.isoformat() if obj.reviewed_at else None


class AdminGiftCardTransactionOutSchema(GiftCardTransactionOutSchema):
    """Extends user view with user info for admin listing."""
    user_email: str
    user_full_name: str

    @staticmethod
    def resolve_user_email(obj):
        return obj.user.email

    @staticmethod
    def resolve_user_full_name(obj):
        return getattr(obj.user, 'full_name', '') or obj.user.email


class AdminApproveSchema(Schema):
    """No payload needed — just call the endpoint."""
    pass


class AdminRejectSchema(Schema):
    reason_id: int

