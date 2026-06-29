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
    ref: str
    bank: Optional[str] = None
    coin: Optional[str] = None
    network: Optional[str] = None
    crypto_amount: Optional[Decimal] = None
    rate: Optional[Decimal] = None

class AdminTransactionSchema(TransactionSchema):
    user_email: str
    user_full_name: str





class DashboardStatsSchema(BaseModel):
    current_balance: Decimal
    total_deposit_amount: Decimal
    total_withdrawal_amount: Decimal
    deposit_count: int
    withdrawal_count: int

class AdminWithdrawalSchema(BaseModel):
    id: int
    user_email: str
    user_id: int
    asset: str
    amount: Decimal
    status: str
    bank_name: str
    bank_account_name: str
    bank_account_number: str
    wallet_address: str
    network: str
    created_at: str


