from django.db import models
from django.conf import settings


class KYCStatus(models.TextChoices):
    UNVERIFIED = 'unverified', 'Unverified'
    SUBMITTED = 'submitted', 'Submitted'
    RESUBMISSION = 'resubmission', 'Resubmission'
    VERIFIED = 'verified', 'Verified'


class DocumentType(models.TextChoices):
    NIN = 'nin', 'NIN'
    VOTERS_CARD = 'voters_card', "Voter's Card"
    DRIVERS_LICENSE = 'drivers_license', "Driver's License"
    INTERNATIONAL_PASSPORT = 'international_passport', "International Passport"


class KYCVerification(models.Model):
    """
    Stores user's KYC documents and status for manual verification.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='kyc',
    )
    document_type = models.CharField(
        max_length=50,
        choices=DocumentType.choices,
        default=DocumentType.NIN,
    )
    document_number = models.CharField(
        max_length=50,
        help_text="Document ID number (NIN, Voter's Card, License number, or Passport number)",
    )
    document_url = models.URLField(
        max_length=500,
        blank=True,
        help_text='URL from Cloudinary/S3 containing the ID document image',
    )
    selfie_url = models.URLField(
        max_length=500,
        blank=True,
        help_text='Cloudinary URL of the user selfie for face matching',
    )
    date_of_birth = models.CharField(max_length=50, blank=True)

    status = models.CharField(
        max_length=20,
        choices=KYCStatus.choices,
        default=KYCStatus.UNVERIFIED,
    )
    rejection_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'kyc_verifications'
        verbose_name = 'KYC Verification'
        verbose_name_plural = 'KYC Verifications'
        ordering = ['-created_at']

    def __str__(self):
        return f"KYC for {self.user.email} - {self.status}"
