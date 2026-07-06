import logging
from typing import Optional, List, Dict

import httpx
from django.conf import settings
from django.db import transaction

from .models import NGNWallet, DepositAddress, BankAccount, ASSET_NETWORKS

logger = logging.getLogger(__name__)





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
        Create an NGN wallet for a new user.
        No longer calls Quidax — addresses are generated lazily on first deposit screen visit.
        """
        wallet, _ = NGNWallet.objects.get_or_create(user=user)
        return wallet

    @staticmethod
    def get_or_create_deposit_address(user, asset: str, network: str) -> DepositAddress:
        """
        Get existing deposit address or derive a new one from xpub and subscribe to Tatum.
        """
        from .crypto import get_next_derivation_index, derive_address
        from .alchemy import subscribe_to_alchemy
        from .blockcypher import subscribe_to_blockcypher

        wallet = NGNWallet.objects.get(user=user)

        # ETH and all ERC-20/BEP-20 tokens share the same address derivation
        lookup_asset = "eth" if network in ["erc20", "bep20"] else asset
        existing = DepositAddress.objects.filter(
            wallet=wallet, asset=lookup_asset, network=network
        ).first()

        if existing:
            # For non-eth assets that share the ETH address, return a matching record
            if asset != lookup_asset:
                addr, _ = DepositAddress.objects.get_or_create(
                    wallet=wallet,
                    asset=asset,
                    network=network,
                    defaults={
                        "address": existing.address,
                        "derivation_index": existing.derivation_index,
                    }
                )
                return addr
            return existing

        with transaction.atomic():
            index = get_next_derivation_index(lookup_asset, network)
            address = derive_address(lookup_asset, network, index)

            deposit_address = DepositAddress.objects.create(
                wallet=wallet,
                asset=lookup_asset,
                network=network,
                address=address,
                derivation_index=index,
            )

            try:
                if network in ["erc20", "bep20"]:
                    success = subscribe_to_alchemy(address)
                    if success:
                        deposit_address.tatum_subscription_id = "alchemy_subscribed"
                        deposit_address.save(update_fields=["tatum_subscription_id"])
                elif network == "bitcoin":
                    webhook_url = f"{settings.BACKEND_URL}/api/webhooks/blockcypher-deposit/"
                    sub_id = subscribe_to_blockcypher(address, webhook_url)
                    if sub_id:
                        deposit_address.tatum_subscription_id = sub_id
                        deposit_address.save(update_fields=["tatum_subscription_id"])
            except Exception as e:
                logger.error(f"Webhook subscription failed for {address}: {e}")

        # For non-eth assets that share the ETH address, return a matching record
        if asset != lookup_asset:
            addr, _ = DepositAddress.objects.get_or_create(
                wallet=wallet,
                asset=asset,
                network=network,
                defaults={
                    "address": deposit_address.address,
                    "derivation_index": deposit_address.derivation_index,
                    "tatum_subscription_id": deposit_address.tatum_subscription_id,
                }
            )
            return addr

        return deposit_address

    @staticmethod
    def get_all_deposit_addresses(user) -> List[Dict]:
        """Get all crypto deposit addresses for the user, grouped by asset."""
        try:
            wallet = NGNWallet.objects.get(user=user)
        except NGNWallet.DoesNotExist:
            raise ValueError('Wallet not found')

        grouped = {}
        for asset, networks in ASSET_NETWORKS.items():
            for network in networks:
                # Currently only supporting BTC and ETH/ERC20/BEP20 via HD wallet logic mapped in Tatum
                if network.value not in ["bitcoin", "erc20", "bep20"]:
                    continue
                try:
                    addr = WalletService.get_or_create_deposit_address(user, asset, network.value)
                    if addr.asset not in grouped:
                        grouped[addr.asset] = []
                    grouped[addr.asset].append({
                        'network': addr.network,
                        'address': addr.address,
                    })
                except Exception as e:
                    logger.error(f"Failed to setup address for {asset}/{network.value}: {e}")
                    
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
