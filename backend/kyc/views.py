from ninja import Router
from ninja.errors import HttpError

from .schemas import KYCSubmissionSchema, KYCResponseSchema
from .models import KYCVerification, KYCStatus, DocumentType

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
