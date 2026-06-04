from ninja import Router
from ninja.errors import HttpError

from pydantic import BaseModel

from .schemas import KYCSubmissionSchema, KYCResponseSchema
from .models import KYCVerification, KYCStatus, DocumentType
from authenticator.email import send_kyc_approved_email, send_kyc_rejected_email

router = Router(tags=['KYC'])


@router.post('/submit', response=KYCResponseSchema)
def submit_kyc(request, payload: KYCSubmissionSchema):
    """
    Submit KYC documents for manual verification.
    Expects URLs of uploaded images from the frontend (e.g., Cloudinary).
    """
    if KYCVerification.objects.filter(user=request.user).exists():
        kyc = KYCVerification.objects.get(user=request.user)
        if kyc.status in [KYCStatus.PENDING, KYCStatus.APPROVED]:
            raise HttpError(400, f"KYC is already {kyc.status}")
        
        valid_types = [choice[0] for choice in DocumentType.choices]
        if payload.document_type not in valid_types:
            raise HttpError(400, f"Invalid document type. Allowed: {', '.join(valid_types)}")

        # If rejected, allow resubmission
        kyc.document_type = payload.document_type
        kyc.document_number = payload.document_number
        kyc.document_url = str(payload.document_url)
        kyc.selfie_url = str(payload.selfie_url)
        kyc.status = KYCStatus.PENDING
        kyc.rejection_reason = ""
        kyc.save()
    else:
        valid_types = [choice[0] for choice in DocumentType.choices]
        if payload.document_type not in valid_types:
            raise HttpError(400, f"Invalid document type. Allowed: {', '.join(valid_types)}")

        kyc = KYCVerification.objects.create(
            user=request.user,
            document_type=payload.document_type,
            document_number=payload.document_number,
            document_url=str(payload.document_url),
            selfie_url=str(payload.selfie_url),
            status=KYCStatus.PENDING,
        )

    return KYCResponseSchema(
        status=kyc.status,
        document_type=kyc.document_type,
        document_number=kyc.document_number,
        rejection_reason=kyc.rejection_reason,
        created_at=kyc.created_at.isoformat()
    )


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
        raise HttpError(404, "KYC has not been submitted yet.")


class KYCRejectSchema(BaseModel):
    reason: str


@router.post('/{kyc_id}/approve', response=KYCResponseSchema)
def approve_kyc(request, kyc_id: int):
    """Admin endpoint to approve a KYC submission."""
    if not request.user.is_staff:
        raise HttpError(403, "Permission denied")
    
    try:
        kyc = KYCVerification.objects.get(id=kyc_id)
        if kyc.status == KYCStatus.APPROVED:
            raise HttpError(400, "KYC is already approved")
        
        kyc.status = KYCStatus.APPROVED
        kyc.save()

        # Send Email
        send_kyc_approved_email(user=kyc.user)

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
        if kyc.status == KYCStatus.REJECTED:
            raise HttpError(400, "KYC is already rejected")
        
        kyc.status = KYCStatus.REJECTED
        kyc.rejection_reason = payload.reason
        kyc.save()

        # Send Email
        send_kyc_rejected_email(user=kyc.user, reason=payload.reason)

        return KYCResponseSchema(
            status=kyc.status,
            document_type=kyc.document_type,
            document_number=kyc.document_number,
            rejection_reason=kyc.rejection_reason,
            created_at=kyc.created_at.isoformat()
        )
    except KYCVerification.DoesNotExist:
        raise HttpError(404, "KYC not found")
