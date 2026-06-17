import logging
from datetime import datetime, timezone

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """
    Sends formatted admin alert messages to a Telegram group via Bot API.
    All methods are fire-and-forget: errors are logged but never raised,
    so a Telegram failure can never crash a user-facing request.
    """

    BASE_URL = "https://api.telegram.org/bot{token}/sendMessage"

    @classmethod
    def _send(cls, message: str) -> None:
        """Internal: POST a MarkdownV2-formatted message to the admin chat."""
        token = getattr(settings, "TELEGRAM_BOT_TOKEN", "")
        chat_id = getattr(settings, "TELEGRAM_CHAT_ID", "")

        if not token or not chat_id:
            logger.debug("Telegram not configured — skipping notification.")
            return

        url = cls.BASE_URL.format(token=token)
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }

        try:
            with httpx.Client(timeout=5.0) as client:
                response = client.post(url, json=payload)
                if response.status_code != 200:
                    logger.warning(
                        f"Telegram API returned {response.status_code}: {response.text}"
                    )
        except Exception as exc:
            logger.error(f"Telegram notification failed: {exc}")

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # ------------------------------------------------------------------ #
    #  User Events                                                          #
    # ------------------------------------------------------------------ #

    @classmethod
    def new_user_registered(cls, full_name: str, email: str) -> None:
        message = (
            "🟢 <b>NEW USER REGISTERED</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>Name:</b> {full_name}\n"
            f"📧 <b>Email:</b> {email}\n"
            f"⏰ {cls._now()}"
        )
        cls._send(message)

    # ------------------------------------------------------------------ #
    #  Deposit Events                                                       #
    # ------------------------------------------------------------------ #

    @classmethod
    def deposit_received(
        cls,
        full_name: str,
        email: str,
        asset: str,
        crypto_amount: str,
        ngn_amount: str,
        rate: str,
        reference: str,
    ) -> None:
        message = (
            "📥 <b>NEW CRYPTO DEPOSIT</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>User:</b> {full_name} ({email})\n"
            f"💰 <b>Crypto:</b> {crypto_amount} {asset.upper()}\n"
            f"💵 <b>NGN Credited:</b> ₦{ngn_amount}\n"
            f"📊 <b>Rate Used:</b> ₦{rate}/{asset.upper()}\n"
            f"🔗 <b>Quidax Ref:</b> <code>{reference}</code>\n"
            f"⏰ {cls._now()}"
        )
        cls._send(message)

    # ------------------------------------------------------------------ #
    #  Withdrawal Events                                                    #
    # ------------------------------------------------------------------ #

    @classmethod
    def withdrawal_requested(
        cls,
        full_name: str,
        email: str,
        amount: str,
        bank_name: str,
        account_number: str,
        reference: str,
    ) -> None:
        message = (
            "💸 <b>WITHDRAWAL REQUESTED</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>User:</b> {full_name} ({email})\n"
            f"💵 <b>Amount:</b> ₦{amount}\n"
            f"🏦 <b>Bank:</b> {bank_name} — <code>{account_number}</code>\n"
            f"🔗 <b>Ref:</b> <code>{reference}</code>\n"
            f"⏰ {cls._now()}"
        )
        cls._send(message)

    @classmethod
    def withdrawal_success(
        cls,
        full_name: str,
        email: str,
        amount: str,
        bank_name: str,
        account_number: str,
        reference: str,
    ) -> None:
        message = (
            "✅ <b>WITHDRAWAL SUCCESSFUL</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>User:</b> {full_name} ({email})\n"
            f"💵 <b>Amount:</b> ₦{amount}\n"
            f"🏦 <b>Bank:</b> {bank_name} — <code>{account_number}</code>\n"
            f"🔗 <b>Ref:</b> <code>{reference}</code>\n"
            f"⏰ {cls._now()}"
        )
        cls._send(message)

    @classmethod
    def withdrawal_failed(
        cls,
        full_name: str,
        email: str,
        amount: str,
        bank_name: str,
        reference: str,
        reason: str = "Transfer failed or reversed by provider",
    ) -> None:
        message = (
            "❌ <b>WITHDRAWAL FAILED / REVERSED</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>User:</b> {full_name} ({email})\n"
            f"💵 <b>Amount:</b> ₦{amount} <i>(refunded to wallet)</i>\n"
            f"🏦 <b>Bank:</b> {bank_name}\n"
            f"🔗 <b>Ref:</b> <code>{reference}</code>\n"
            f"⚠️ <b>Reason:</b> {reason}\n"
            f"⏰ {cls._now()}"
        )
        cls._send(message)

    # ------------------------------------------------------------------ #
    #  KYC Events                                                           #
    # ------------------------------------------------------------------ #

    @classmethod
    def kyc_submitted(
        cls,
        full_name: str,
        email: str,
        document_type: str,
        kyc_id: int,
    ) -> None:
        message = (
            "📋 <b>KYC SUBMITTED — ACTION REQUIRED</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>User:</b> {full_name} ({email})\n"
            f"🪪 <b>Document:</b> {document_type.replace('_', ' ').title()}\n"
            f"🆔 <b>KYC ID:</b> <code>{kyc_id}</code>\n"
            f"⏰ {cls._now()}"
        )
        cls._send(message)

    @classmethod
    def kyc_approved(cls, full_name: str, email: str, kyc_id: int) -> None:
        message = (
            "✅ <b>KYC APPROVED</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>User:</b> {full_name} ({email})\n"
            f"🆔 <b>KYC ID:</b> <code>{kyc_id}</code>\n"
            f"⏰ {cls._now()}"
        )
        cls._send(message)

    @classmethod
    def kyc_rejected(
        cls, full_name: str, email: str, kyc_id: int, reason: str
    ) -> None:
        message = (
            "❌ <b>KYC REJECTED</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>User:</b> {full_name} ({email})\n"
            f"🆔 <b>KYC ID:</b> <code>{kyc_id}</code>\n"
            f"📝 <b>Reason:</b> {reason}\n"
            f"⏰ {cls._now()}"
        )
        cls._send(message)
