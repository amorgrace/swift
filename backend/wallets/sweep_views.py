"""
wallets/sweep_views.py — Admin-only sweep API endpoints.
"""
import logging
from typing import List
from ninja import Router, Schema
from ninja.errors import HttpError

logger = logging.getLogger(__name__)
router = Router(tags=["Sweep"])


# ── Schemas ──────────────────────────────────────────────────────────────────

class RequestOtpSchema(Schema):
    asset: str
    network: str


class ConfirmSweepSchema(Schema):
    asset: str
    network: str
    otp: str  # admin sweep OTP


class SweepBalanceItem(Schema):
    asset: str
    network: str
    total_balance: float
    address_count: int
    users: list[str]


class SweepHistoryItem(Schema):
    id: int
    asset: str
    network: str
    total_crypto_amount: float
    gas_cost_crypto: float
    destination_address: str
    status: str
    tx_hash: str
    admin_email: str
    created_at: str


# ── Helpers ───────────────────────────────────────────────────────────────────

def _require_sweep_owner(request):
    import os
    if not request.user.is_staff:
        raise HttpError(403, "Admin access required.")
    
    owner_email = os.environ.get("SWEEP_OWNER_EMAIL", "famakinwa99@gmail.com").strip().lower()
    if request.user.email.strip().lower() != owner_email:
        raise HttpError(403, f"Access denied. Only the sweep owner ({owner_email}) is authorized.")


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/sweep/balances", response=List[SweepBalanceItem])
def get_sweep_balances(request):
    """List all unswept on-chain balances across all user deposit addresses."""
    _require_sweep_owner(request)
    try:
        from wallets.sweep import fetch_pending_balances
        results = fetch_pending_balances()
        return [
            SweepBalanceItem(
                asset=r["asset"],
                network=r["network"],
                total_balance=r["total_balance"],
                address_count=r["address_count"],
                users=[e["user_email"] for e in r["entries"]]
            )
            for r in results
        ]
    except Exception as e:
        logger.error(f"[Sweep API] fetch_pending_balances error: {e}")
        raise HttpError(500, str(e))


@router.post("/sweep/request-otp", response={200: dict})
def request_sweep_otp(request, payload: RequestOtpSchema):
    """Generate a 6-digit OTP and send it via email to the sweep owner."""
    _require_sweep_owner(request)
    import random
    import os
    from django.core.cache import cache
    from notifications.tasks import send_email_task
    from wallets.sweep import fetch_pending_balances

    # 1. Fetch live balance for display in email
    all_balances = fetch_pending_balances()
    target = next(
        (b for b in all_balances
         if b["asset"].lower() == payload.asset.lower()
         and b["network"].lower() == payload.network.lower()),
        None,
    )
    total_bal = target["total_balance"] if target else 0.0

    # 2. Generate 6-digit OTP
    otp = f"{random.randint(100000, 999999)}"

    # 3. Store OTP in cache for 10 minutes (600s)
    cache_key = f"sweep_otp_{payload.asset.lower()}_{payload.network.lower()}"
    cache.set(cache_key, otp, timeout=600)

    # 4. Dispatch Email to Owner
    owner_email = os.environ.get("SWEEP_OWNER_EMAIL", "famakinwa99@gmail.com").strip().lower()
    
    send_email_task.delay(
        to_email=owner_email,
        to_name="Project Owner",
        subject=f"Sweep Authorization OTP - {payload.asset.upper()}",
        template_name="emails/sweep_otp.html",
        context={
            "full_name": request.user.full_name or "Owner",
            "amount": f"{total_bal:,.6f}" if total_bal else "0",
            "asset": payload.asset.upper(),
            "network": payload.network.upper(),
            "token": otp,
        }
    )

    return {"message": f"OTP successfully sent to {owner_email}"}


@router.post("/sweep/execute", response={200: dict})
def execute_sweep(request, payload: ConfirmSweepSchema):
    """
    Initiate and execute a sweep for the given asset/network.
    Requires a valid 6-digit sweep OTP.
    """
    _require_sweep_owner(request)

    # 1. Verify OTP
    from django.core.cache import cache
    cache_key = f"sweep_otp_{payload.asset.lower()}_{payload.network.lower()}"
    cached_otp = cache.get(cache_key)
    
    if not cached_otp:
        raise HttpError(400, "OTP has expired or was not requested. Please request a new code.")
    if cached_otp != payload.otp:
        raise HttpError(403, "Invalid security code (OTP).")

    # Clear OTP so it cannot be used again
    cache.delete(cache_key)

    # 2. Fetch live balances for the requested asset/network
    from wallets.sweep import fetch_pending_balances, sweep_btc_addresses, sweep_evm_addresses
    from wallets.models import SweepRequest, SweepStatus
    import os
    from decimal import Decimal

    all_balances = fetch_pending_balances()
    target = next(
        (b for b in all_balances
         if b["asset"].lower() == payload.asset.lower()
         and b["network"].lower() == payload.network.lower()),
        None,
    )
    if not target or target["total_balance"] <= 0:
        raise HttpError(400, f"No sweepable balance found for {payload.asset.upper()} on {payload.network}.")

    destination = (
        os.environ.get("MASTER_BTC_ADDRESS", "")
        if payload.network == "bitcoin"
        else os.environ.get("MASTER_EVM_ADDRESS", "")
    )
    if not destination:
        raise HttpError(500, "Master destination address is not configured. Add MASTER_BTC_ADDRESS or MASTER_EVM_ADDRESS to your .env.")

    # 3. Create a pending sweep record
    sweep = SweepRequest.objects.create(
        network=payload.network,
        asset=payload.asset.lower(),
        addresses_swept=[e["address"] for e in target["entries"]],
        total_crypto_amount=Decimal(str(target["total_balance"])),
        destination_address=destination,
        status=SweepStatus.APPROVED,
        requested_by=request.user,
    )

    # 4. Execute on-chain
    try:
        if payload.network == "bitcoin":
            result = sweep_btc_addresses(target["entries"])
            tx_hash = result.get("tx_hash", "")
        else:
            result = sweep_evm_addresses(target["entries"], payload.asset.lower(), payload.network.lower())
            tx_hash = ", ".join(result.get("tx_hashes", []))

        sweep.status = SweepStatus.BROADCAST
        sweep.tx_hash = tx_hash
        sweep.save(update_fields=["status", "tx_hash", "updated_at"])

        return {
            "message": "Sweep broadcast successfully.",
            "tx_hash": tx_hash,
            "total_swept": target["total_balance"],
            "asset": payload.asset.upper(),
            "network": payload.network,
            "destination": destination,
        }
    except Exception as e:
        sweep.status = SweepStatus.FAILED
        sweep.error_message = str(e)
        sweep.save(update_fields=["status", "error_message", "updated_at"])
        logger.error(f"[Sweep Execute] Failed: {e}")
        raise HttpError(500, f"Sweep failed: {e}")


@router.get("/sweep/history", response=List[SweepHistoryItem])
def get_sweep_history(request):
    """Return the full audit log of past sweep requests."""
    _require_sweep_owner(request)
    from wallets.models import SweepRequest
    sweeps = SweepRequest.objects.all()[:50]
    return [
        SweepHistoryItem(
            id=s.id,
            asset=s.asset.upper(),
            network=s.network,
            total_crypto_amount=float(s.total_crypto_amount),
            gas_cost_crypto=float(s.gas_cost_crypto),
            destination_address=s.destination_address,
            status=s.status,
            tx_hash=s.tx_hash,
            admin_email=s.requested_by.email if s.requested_by else "System",
            created_at=s.created_at.isoformat(),
        )
        for s in sweeps
    ]
