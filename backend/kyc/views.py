from ninja import Router
from ninja.errors import HttpError
from django.conf import settings
import httpx

from pydantic import BaseModel
from datetime import datetime

from .schemas import (
    KYCSubmitSchema,
    KYCResponseSchema, AdminKYCResponseSchema
)
from .models import KYCVerification, KYCStatus, DocumentType
from notifications.tasks import send_email_task, send_telegram_task, create_notification_task

router = Router(tags=['KYC'])


@router.post('/submit', response=KYCResponseSchema)
def submit_kyc(request, payload: KYCSubmitSchema):
    """
    Submit KYC documents and selfie for manual review.
    """
    if KYCVerification.objects.filter(user=request.user).exists():
        kyc = KYCVerification.objects.get(user=request.user)
        if kyc.status in [KYCStatus.SUBMITTED, KYCStatus.VERIFIED]:
            raise HttpError(400, f"KYC is already {kyc.status}")
    else:
        kyc = KYCVerification(user=request.user)

    valid_types = [choice[0] for choice in DocumentType.choices]
    if payload.document_type not in valid_types:
        raise HttpError(400, f"Invalid document type. Allowed: {', '.join(valid_types)}")

    kyc.document_type = payload.document_type
    kyc.document_number = payload.document_number
    kyc.document_url = str(payload.document_url)
    kyc.selfie_url = str(payload.selfie_url)
    if payload.date_of_birth:
        kyc.date_of_birth = payload.date_of_birth
        
    kyc.status = KYCStatus.SUBMITTED
    kyc.save()

    send_email_task.delay(
        to_email=kyc.user.email,
        to_name=kyc.user.full_name,
        subject="SwiftTrade \u2013 KYC Submitted",
        template_name="emails/kyc_submitted.html",
        context={
            "full_name": kyc.user.full_name,
            "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        },
    )

    create_notification_task.delay(
        user_id=kyc.user.id,
        notification_type='kyc',
        title='KYC Under Review',
        body='Your KYC verification requires manual review and will be processed shortly.',
    )

    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    telegram_msg = (
        "\U0001f4cb <b>KYC SUBMITTED \u2014 ACTION REQUIRED</b>\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        f"\U0001f464 <b>User:</b> {kyc.user.full_name} ({kyc.user.email})\n"
        f"\U0001fa96 <b>Document:</b> {kyc.document_type.replace('_', ' ').title()}\n"
        f"\U0001f194 <b>KYC ID:</b> <code>{kyc.id}</code>\n"
        f"\u23f0 {ts}"
    )
    send_telegram_task.delay(telegram_msg)

    return KYCResponseSchema(
        status=kyc.status,
        document_type=kyc.document_type,
        document_number=kyc.document_number,
        rejection_reason=kyc.rejection_reason,
        created_at=kyc.created_at.isoformat()
    )


@router.get('/admin/all', response=list[AdminKYCResponseSchema])
def get_all_kyc_requests(request):
    """Admin endpoint to list all KYC requests."""
    if not request.user.is_staff:
        raise HttpError(403, "Permission denied.")
    
    kycs = KYCVerification.objects.all().select_related('user').order_by('-created_at')
    
    result = []
    for kyc in kycs:
        result.append(AdminKYCResponseSchema(
            id=str(kyc.id),
            status=kyc.status,
            document_type=kyc.document_type,
            document_number=kyc.document_number,
            rejection_reason=kyc.rejection_reason,
            created_at=kyc.created_at.isoformat(),
            user_id=str(kyc.user.id),
            user_email=kyc.user.email,
            user_full_name=kyc.user.full_name,
            document_url=kyc.document_url,
            selfie_url=kyc.selfie_url
        ))
        
    return result


@router.get('/status', response=KYCResponseSchema)
def get_kyc_status(request):
    """Get the current KYC verification status."""
    try:
        kyc = KYCVerification.objects.get(user=request.user)
        return KYCResponseSchema(
            status=kyc.status,
            document_type=kyc.document_type,
            document_number=kyc.document_number,
            rejection_reason=kyc.rejection_reason,
            created_at=kyc.created_at.isoformat()
        )
    except KYCVerification.DoesNotExist:
        return KYCResponseSchema(
            status=KYCStatus.UNVERIFIED,
            document_type="",
            document_number="",
            rejection_reason=None,
            created_at="",
        )


class KYCRejectSchema(BaseModel):
    reason: str


@router.post('/{kyc_id}/approve', response=KYCResponseSchema)
def approve_kyc(request, kyc_id: int):
    """Admin endpoint to approve a KYC submission."""
    if not request.user.is_staff:
        raise HttpError(403, "Permission denied")

    try:
        kyc = KYCVerification.objects.get(id=kyc_id)
        if kyc.status == KYCStatus.VERIFIED:
            raise HttpError(400, "KYC is already verified")

        kyc.status = KYCStatus.VERIFIED
        kyc.save()

        # Background notifications
        send_email_task.delay(
            to_email=kyc.user.email,
            to_name=kyc.user.full_name,
            subject="SwiftTrade \u2013 KYC Approved",
            template_name="emails/kyc_approved.html",
            context={
                "full_name": kyc.user.full_name,
                "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
            },
        )

        create_notification_task.delay(
            user_id=kyc.user.id,
            notification_type='kyc',
            title='KYC Approved',
            body='Your KYC verification has been approved by our team.',
        )

        ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        telegram_msg = (
            "\u2705 <b>KYC APPROVED</b>\n"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            f"\U0001f464 <b>User:</b> {kyc.user.full_name} ({kyc.user.email})\n"
            f"\U0001f194 <b>KYC ID:</b> <code>{kyc.id}</code>\n"
            f"\u23f0 {ts}"
        )
        send_telegram_task.delay(telegram_msg)

        return KYCResponseSchema(
            status=kyc.status,
            document_type=kyc.document_type,
            document_number=kyc.document_number,
            rejection_reason=kyc.rejection_reason,
            created_at=kyc.created_at.isoformat()
        )
    except KYCVerification.DoesNotExist:
        raise HttpError(404, "KYC not found")


@router.post('/{kyc_id}/reject', response=KYCResponseSchema)
def reject_kyc(request, kyc_id: int, payload: KYCRejectSchema):
    """Admin endpoint to reject a KYC submission."""
    if not request.user.is_staff:
        raise HttpError(403, "Permission denied")

    try:
        kyc = KYCVerification.objects.get(id=kyc_id)
        if kyc.status == KYCStatus.RESUBMISSION:
            raise HttpError(400, "KYC is already marked for resubmission")

        kyc.status = KYCStatus.RESUBMISSION
        kyc.rejection_reason = payload.reason
        kyc.save()

        # Background notifications
        send_email_task.delay(
            to_email=kyc.user.email,
            to_name=kyc.user.full_name,
            subject="SwiftTrade \u2013 KYC Rejected",
            template_name="emails/kyc_rejected.html",
            context={
                "full_name": kyc.user.full_name,
                "reason": payload.reason,
                "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
            },
        )

        create_notification_task.delay(
            user_id=kyc.user.id,
            notification_type='kyc',
            title='KYC Rejected',
            body=f'Your KYC verification was rejected. Reason: {payload.reason}',
        )

        ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        telegram_msg = (
            "\u274c <b>KYC REJECTED</b>\n"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            f"\U0001f464 <b>User:</b> {kyc.user.full_name} ({kyc.user.email})\n"
            f"\U0001f194 <b>KYC ID:</b> <code>{kyc.id}</code>\n"
            f"\U0001f4dd <b>Reason:</b> {payload.reason}\n"
            f"\u23f0 {ts}"
        )
        send_telegram_task.delay(telegram_msg)

        return KYCResponseSchema(
            status=kyc.status,
            document_type=kyc.document_type,
            document_number=kyc.document_number,
            rejection_reason=kyc.rejection_reason,
            created_at=kyc.created_at.isoformat()
        )
    except KYCVerification.DoesNotExist:
        raise HttpError(404, "KYC not found")


@router.post('/{kyc_id}/unverify', response=KYCResponseSchema)
def unverify_kyc(request, kyc_id: int):
    """Admin endpoint to set a user to unverified."""
    if not request.user.is_staff:
        raise HttpError(403, "Permission denied")

    try:
        kyc = KYCVerification.objects.get(id=kyc_id)
        if kyc.status == KYCStatus.UNVERIFIED:
            raise HttpError(400, "KYC is already unverified")

        kyc.status = KYCStatus.UNVERIFIED
        kyc.save()

        return KYCResponseSchema(
            status=kyc.status,
            document_type=kyc.document_type,
            document_number=kyc.document_number,
            rejection_reason=kyc.rejection_reason,
            created_at=kyc.created_at.isoformat()
        )
    except KYCVerification.DoesNotExist:
        raise HttpError(404, "KYC not found")
