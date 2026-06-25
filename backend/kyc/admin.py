from django.contrib import admin
from .models import KYCVerification

@admin.register(KYCVerification)
class KYCVerificationAdmin(admin.ModelAdmin):
    list_display = ('user', 'document_type', 'status', 'needs_manual_review', 'created_at')
    list_filter = ('status', 'document_type', 'needs_manual_review')
    search_fields = ('user__email', 'user__first_name', 'user__last_name', 'document_number')
    readonly_fields = ('created_at', 'updated_at')
    # Admin will be able to edit 'status' along with other fields.
