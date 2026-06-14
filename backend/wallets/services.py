import logging
from typing import Optional, List, Dict

import httpx
from django.conf import settings
from django.db import transaction

from .models import NGNWallet, DepositAddress, BankAccount, ASSET_NETWORKS

logger = logging.getLogger(__name__)


class QuidaxService:
    """
    Wraps Quidax API calls for sub-account management and deposit address generation.
    Skeleton — will function once QUIDAX_API_KEY is set in .env.
    """

    @staticmethod
    def _get_headers() -> dict:
        api_key = getattr(settings, 'QUIDAX_API_KEY', '')
        return {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
        }

    @staticmethod
    def _get_base_url() -> str:
        return getattr(
            settings,
            'QUIDAX_BASE_URL',
            'https://openapi.quidax.io/exchange-open-api/v1',
        )

    @staticmethod
    def create_sub_account(user) -> str:
        """
        Create a Quidax sub-account for the given user.
        Returns the Quidax user ID.
        """
        url = f'{QuidaxService._get_base_url()}/users'
        payload = {
            'email': user.email,
            'first_name': user.full_name.split(' ')[0],
            'last_name': ' '.join(user.full_name.split(' ')[1:]) or user.full_name,
        }

        try:
            with httpx.Client(timeout=15) as client:
                response = client.post(
                    url,
                    json=payload,
                    headers=QuidaxService._get_headers(),
                )
                response.raise_for_status()
                data = response.json()
                quidax_user_id = data.get('data', {}).get('id', '')
                logger.info(f'Created Quidax sub-account for {user.email}: {quidax_user_id}')
                return quidax_user_id
        except httpx.HTTPError as e:
            logger.error(f'Quidax sub-account creation failed for {user.email}: {e}')
            raise ValueError(f'Failed to create Quidax sub-account: {e}')

    @staticmethod
    def generate_deposit_address(quidax_user_id: str, asset: str, network: str) -> str:
        """
        Generate a deposit address for the given asset/network on a Quidax sub-account.
        Returns the deposit address string.
        """
        url = (
            f'{QuidaxService._get_base_url()}/users/{quidax_user_id}'
            f'/wallets/{asset}/addresses'
        )
        params = {'network': network} if network else {}

        try:
            with httpx.Client(timeout=15) as client:
                response = client.post(
                    url,
                    params=params,
                    headers=QuidaxService._get_headers(),
                )
                response.raise_for_status()
                data = response.json()
                address = data.get('data', {}).get('address', '')
                logger.info(f'Generated {asset}/{network} address for {quidax_user_id}: {address}')
                return address
        except httpx.HTTPError as e:
            logger.error(f'Quidax address generation failed: {e}')
            raise ValueError(f'Failed to generate deposit address: {e}')

    @staticmethod
    def generate_all_addresses(quidax_user_id: str, wallet: NGNWallet) -> List[DepositAddress]:
        """
        Generate deposit addresses for all supported assets/networks.
        Creates DepositAddress records in the database.
        """
        addresses = []
        for asset, networks in ASSET_NETWORKS.items():
            for network in networks:
                try:
                    address_str = QuidaxService.generate_deposit_address(
                        quidax_user_id, asset, network.value,
                    )
                    deposit_address, _ = DepositAddress.objects.get_or_create(
                        wallet=wallet,
                        asset=asset,
                        network=network.value,
                        defaults={'address': address_str},
                    )
                    addresses.append(deposit_address)
                except ValueError as e:
                    logger.warning(f'Skipping {asset}/{network}: {e}')
        return addresses

    @staticmethod
    def verify_webhook_signature(request) -> bool:
        """
        Verify the authenticity of a Quidax webhook request.
        TODO: Implement signature verification once Quidax provides HMAC details.
        """
        # Placeholder — implement with actual Quidax signature verification
        logger.warning('Quidax webhook signature verification not yet implemented')
        return True


class PaystackService:
    """
    Wraps Paystack API calls for bank account verification and NGN transfers.
    Skeleton — will function once PAYSTACK_SECRET_KEY is set in .env.
    """

    @staticmethod
    def _get_headers() -> dict:
        secret_key = getattr(settings, 'PAYSTACK_SECRET_KEY', '')
        return {
            'Authorization': f'Bearer {secret_key}',
            'Content-Type': 'application/json',
        }

    @staticmethod
    def _get_base_url() -> str:
        return getattr(settings, 'PAYSTACK_BASE_URL', 'https://api.paystack.co')

    @staticmethod
    def list_banks() -> list:
        """Fetch list of Nigerian banks from Paystack."""
        url = f'{PaystackService._get_base_url()}/bank'
        params = {'currency': 'NGN', 'perPage': 100}

        try:
            with httpx.Client(timeout=10) as client:
                response = client.get(
                    url,
                    params=params,
                    headers=PaystackService._get_headers(),
                )
                response.raise_for_status()
                data = response.json()
                return data.get('data', [])
        except httpx.HTTPError as e:
            logger.error(f'Paystack list banks failed: {e}')
            raise ValueError(f'Failed to fetch banks: {e}')

    @staticmethod
    def resolve_account(account_number: str, bank_code: str) -> dict:
        """
        Verify a bank account number and resolve the account name.
        Returns dict with account_name and account_number.
        """
        url = f'{PaystackService._get_base_url()}/bank/resolve'
        params = {
            'account_number': account_number,
            'bank_code': bank_code,
        }

        try:
            with httpx.Client(timeout=10) as client:
                response = client.get(
                    url,
                    params=params,
                    headers=PaystackService._get_headers(),
                )
                response.raise_for_status()
                data = response.json()
                return data.get('data', {})
        except httpx.HTTPError as e:
            logger.error(f'Paystack resolve account failed: {e}')
            raise ValueError(f'Failed to resolve account: {e}')

    @staticmethod
    def create_transfer_recipient(bank_account: BankAccount) -> str:
        """
        Create a Paystack transfer recipient.
        Returns the recipient_code.
        """
        url = f'{PaystackService._get_base_url()}/transferrecipient'
        payload = {
            'type': 'nuban',
            'name': bank_account.account_name,
            'account_number': bank_account.account_number,
            'bank_code': bank_account.bank_code,
            'currency': 'NGN',
        }

        try:
            with httpx.Client(timeout=10) as client:
                response = client.post(
                    url,
                    json=payload,
                    headers=PaystackService._get_headers(),
                )
                response.raise_for_status()
                data = response.json()
                recipient_code = data.get('data', {}).get('recipient_code', '')
                logger.info(f'Created Paystack recipient: {recipient_code}')
                return recipient_code
        except httpx.HTTPError as e:
            logger.error(f'Paystack create recipient failed: {e}')
            raise ValueError(f'Failed to create transfer recipient: {e}')

    @staticmethod
    def initiate_transfer(amount_kobo: int, recipient_code: str, reference: str) -> dict:
        """
        Initiate an NGN transfer via Paystack.
        Amount is in kobo (₦1 = 100 kobo).
        """
        url = f'{PaystackService._get_base_url()}/transfer'
        payload = {
            'source': 'balance',
            'amount': amount_kobo,
            'recipient': recipient_code,
            'reason': 'Swift wallet withdrawal',
            'reference': reference,
        }

        try:
            with httpx.Client(timeout=15) as client:
                response = client.post(
                    url,
                    json=payload,
                    headers=PaystackService._get_headers(),
                )
                response.raise_for_status()
                data = response.json()
                logger.info(f'Initiated Paystack transfer: {reference}')
                return data.get('data', {})
        except httpx.HTTPError as e:
            logger.error(f'Paystack transfer failed: {e}')
            raise ValueError(f'Failed to initiate transfer: {e}')

    @staticmethod
    def verify_webhook_signature(request) -> bool:
        """
        Verify Paystack webhook signature using HMAC SHA-512.
        """
        import hashlib
        import hmac

        secret_key = getattr(settings, 'PAYSTACK_SECRET_KEY', '')
        if not secret_key:
            logger.warning('PAYSTACK_SECRET_KEY not set, skipping signature verification')
            return True

        signature = request.headers.get('x-paystack-signature', '')
        body = request.body

        expected = hmac.new(
            secret_key.encode('utf-8'),
            body,
            hashlib.sha512,
        ).hexdigest()

        return hmac.compare_digest(expected, signature)


class WalletService:
    """High-level wallet operations."""

    @staticmethod
    def create_wallet_for_user(user) -> NGNWallet:
        """
        Create an NGN wallet for a user and initialize Quidax sub-account.
        """
        wallet, created = NGNWallet.objects.get_or_create(user=user)
        if created and not wallet.quidax_user_id:
            try:
                quidax_user_id = QuidaxService.create_sub_account(user)
                wallet.quidax_user_id = quidax_user_id
                wallet.save(update_fields=['quidax_user_id'])
                QuidaxService.generate_all_addresses(quidax_user_id, wallet)
            except Exception as e:
                logger.error(f'Failed to setup Quidax for wallet {wallet.id}: {e}')
        return wallet

    @staticmethod
    def get_deposit_addresses(user) -> List[Dict]:
        """Get all deposit addresses for a user, grouped by asset."""
        try:
            wallet = NGNWallet.objects.get(user=user)
        except NGNWallet.DoesNotExist:
            raise ValueError('Wallet not found')

        if not wallet.quidax_user_id:
            try:
                quidax_user_id = QuidaxService.create_sub_account(user)
                wallet.quidax_user_id = quidax_user_id
                wallet.save(update_fields=['quidax_user_id'])
            except Exception as e:
                logger.error(f'Failed to setup Quidax sub-account: {e}')

        if wallet.quidax_user_id:
            if not DepositAddress.objects.filter(wallet=wallet).exists():
                try:
                    QuidaxService.generate_all_addresses(wallet.quidax_user_id, wallet)
                except Exception as e:
                    logger.error(f'Failed to generate deposit addresses: {e}')

        addresses = DepositAddress.objects.filter(wallet=wallet).order_by('asset', 'network')
        grouped = {}
        for addr in addresses:
            if addr.asset not in grouped:
                grouped[addr.asset] = []
            grouped[addr.asset].append({
                'network': addr.network,
                'address': addr.address,
            })
        return grouped

    @staticmethod
    def add_bank_account(user, bank_code: str, account_number: str) -> BankAccount:
        """
        Add a bank account for the user.
        Resolves via Paystack to verify and get the account name.
        """
        # Enforce maximum of 5 bank accounts per user
        if BankAccount.objects.filter(user=user).count() >= 5:
            raise ValueError('You cannot link more than 5 bank accounts')

        # Resolve the account
        resolved = PaystackService.resolve_account(account_number, bank_code)
        account_name = resolved.get('account_name', '')

        if not account_name:
            raise ValueError('Could not resolve bank account. Please check the details.')

        # Get bank name from the banks list
        bank_name = bank_code  # fallback
        try:
            banks = PaystackService.list_banks()
            for bank in banks:
                if bank.get('code') == bank_code:
                    bank_name = bank.get('name', bank_code)
                    break
        except ValueError:
            pass

        # Check for duplicate
        existing = BankAccount.objects.filter(
            user=user,
            bank_code=bank_code,
            account_number=account_number,
        ).first()
        if existing:
            raise ValueError('This bank account is already linked')

        # Set as default if first account
        is_default = not BankAccount.objects.filter(user=user).exists()

        bank_account = BankAccount.objects.create(
            user=user,
            bank_name=bank_name,
            bank_code=bank_code,
            account_number=account_number,
            account_name=account_name,
            is_default=is_default,
        )

        # Create Paystack transfer recipient
        try:
            recipient_code = PaystackService.create_transfer_recipient(bank_account)
            bank_account.paystack_recipient_code = recipient_code
            bank_account.save(update_fields=['paystack_recipient_code'])
        except ValueError as e:
            logger.warning(f'Paystack recipient creation failed: {e}. Can retry later.')

        return bank_account

    @staticmethod
    def get_balance(user) -> dict:
        """Get user's current NGN balance."""
        try:
            wallet = NGNWallet.objects.get(user=user)
            return {
                'balance': wallet.balance,
                'pin_is_set': wallet.pin_is_set,
                'created_at': wallet.created_at.isoformat(),
            }
        except NGNWallet.DoesNotExist:
            raise ValueError('Wallet not found')
