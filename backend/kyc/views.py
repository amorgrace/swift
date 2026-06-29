from ninja import Router
from ninja.errors import HttpError
from django.conf import settings
import httpx

from pydantic import BaseModel

from .schemas import (
    KYCStep1Schema, KYCStep1ResponseSchema, 
    KYCStep2Schema, KYCStep2ResponseSchema,
    KYCResponseSchema, AdminKYCResponseSchema
)
from .models import KYCVerification, KYCStatus, DocumentType
from .services import (
    verify_nin, verify_bvn, verify_drivers_license,
    check_face_liveness, compare_faces
)
from authenticator.email import (
    send_kyc_approved_email, 
    send_kyc_rejected_email,
    send_kyc_submitted_email
)

router = Router(tags=['KYC'])


@router.post('/verify-id', response=KYCStep1ResponseSchema)
def verify_id(request, payload: KYCStep1Schema):
    """
    Step 1 — submit BVN or NIN or DL, Prembly confirms it's real, stores ID photo
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

    try:
        verified_name = ""
        photo_base64 = ""
        
        if payload.document_type == "nin":
            res = verify_nin(payload.document_number)
            if str(res.get("status")).lower() == "success" or res.get("response_code") == "00":
                data = res.get("data", {})
                verified_name = f"{data.get('firstname', '')} {data.get('surname', '')}".strip()
                photo_base64 = data.get("photo", "")
            else:
                raise HttpError(400, "NIN verification failed")
                
        elif payload.document_type == "bvn":
            res = verify_bvn(payload.document_number)
            if str(res.get("status")).lower() == "success" or res.get("response_code") == "00":
                data = res.get("data", {})
                verified_name = f"{data.get('firstName', '')} {data.get('lastName', '')}".strip()
                photo_base64 = data.get("base64Image", "")
            else:
                raise HttpError(400, "BVN verification failed")
                
        elif payload.document_type == "drivers_license":
            if not payload.date_of_birth or not payload.first_name or not payload.last_name:
                raise HttpError(400, "DOB, first_name, and last_name are required for Driver's License")
            res = verify_drivers_license(payload.document_number, payload.date_of_birth, payload.first_name, payload.last_name)
            if str(res.get("status")).lower() == "success" or res.get("response_code") == "00":
                frsc_data = res.get("data", {}).get("frsc_data", res.get("frsc_data", {}))
                verified_name = frsc_data.get("firstName", "")
                photo_base64 = frsc_data.get("photo", "")
            else:
                raise HttpError(400, "Driver's License verification failed")

        kyc.document_type = payload.document_type
        kyc.document_number = payload.document_number
        if payload.date_of_birth:
            kyc.date_of_birth = payload.date_of_birth
        kyc.prembly_verified_name = verified_name
        kyc.prembly_id_photo = photo_base64
        kyc.status = KYCStatus.UNVERIFIED  # Ready for step 2
        kyc.save()

        return KYCStep1ResponseSchema(
            status=kyc.status,
            document_type=kyc.document_type,
            verified_name=verified_name,
            date_of_birth=kyc.date_of_birth
        )
    except httpx.HTTPStatusError as e:
        try:
            err_data = e.response.json()
            message = err_data.get("message", "Verification failed.")
        except Exception:
            message = str(e)
        raise HttpError(400, f"{message}")
    except HttpError:
        raise
    except Exception as e:
        raise HttpError(400, f"Verification error: {str(e)}")


def _handle_selfie_failure(kyc, reason):
    kyc.selfie_attempts += 1
    remaining = max(0, settings.PREMBLY_MAX_SELFIE_RETRIES - kyc.selfie_attempts)
    
    if remaining == 0:
        kyc.status = KYCStatus.SUBMITTED
        kyc.needs_manual_review = True
        kyc.save()
        
        send_kyc_submitted_email(user=kyc.user)
        
        from notifications.models import Notification
        Notification.objects.create(
            user=kyc.user,
            type='kyc',
            title='KYC Under Review',
            body='Your KYC verification requires manual review and will be processed shortly.'
        )

        from notifications.telegram import TelegramNotifier
        TelegramNotifier.kyc_submitted(
            full_name=kyc.user.full_name,
            email=kyc.user.email,
            document_type=kyc.document_type,
            kyc_id=kyc.id,
        )
        return KYCStep2ResponseSchema(
            status=kyc.status,
            message=f"{reason}. Max retries exceeded. Marked for manual review.",
            remaining_attempts=0
        )
    else:
        kyc.save()
        return KYCStep2ResponseSchema(
            status=kyc.status,
            message=f"{reason}. Please try again.",
            remaining_attempts=remaining
        )


@router.post('/verify-selfie', response=KYCStep2ResponseSchema)
def verify_selfie(request, payload: KYCStep2Schema):
    """
    Step 2 — submit selfie, runs liveness + face match, auto-approves if passes
    """
    try:
        kyc = KYCVerification.objects.get(user=request.user)
    except KYCVerification.DoesNotExist:
        raise HttpError(400, "Must complete Step 1 first")
        
    if kyc.status in [KYCStatus.SUBMITTED, KYCStatus.VERIFIED]:
        raise HttpError(400, f"KYC is already {kyc.status}")
        
    if kyc.selfie_attempts >= settings.PREMBLY_MAX_SELFIE_RETRIES:
        raise HttpError(400, "Maximum retries exceeded. Please wait for manual review.")

    kyc.selfie_url = str(payload.selfie_url)
    
    try:
        # 1. Liveness check
        liveness_res = check_face_liveness(kyc.selfie_url)
        if str(liveness_res.get("status")).lower() == "success" or liveness_res.get("response_code") == "00":
            data = liveness_res.get("data", {})
            confidence = data.get("confidence_in_percentage", 0)
            kyc.liveness_confidence = float(confidence)
            if kyc.liveness_confidence < settings.PREMBLY_LIVENESS_THRESHOLD:
                return _handle_selfie_failure(kyc, "Liveness check failed")
        else:
            return _handle_selfie_failure(kyc, "Liveness check failed")

        # 2. Face comparison
        if not kyc.prembly_id_photo:
            return _handle_selfie_failure(kyc, "No ID photo found for comparison")
            
        match_res = compare_faces(kyc.selfie_url, kyc.prembly_id_photo)
        if str(match_res.get("status")).lower() == "success" or match_res.get("response_code") == "00":
            confidence = match_res.get("confidence")
            if confidence is None:
                confidence = match_res.get("data", {}).get("confidence", 0)
                
            kyc.face_match_confidence = float(confidence)
            if kyc.face_match_confidence < settings.PREMBLY_FACE_MATCH_THRESHOLD:
                return _handle_selfie_failure(kyc, "Face match failed")
        else:
            return _handle_selfie_failure(kyc, "Face match failed")

        # Both passed
        kyc.status = KYCStatus.VERIFIED
        kyc.selfie_attempts = 0
        kyc.save()
        
        send_kyc_approved_email(user=request.user)
        
        from notifications.models import Notification
        Notification.objects.create(
            user=request.user,
            type='kyc',
            title='KYC Verified',
            body='Your KYC verification was successful. You can now use all platform features.'
        )

        from notifications.telegram import TelegramNotifier
        TelegramNotifier.kyc_approved(
            full_name=request.user.full_name,
            email=request.user.email,
            kyc_id=kyc.id,
        )
        
        return KYCStep2ResponseSchema(
            status=kyc.status,
            message="KYC Verified successfully",
            remaining_attempts=0
        )
        
    except HttpError:
        raise
    except Exception as e:
        return _handle_selfie_failure(kyc, f"Error processing selfie: {str(e)}")


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

        # Send Email
        send_kyc_approved_email(user=kyc.user)

        from notifications.models import Notification
        Notification.objects.create(
            user=kyc.user,
            type='kyc',
            title='KYC Approved',
            body='Your KYC verification has been approved by our team.'
        )

        from notifications.telegram import TelegramNotifier
        TelegramNotifier.kyc_approved(
            full_name=kyc.user.full_name,
            email=kyc.user.email,
            kyc_id=kyc.id,
        )

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

        from notifications.models import Notification
        Notification.objects.create(
            user=kyc.user,
            type='kyc',
            title='KYC Rejected',
            body=f'Your KYC verification was rejected. Reason: {payload.reason}'
        )

        from notifications.telegram import TelegramNotifier
        TelegramNotifier.kyc_rejected(
            full_name=kyc.user.full_name,
            email=kyc.user.email,
            kyc_id=kyc.id,
            reason=payload.reason,
        )

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
