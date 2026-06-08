from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from decimal import Decimal


class WalletResponseSchema(BaseModel):
    """Schema for user's NGN wallet balance."""
    balance: Decimal
    pin_is_set: bool
    created_at: str


class DepositAddressSchema(BaseModel):
    """Schema for a single deposit address."""
    network: str
    address: str


class DepositAddressesResponseSchema(BaseModel):
    """Schema for all user deposit addresses."""
    btc: Optional[List[DepositAddressSchema]] = None
    eth: Optional[List[DepositAddressSchema]] = None
    usdt: Optional[List[DepositAddressSchema]] = None
    usdc: Optional[List[DepositAddressSchema]] = None
    sol: Optional[List[DepositAddressSchema]] = None
    bnb: Optional[List[DepositAddressSchema]] = None


class BankAccountSchema(BaseModel):
    """Schema for a linked bank account."""
    id: int
    bank_name: str
    bank_code: str
    account_number: str
    account_name: str
    is_default: bool


class AddBankAccountSchema(BaseModel):
    """Schema for adding a new bank account."""
    bank_code: str = Field(..., examples=["058"])
    account_number: str = Field(..., examples=["0123456789"])


class ResolveAccountSchema(BaseModel):
    """Schema for resolving an account name before adding."""
    bank_code: str = Field(..., examples=["058"])
    account_number: str = Field(..., examples=["0123456789"])


class BankListSchema(BaseModel):
    """Schema for a bank in the list of supported banks."""
    name: str
    code: str


class SetTransactionPinSchema(BaseModel):
    """Schema for setting or updating transaction PIN."""
    pin: str = Field(..., min_length=4, max_length=4, examples=["1234"])
