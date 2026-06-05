from django.db import models
from django.conf import settings


class KYCStatus(models.TextChoices):
    UNVERIFIED = 'unverified', 'Unverified'
    SUBMITTED = 'submitted', 'Submitted'
    REJECTED = 'rejected', 'Rejected'
    VERIFIED = 'verified', 'Verified'


class DocumentType(models.TextChoices):
    NIN = 'nin', 'NIN'
    DRIVERS_LICENSE = 'drivers_license', "Driver's License"
    PASSPORT = 'passport', 'Passport'


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
        max_length=20,
        choices=DocumentType.choices,
        default=DocumentType.NIN,
    )
    document_number = models.CharField(
        max_length=50,
        help_text='Document ID number (NIN, License, or Passport number)',
    )
    document_url = models.URLField(
        max_length=500,
        help_text='URL from Cloudinary/S3 containing the ID document image',
    )
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
