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

class SetSweepPinSchema(Schema):
    pin: str  # 6 digits


class ConfirmSweepSchema(Schema):
    asset: str
    network: str
    pin: str  # admin sweep PIN


class SweepBalanceItem(Schema):
    asset: str
    network: str
    total_balance: float
    address_count: int


class SweepHistoryItem(Schema):
    id: int
    asset: str
    network: str
    total_crypto_amount: float
    gas_cost_crypto: float
    destination_address: str
    status: str
    tx_hash: str
    created_at: str


# ── Helpers ───────────────────────────────────────────────────────────────────

def _require_admin(request):
    if not request.user.is_staff:
        raise HttpError(403, "Admin access required.")


def _get_or_create_admin_profile(user):
    from wallets.models import AdminProfile
    profile, _ = AdminProfile.objects.get_or_create(user=user)
    return profile


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/sweep/balances", response=List[SweepBalanceItem])
def get_sweep_balances(request):
    """List all unswept on-chain balances across all user deposit addresses."""
    _require_admin(request)
    try:
        from wallets.sweep import fetch_pending_balances
        results = fetch_pending_balances()
        return [
            SweepBalanceItem(
                asset=r["asset"],
                network=r["network"],
                total_balance=r["total_balance"],
                address_count=r["address_count"],
            )
            for r in results
        ]
    except Exception as e:
        logger.error(f"[Sweep API] fetch_pending_balances error: {e}")
        raise HttpError(500, str(e))


@router.post("/sweep/set-pin", response={200: dict})
def set_sweep_pin(request, payload: SetSweepPinSchema):
    """Set or update the admin sweep PIN (6 digits)."""
    _require_admin(request)
    try:
        profile = _get_or_create_admin_profile(request.user)
        profile.set_sweep_pin(payload.pin)
        return {"message": "Sweep PIN set successfully."}
    except ValueError as e:
        raise HttpError(400, str(e))
    except Exception as e:
        raise HttpError(500, str(e))


@router.get("/sweep/pin-status", response={200: dict})
def get_sweep_pin_status(request):
    """Check whether the current admin has set their sweep PIN."""
    _require_admin(request)
    profile = _get_or_create_admin_profile(request.user)
    return {"pin_is_set": profile.pin_is_set}


@router.post("/sweep/execute", response={200: dict})
def execute_sweep(request, payload: ConfirmSweepSchema):
    """
    Initiate and execute a sweep for the given asset/network.
    Requires a valid 6-digit sweep PIN.
    """
    _require_admin(request)

    # 1. Verify PIN
    profile = _get_or_create_admin_profile(request.user)
    if not profile.pin_is_set:
        raise HttpError(400, "You must set your sweep PIN before executing a sweep.")
    if not profile.verify_sweep_pin(payload.pin):
        raise HttpError(403, "Invalid sweep PIN.")

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
    _require_admin(request)
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
            created_at=s.created_at.isoformat(),
        )
        for s in sweeps
    ]
