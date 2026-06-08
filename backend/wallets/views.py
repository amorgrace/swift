from ninja import Router
from ninja.errors import HttpError
from typing import List, Dict

from .schemas import (
    WalletResponseSchema,
    DepositAddressesResponseSchema,
    DepositAddressSchema,
    BankAccountSchema,
    AddBankAccountSchema,
    ResolveAccountSchema,
    BankListSchema,
    SetTransactionPinSchema
)
from .services import WalletService, PaystackService
from .models import BankAccount, NGNWallet
from django_ratelimit.decorators import ratelimit

router = Router(tags=['Wallets'])


@router.get('/balance', response=WalletResponseSchema)
def get_balance(request):
    """Get the user's current NGN balance and PIN status."""
    try:
        return WalletService.get_balance(request.user)
    except ValueError as e:
        raise HttpError(404, str(e))
    except Exception as e:
        raise HttpError(500, str(e))


@router.get('/deposit-addresses', response=DepositAddressesResponseSchema)
def get_deposit_addresses(request):
    """Get all crypto deposit addresses for the user."""
    try:
        addresses = WalletService.get_deposit_addresses(request.user)
        return addresses
    except ValueError as e:
        raise HttpError(404, str(e))
    except Exception as e:
        raise HttpError(500, str(e))


@router.get('/banks', response=List[BankListSchema], auth=None)
@ratelimit(key='ip', rate='10/m', block=True)
def list_banks(request):
    """List all supported Nigerian banks from Paystack."""
    try:
        banks = PaystackService.list_banks()
        return [{'name': bank['name'], 'code': bank['code']} for bank in banks]
    except ValueError as e:
        raise HttpError(500, str(e))


@router.get('/bank-accounts', response=List[BankAccountSchema])
def get_bank_accounts(request):
    """List all linked bank accounts for the user."""
    accounts = BankAccount.objects.filter(user=request.user).order_by('-is_default', '-created_at')
    return [
        BankAccountSchema(
            id=acc.id,
            bank_name=acc.bank_name,
            bank_code=acc.bank_code,
            account_number=acc.account_number,
            account_name=acc.account_name,
            is_default=acc.is_default
        ) for acc in accounts
    ]


@router.post('/bank-accounts', response=BankAccountSchema)
def add_bank_account(request, payload: AddBankAccountSchema):
    """Link a new Nigerian bank account for withdrawals."""
    try:
        account = WalletService.add_bank_account(
            user=request.user,
            bank_code=payload.bank_code,
            account_number=payload.account_number
        )
        return BankAccountSchema(
            id=account.id,
            bank_name=account.bank_name,
            bank_code=account.bank_code,
            account_number=account.account_number,
            account_name=account.account_name,
            is_default=account.is_default
        )
    except ValueError as e:
        raise HttpError(400, str(e))
    except Exception as e:
        raise HttpError(500, str(e))


@router.post('/resolve-account', response={200: dict})
def resolve_account(request, payload: ResolveAccountSchema):
    """Verify an account number and get the account name before saving."""
    try:
        resolved = PaystackService.resolve_account(payload.account_number, payload.bank_code)
        return {'account_name': resolved.get('account_name', '')}
    except ValueError as e:
        raise HttpError(400, "Could not resolve bank account. Please check the details.")
    except Exception as e:
        raise HttpError(500, "An error occurred during account verification.")


@router.delete('/bank-accounts/{account_id}', response={200: dict})
def remove_bank_account(request, account_id: int):
    """Remove a linked bank account."""
    try:
        account = BankAccount.objects.get(id=account_id, user=request.user)
        account.delete()
        return {'message': 'Bank account removed successfully'}
    except BankAccount.DoesNotExist:
        raise HttpError(404, 'Bank account not found')
    except Exception as e:
        raise HttpError(500, str(e))


@router.post('/transaction-pin', response={200: dict})
def set_transaction_pin(request, payload: SetTransactionPinSchema):
    """Set or update the 4-digit transaction PIN for withdrawals."""
    try:
        wallet = NGNWallet.objects.get(user=request.user)
        wallet.set_transaction_pin(payload.pin)
        return {'message': 'Transaction PIN set successfully'}
    except NGNWallet.DoesNotExist:
        raise HttpError(404, 'Wallet not found')
    except ValueError as e:
        raise HttpError(400, str(e))
    except Exception as e:
        raise HttpError(500, str(e))
