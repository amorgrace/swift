from pydantic import BaseModel, Field
from typing import Optional, List
from decimal import Decimal


class DepositSchema(BaseModel):
    id: int
    asset: str
    network: str
    crypto_amount: Decimal
    rate_applied: Decimal
    ngn_amount: Decimal
    status: str
    created_at: str


class WithdrawalRequestSchema(BaseModel):
    bank_account_id: int
    amount: Decimal = Field(..., gt=0, examples=[1000.00])
    pin: str = Field(..., min_length=4, max_length=4, examples=["1234"])


class WithdrawalSchema(BaseModel):
    id: int
    amount: Decimal
    fee: Decimal
    bank_account_name: str
    account_number: str
    status: str
    created_at: str


class TransactionSchema(BaseModel):
    id: int
    type: str
    amount: Decimal
    description: str
    status: str
    created_at: str





class DashboardStatsSchema(BaseModel):
    current_balance: Decimal
    total_deposit_amount: Decimal
    total_withdrawal_amount: Decimal
    deposit_count: int
    withdrawal_count: int
