from django.contrib import admin
from django.utils.html import format_html
from .models import KYCVerification

@admin.register(KYCVerification)
class KYCVerificationAdmin(admin.ModelAdmin):
    list_display = ('user', 'document_type', 'status', 'created_at')
    list_filter = ('status', 'document_type')
    search_fields = ('user__email', 'user__first_name', 'user__last_name', 'document_number')
    readonly_fields = ('created_at', 'updated_at', 'document_preview', 'selfie_preview')
    
    fieldsets = (
        ('User Info', {
            'fields': ('user', 'status', 'rejection_reason')
        }),
        ('Document Details', {
            'fields': ('document_type', 'document_number', 'date_of_birth', 'document_url', 'document_preview')
        }),
        ('Selfie Details', {
            'fields': ('selfie_url', 'selfie_preview')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
    )

    def document_preview(self, obj):
        if obj.document_url:
            return format_html('<a href="{0}" target="_blank"><img src="{0}" style="max-height: 200px; max-width: 100%;" /></a>', obj.document_url)
        return "No Document"
    document_preview.short_description = 'Document Preview'

    def selfie_preview(self, obj):
        if obj.selfie_url:
            return format_html('<a href="{0}" target="_blank"><img src="{0}" style="max-height: 200px; max-width: 100%;" /></a>', obj.selfie_url)
        return "No Selfie"
    selfie_preview.short_description = 'Selfie Preview'

    def save_model(self, request, obj, form, change):
        if change:
            old_obj = KYCVerification.objects.get(pk=obj.pk)
            if old_obj.status != obj.status:
                from authenticator.email import send_kyc_approved_email, send_kyc_rejected_email
                from notifications.models import Notification
                from notifications.telegram import TelegramNotifier
                
                if obj.status == 'verified':
                    send_kyc_approved_email(user=obj.user)
                    Notification.objects.create(
                        user=obj.user,
                        type='kyc',
                        title='KYC Approved',
                        body='Your KYC verification has been approved by our team.'
                    )
                    TelegramNotifier.kyc_approved(
                        full_name=obj.user.full_name,
                        email=obj.user.email,
                        kyc_id=obj.id,
                    )
                elif obj.status == 'resubmission':
                    reason = obj.rejection_reason or "Document issues."
                    send_kyc_rejected_email(user=obj.user, reason=reason)
                    Notification.objects.create(
                        user=obj.user,
                        type='kyc',
                        title='KYC Rejected',
                        body=f'Your KYC verification was rejected. Reason: {reason}'
                    )
                    TelegramNotifier.kyc_rejected(
                        full_name=obj.user.full_name,
                        email=obj.user.email,
                        kyc_id=obj.id,
                        reason=reason,
                    )
        super().save_model(request, obj, form, change)
